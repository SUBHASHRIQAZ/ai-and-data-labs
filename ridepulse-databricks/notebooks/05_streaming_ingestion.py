# Databricks notebook source
# MAGIC %md
# MAGIC # Streaming ingestion (Auto Loader)
# MAGIC
# MAGIC Replaces the one-shot batch read in `01_bronze_ingestion.py` with Auto
# MAGIC Loader (`cloudFiles`) so only newly-arrived files get processed, with a
# MAGIC checkpoint tracking what's already been read. That checkpoint is what
# MAGIC gives you failure recovery for free: kill this query mid-run and restart
# MAGIC it, and it picks up from the last committed offset instead of reprocessing
# MAGIC (or worse, losing) files. It's also what makes this notebook idempotent
# MAGIC without the manual "have I seen this file before" check that
# MAGIC `01_bronze_ingestion.py` needs for its batch path.
# MAGIC
# MAGIC Point `source_path` at a directory that accumulates HVFHV parquet files
# MAGIC over time — the small batched files `06_simulate_batches.py` produces
# MAGIC (`batch_000.parquet`, `batch_001.parquet`, ...) — rather than one static file.
# MAGIC
# MAGIC No watermark here, on purpose: a watermark tells Spark how long to wait
# MAGIC for late-arriving *event-time* data before finalizing a windowed
# MAGIC aggregation. This notebook doesn't aggregate anything, it just passes
# MAGIC rows through to Bronze, so there's nothing for a watermark to bound. The
# MAGIC Kafka path (`07_kafka_streaming_ingestion.py`) does use one, because that
# MAGIC stream is closer to what a real ride-hailing event feed looks like:
# MAGIC events that can genuinely arrive out of order or get retried.
# MAGIC
# MAGIC One more thing worth knowing: Databricks' current recommendation for new
# MAGIC streaming ETL is Lakeflow Declarative Pipelines (the evolution of Delta
# MAGIC Live Tables), which handles checkpoints, retries and schema evolution
# MAGIC through a higher-level `@dlt.table` API. This notebook deliberately stays
# MAGIC at the raw `readStream`/`writeStream` level instead, because the point
# MAGIC here is to actually see Auto Loader and Structured Streaming work rather
# MAGIC than have a framework manage them for you — useful to know when you'd
# MAGIC reach for the framework, useful to have built it by hand once too.

# COMMAND ----------

dbutils.widgets.text("catalog", "ridepulse", "Catalog name")
dbutils.widgets.text("source_path", "/Volumes/ridepulse/landing/raw/hvfhv_stream/", "Source directory to watch")
dbutils.widgets.text("checkpoint_path", "/Volumes/ridepulse/landing/checkpoints/bronze_trips_stream/", "Checkpoint location")
dbutils.widgets.dropdown("trigger_mode", "availableNow", ["availableNow", "continuous"], "Trigger mode")

catalog = dbutils.widgets.get("catalog")
source_path = dbutils.widgets.get("source_path")
checkpoint_path = dbutils.widgets.get("checkpoint_path")
trigger_mode = dbutils.widgets.get("trigger_mode")

target_table = f"{catalog}.bronze.trips_stream"
schema_location = f"{checkpoint_path}_schema"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read new files with Auto Loader
# MAGIC
# MAGIC `cloudFiles.schemaLocation` is where Auto Loader remembers the schema it
# MAGIC inferred from the first files it saw, so it doesn't have to re-infer (and
# MAGIC potentially guess differently) on every run. `schemaEvolutionMode =
# MAGIC addNewColumns` is actually the default, but it's worth setting explicitly:
# MAGIC if TLC adds a column mid-stream, this stream stops itself with an
# MAGIC exception on the batch containing the new column rather than silently
# MAGIC dropping data, and picking the run back up after that (same checkpoint,
# MAGIC same code) continues with the new column included.

# COMMAND ----------

from pyspark.sql.functions import col, current_timestamp

# Same fix as 01_bronze_ingestion.py: recent TLC parquet writes timestamp
# columns with isAdjustedToUTC=false, which Spark would otherwise infer as
# TimestampNTZType -- a Delta table feature Unity Catalog doesn't
# auto-enable, so the first write to a new table fails asking you to
# manually run ALTER TABLE ... SET TBLPROPERTIES. Forcing the regular
# TimestampType avoids that.
spark.conf.set("spark.sql.parquet.inferTimestampNTZ.enabled", "false")

stream_df = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "parquet")
    .option("cloudFiles.schemaLocation", schema_location)
    .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
    .load(source_path)
    .withColumn("ingestion_timestamp", current_timestamp())
    .withColumn("source_file", col("_metadata.file_path"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the stream to Bronze
# MAGIC
# MAGIC `availableNow` processes everything currently sitting in `source_path` and
# MAGIC then stops — good for demoing incremental batches one at a time. Switch to
# MAGIC a `processingTime` trigger (e.g. `"30 seconds"`) for a query that keeps
# MAGIC running and picks up new files as they land.

# COMMAND ----------

query = stream_df.writeStream.format("delta").option("checkpointLocation", checkpoint_path)

if trigger_mode == "availableNow":
    query = query.trigger(availableNow=True)
else:
    query = query.trigger(processingTime="30 seconds")

streaming_query = query.toTable(target_table)
streaming_query.awaitTermination()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sanity check

# COMMAND ----------

row_count = spark.table(target_table).count()
print(f"{target_table}: {row_count:,} rows")

display(spark.table(target_table).orderBy(col("ingestion_timestamp").desc()).limit(10))
