# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze ingestion
# MAGIC
# MAGIC Lands raw NYC TLC High Volume FHV (HVFHV) trip records in
# MAGIC `ridepulse.bronze.trips`, more or less as-is. Bronze's job is just to be a
# MAGIC durable, queryable copy of the source file — no filtering, no renaming, no
# MAGIC business logic. Two columns get added on top of the raw schema:
# MAGIC `ingestion_timestamp` (when this notebook ran) and `source_file` (which
# MAGIC parquet file a row came from), so downstream layers can always trace a row
# MAGIC back to its origin.
# MAGIC
# MAGIC Get the data first: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
# MAGIC → "High Volume For-Hire Vehicle Trip Records" → one month, e.g.
# MAGIC `fhvhv_tripdata_2026-01.parquet`. See the repo README for how to get that
# MAGIC file into a Databricks Volume if you're on Free Edition (no outbound
# MAGIC internet from the workspace, so you can't just `wget` it from a notebook).

# COMMAND ----------

dbutils.widgets.text("catalog", "ridepulse", "Catalog name")
dbutils.widgets.text("source_path", "/Volumes/ridepulse/landing/raw/hvfhv/fhvhv_tripdata_2026-01.parquet", "Source parquet path")

catalog = dbutils.widgets.get("catalog")
source_path = dbutils.widgets.get("source_path")

bronze_table = f"{catalog}.bronze.trips"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Catalog, schemas, and volumes
# MAGIC
# MAGIC ```
# MAGIC ridepulse
# MAGIC   ├── landing        (schema — holds Volumes, not tables)
# MAGIC   │     ├── raw          (uploaded parquet/csv files land here)
# MAGIC   │     └── checkpoints  (streaming checkpoints + Auto Loader schema tracking)
# MAGIC   ├── bronze
# MAGIC   ├── silver
# MAGIC   ├── gold
# MAGIC   └── lakeflow_demo  (bronze_trips/silver_trips/gold_* from pipelines/lakeflow_etl.py —
# MAGIC                       the Lakeflow Declarative Pipeline comparison, kept separate so it
# MAGIC                       never collides with the tables this notebook chain writes)
# MAGIC ```
# MAGIC
# MAGIC `landing` is separate from `bronze`/`silver`/`gold` because it holds files
# MAGIC (Volumes), not managed Delta tables — keeping raw uploads and checkpoint
# MAGIC state out of the same schema as governed tables makes it obvious at a
# MAGIC glance which objects in Unity Catalog are "data" versus "plumbing."
# MAGIC
# MAGIC If `CREATE CATALOG` fails with a permission error, your workspace doesn't
# MAGIC allow creating new catalogs (this can happen on Free Edition depending on
# MAGIC how the workspace is configured). Set the `catalog` widget to whatever
# MAGIC catalog you already have access to — the workspace's default one works —
# MAGIC and let the `CREATE SCHEMA`/`CREATE VOLUME` statements run against that
# MAGIC instead; those only need rights inside a catalog you can already use.

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.landing")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.bronze")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.silver")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.gold")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.lakeflow_demo")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.landing.raw")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.landing.checkpoints")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read + tag with ingestion metadata

# COMMAND ----------

from pyspark.sql.functions import col, current_timestamp

# Recent TLC parquet files write pickup/dropoff/request/on_scene timestamps
# with isAdjustedToUTC=false, which Spark would otherwise infer as
# TimestampNTZType -- a newer Delta table feature that Unity Catalog-managed
# tables don't auto-enable, causing a "manually enable timestampNtz" error
# on whichever table gets created first with that schema. Forcing the
# regular TimestampType here avoids that everywhere downstream.
spark.conf.set("spark.sql.parquet.inferTimestampNTZ.enabled", "false")

raw = spark.read.parquet(source_path)

tagged = raw.withColumn("ingestion_timestamp", current_timestamp()).withColumn(
    "source_file", col("_metadata.file_path")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Skip files that are already in Bronze
# MAGIC
# MAGIC This notebook runs as a batch job, so it has no checkpoint to remember what
# MAGIC it already processed — re-running it against the same file would append a
# MAGIC second copy of every row. The fix is simple: check `source_file` against
# MAGIC what's already in the table and only append rows from files that aren't
# MAGIC there yet. That's the whole idempotency story for a batch append job.
# MAGIC (The streaming version of this in `05_streaming_ingestion.py` gets this
# MAGIC for free from its Auto Loader checkpoint — one of the real advantages of
# MAGIC the streaming path even when you're not using it for real-time data.)

# COMMAND ----------

table_exists = spark.catalog.tableExists(bronze_table)

if table_exists:
    already_ingested = [
        row.source_file
        for row in spark.table(bronze_table).select("source_file").distinct().collect()
    ]
    to_write = tagged.filter(~tagged["source_file"].isin(already_ingested))
else:
    to_write = tagged

new_row_count = to_write.count()
print(f"{new_row_count:,} new rows to append (already-ingested files were skipped)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to Bronze

# COMMAND ----------

if new_row_count > 0:
    to_write.write.format("delta").mode("append").saveAsTable(bronze_table)
else:
    print("Nothing new — skipping write.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sanity check

# COMMAND ----------

total = spark.table(bronze_table).count()
print(f"{bronze_table}: {total:,} rows total")
display(spark.table(bronze_table).limit(10))
