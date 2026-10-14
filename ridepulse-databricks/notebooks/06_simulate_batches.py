# Databricks notebook source
# MAGIC %md
# MAGIC # Simulate real-time ride batches
# MAGIC
# MAGIC Splits one month of downloaded HVFHV data into small, chronologically
# MAGIC ordered parquet files (`batch_000.parquet`, `batch_001.parquet`, ...) written
# MAGIC one at a time with a delay in between — simulating new trip files landing
# MAGIC over time without pretending the TLC source itself is a live API.
# MAGIC
# MAGIC Point `05_streaming_ingestion.py`'s `source_path` widget at the same
# MAGIC `output_dir` used here, run it with `trigger_mode = continuous`, and you'll
# MAGIC see Auto Loader pick up each batch as this notebook drops it.
# MAGIC
# MAGIC Batches are parquet, not JSON, to match the `cloudFiles.format = "parquet"`
# MAGIC Auto Loader config in `05_streaming_ingestion.py`.
# MAGIC
# MAGIC `.cache()` below is deliberate: the loop reads from `trips` once per
# MAGIC batch (up to `num_batches` times), and without caching, Spark would redo
# MAGIC the full read + sort + row-numbering from scratch on every single
# MAGIC iteration since DataFrames are lazy and nothing is shared across actions
# MAGIC by default.

# COMMAND ----------

dbutils.widgets.text("input_path", "/Volumes/ridepulse/landing/raw/hvfhv/fhvhv_tripdata_2026-01.parquet", "Full HVFHV parquet path")
dbutils.widgets.text("output_dir", "/Volumes/ridepulse/landing/raw/hvfhv_stream/", "Directory to drop simulated batch files into")
dbutils.widgets.text("batch_size", "100", "Rows per simulated batch")
dbutils.widgets.text("num_batches", "20", "Number of batches to generate (0 = all)")
dbutils.widgets.text("sleep_seconds", "10", "Seconds to wait between batches")

input_path = dbutils.widgets.get("input_path")
output_dir = dbutils.widgets.get("output_dir")
batch_size = int(dbutils.widgets.get("batch_size"))
num_batches = int(dbutils.widgets.get("num_batches"))
sleep_seconds = int(dbutils.widgets.get("sleep_seconds"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Order trips chronologically and assign batch numbers

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

pickup_order = Window.orderBy("pickup_datetime")

trips = (
    spark.read.parquet(input_path)
    .withColumn("row_num", F.row_number().over(pickup_order) - 1)
    .withColumn("batch_id", (F.col("row_num") / batch_size).cast("int"))
    .drop("row_num")
    .cache()
)

total_batches = trips.select(F.max("batch_id")).first()[0] + 1
batches_to_write = total_batches if num_batches == 0 else min(num_batches, total_batches)
print(f"{total_batches} batches available, writing {batches_to_write}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write one batch at a time, pausing between writes

# COMMAND ----------

import time

for batch_id in range(batches_to_write):
    batch_pdf = trips.filter(F.col("batch_id") == batch_id).drop("batch_id").toPandas()
    out_path = f"{output_dir.rstrip('/')}/batch_{batch_id:03d}.parquet"
    batch_pdf.to_parquet(out_path)
    print(f"Wrote {out_path} ({len(batch_pdf)} rows)")

    if batch_id < batches_to_write - 1:
        time.sleep(sleep_seconds)

print("Done.")
