# Databricks notebook source
# MAGIC %md
# MAGIC # Data quality
# MAGIC
# MAGIC Runs a set of checks across Bronze/Silver/Gold and reports PASS/FAIL for
# MAGIC each, then raises if anything failed — so this can gate a Workflow run
# MAGIC (fail this task, the downstream ones don't run) instead of just logging a
# MAGIC warning nobody reads. Run it after `01`, `02`, and `03` have populated
# MAGIC their tables.
# MAGIC
# MAGIC Checks:
# MAGIC - row counts per layer are non-zero, and Silver isn't unexpectedly larger than Bronze
# MAGIC - key columns in Silver have no NULLs
# MAGIC - no duplicate trips in Silver (same natural key `02_silver_transformations.py` merges on)
# MAGIC - fare, distance, and duration are within the bounds Silver is supposed to enforce
# MAGIC - Gold trip counts reconcile against Silver

# COMMAND ----------

dbutils.widgets.text("catalog", "ridepulse", "Catalog name")
dbutils.widgets.text("max_trip_duration_minutes", "180", "Max realistic trip duration (minutes), must match Silver")

catalog = dbutils.widgets.get("catalog")
max_trip_duration_minutes = int(dbutils.widgets.get("max_trip_duration_minutes"))

# COMMAND ----------

from pyspark.sql import functions as F

from transformations import KEY_COLUMNS

results = []


def check(name, passed, detail):
    results.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})


# COMMAND ----------

# MAGIC %md
# MAGIC ## Row counts per layer

# COMMAND ----------

bronze = spark.table(f"{catalog}.bronze.trips")
silver = spark.table(f"{catalog}.silver.trips")

bronze_count = bronze.count()
silver_count = silver.count()

check("bronze.trips has rows", bronze_count > 0, f"{bronze_count:,} rows")
check("silver.trips has rows", silver_count > 0, f"{silver_count:,} rows")
check(
    "silver.trips is not larger than bronze.trips",
    silver_count <= bronze_count,
    f"silver={silver_count:,}, bronze={bronze_count:,}",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: NULL checks on key columns

# COMMAND ----------

NOT_NULL_COLUMNS = ["pickup_datetime", "dropoff_datetime", "PULocationID", "DOLocationID"]

for column in NOT_NULL_COLUMNS:
    null_count = silver.filter(F.col(column).isNull()).count()
    check(f"silver.trips.{column} has no NULLs", null_count == 0, f"{null_count:,} NULLs")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: no duplicate trips

# COMMAND ----------

duplicate_count = silver_count - silver.dropDuplicates(KEY_COLUMNS).count()
check("silver.trips has no duplicate trips", duplicate_count == 0, f"{duplicate_count:,} duplicates")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: fare / distance / duration bounds

# COMMAND ----------

negative_fare_count = silver.filter(F.col("base_passenger_fare") < 0).count()
check("silver.trips has no negative fares", negative_fare_count == 0, f"{negative_fare_count:,} negative fares")

zero_distance_count = silver.filter(F.col("trip_miles") <= 0).count()
check("silver.trips has no zero/negative distances", zero_distance_count == 0, f"{zero_distance_count:,} rows")

bad_duration_count = silver.filter(
    (F.col("trip_duration_minutes") <= 0) | (F.col("trip_duration_minutes") > max_trip_duration_minutes)
).count()
check(
    f"silver.trips duration is within (0, {max_trip_duration_minutes}] minutes",
    bad_duration_count == 0,
    f"{bad_duration_count:,} rows out of bounds",
)

invalid_timestamp_count = silver.filter(F.col("dropoff_datetime") <= F.col("pickup_datetime")).count()
check(
    "silver.trips dropoff is always after pickup",
    invalid_timestamp_count == 0,
    f"{invalid_timestamp_count:,} rows with dropoff <= pickup",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold: trip counts reconcile against Silver

# COMMAND ----------

gold_trip_kpis_total = spark.table(f"{catalog}.gold.trip_kpis").agg(F.sum("total_trips")).first()[0] or 0
check(
    "gold.trip_kpis total_trips matches silver.trips row count",
    gold_trip_kpis_total == silver_count,
    f"gold={gold_trip_kpis_total:,}, silver={silver_count:,}",
)

gold_hourly_demand_total = spark.table(f"{catalog}.gold.hourly_demand").agg(F.sum("trip_count")).first()[0] or 0
check(
    "gold.hourly_demand trip_count matches silver.trips row count",
    gold_hourly_demand_total == silver_count,
    f"gold={gold_hourly_demand_total:,}, silver={silver_count:,}",
)

gold_zone_revenue_total = spark.table(f"{catalog}.gold.zone_revenue").agg(F.sum("trip_count")).first()[0] or 0
check(
    "gold.zone_revenue trip_count matches silver.trips row count",
    gold_zone_revenue_total == silver_count,
    f"gold={gold_zone_revenue_total:,}, silver={silver_count:,}",
)

gold_peak_demand_total = spark.table(f"{catalog}.gold.peak_demand").agg(F.sum("trip_count")).first()[0] or 0
check(
    "gold.peak_demand trip_count matches silver.trips row count",
    gold_peak_demand_total == silver_count,
    f"gold={gold_peak_demand_total:,}, silver={silver_count:,}",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Report

# COMMAND ----------

report = spark.createDataFrame(results)
display(report)

failed = [r for r in results if r["status"] == "FAIL"]
print(f"{len(results) - len(failed)}/{len(results)} checks passed")

if failed:
    for r in failed:
        print(f"FAIL: {r['check']} — {r['detail']}")
    raise AssertionError(f"{len(failed)} data quality check(s) failed")
