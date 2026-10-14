# Databricks notebook source
# MAGIC %md
# MAGIC # Silver transformations
# MAGIC
# MAGIC Reads `ridepulse.bronze.trips`, cleans it up, and writes `ridepulse.silver.trips`.
# MAGIC The actual logic lives in `transformations.py` (same folder) so it can be
# MAGIC unit tested with a local SparkSession outside of Databricks — see
# MAGIC `tests/test_transformations.py`. This notebook is really just wiring:
# MAGIC read table → call the functions → write table.
# MAGIC
# MAGIC What gets cleaned:
# MAGIC - NULL pickup/dropoff timestamps or location IDs
# MAGIC - negative fares
# MAGIC - zero/negative distance
# MAGIC - dropoff at or before pickup
# MAGIC - duplicate trips (same license/base/pickup/dropoff/locations)
# MAGIC - trips longer than `max_trip_duration_minutes` (default 180 — a HVFHV
# MAGIC   trip running 3+ hours is almost certainly a bad timestamp, not a real ride)
# MAGIC
# MAGIC What gets added: `pickup_date`, `pickup_hour`, `day_of_week`,
# MAGIC `trip_duration_minutes`, `average_speed`, and `pickup_zone`/`dropoff_zone`
# MAGIC resolved from the TLC taxi zone lookup table.

# COMMAND ----------

dbutils.widgets.text("catalog", "ridepulse", "Catalog name")
dbutils.widgets.text("zone_lookup_path", "/Volumes/ridepulse/landing/raw/taxi_zone_lookup.csv", "Taxi zone lookup CSV path")
dbutils.widgets.text("max_trip_duration_minutes", "180", "Max realistic trip duration (minutes)")

catalog = dbutils.widgets.get("catalog")
zone_lookup_path = dbutils.widgets.get("zone_lookup_path")
max_trip_duration_minutes = int(dbutils.widgets.get("max_trip_duration_minutes"))

bronze_table = f"{catalog}.bronze.trips"
silver_table = f"{catalog}.silver.trips"

# COMMAND ----------

from transformations import KEY_COLUMNS, clean_trips, enrich_trips, add_zone_names

bronze = spark.table(bronze_table)
bronze_count = bronze.count()

# COMMAND ----------

cleaned = clean_trips(bronze)
silver = enrich_trips(cleaned, max_trip_duration_minutes)

zone_lookup = spark.read.option("header", True).option("inferSchema", True).csv(zone_lookup_path)
silver = add_zone_names(silver, zone_lookup)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write with MERGE, not overwrite
# MAGIC
# MAGIC This cell reprocesses the whole Bronze table every run — fine at one
# MAGIC month of data, wasteful at a year of it. A `.mode("overwrite")` would work
# MAGIC correctly here too, but MERGE is the pattern that actually scales: only
# MAGIC changed/new rows get written, and running this notebook twice in a row
# MAGIC (or re-running after adding February's file to Bronze) doesn't create
# MAGIC duplicates — the same natural key used for dedup in `clean_trips` doubles
# MAGIC as the merge key. `<=>` (null-safe equals) instead of `=` matters here
# MAGIC because two NULLs should count as "matching" for merge purposes; plain
# MAGIC `=` treats NULL <> NULL as unknown and the row would never match, so
# MAGIC you'd get a duplicate insert instead of an update.
# MAGIC
# MAGIC `repartition("pickup_date")` before the write is a shuffle — it moves rows
# MAGIC around the cluster so all rows for a given date land in the same output
# MAGIC partition, which is what you want right before writing data that's
# MAGIC partitioned by that same column (otherwise every task can dump a small
# MAGIC file into every partition, and you end up with a small-files problem).
# MAGIC `coalesce()` would be the wrong tool here — it only reduces partition
# MAGIC count without a shuffle, so it can't reorganize rows by key, only merge
# MAGIC existing partitions together.

# COMMAND ----------

from delta.tables import DeltaTable

silver = silver.repartition("pickup_date")

if not spark.catalog.tableExists(silver_table):
    silver.write.format("delta").partitionBy("pickup_date").saveAsTable(silver_table)
else:
    merge_condition = " AND ".join(f"target.{c} <=> source.{c}" for c in KEY_COLUMNS)
    (
        DeltaTable.forName(spark, silver_table)
        .alias("target")
        .merge(silver.alias("source"), merge_condition)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sanity check

# COMMAND ----------

silver_count = spark.table(silver_table).count()
print(f"bronze: {bronze_count:,} rows, silver: {silver_count:,} rows after cleaning")
display(spark.table(silver_table).limit(10))
