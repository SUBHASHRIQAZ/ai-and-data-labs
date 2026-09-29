import sys

sys.path.append(spark.conf.get("bundle.sourcePath") + "/nyc_ridepulse_etl/nyc_ridepulse")

# COMMAND ----------

import json

# transformations is a Databricks notebook (.ipynb), not a .py module,
# so we load it from the workspace FUSE mount and exec the code directly.
_nb_path = "/Workspace/NY_TLC_RidePulse_Demo/ai-and-data-labs/nyc_ridepulse/src/nyc_ridepulse/transformations.ipynb"
with open(_nb_path) as _f:
    _nb = json.load(_f)
for _cell in _nb.get("cells", []):
    if _cell["cell_type"] == "code":
        _src = _cell["source"]
        if isinstance(_src, list):
            _src = "".join(_src)
        exec(_src)

# COMMAND ----------

from pyspark import pipelines as dp  
from pyspark.sql import functions as F  
from pyspark.sql.window import Window

source_path = spark.conf.get("source_path")
zone_lookup_path = spark.conf.get("zone_lookup_path")
spark.conf.set("spark.sql.parquet.inferTimestampNTZ.enabled", "false")


@dp.table()
def bronze_trips():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .load(source_path)
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("source_file", F.col("_metadata.file_path"))
    )



@dp.materialized_view(
    partition_cols=["pickup_date"]
)
@dp.expect_or_drop(
    "valid_pickup_dropoff",
    "pickup_datetime IS NOT NULL AND dropoff_datetime IS NOT NULL "
    "AND PULocationID IS NOT NULL AND DOLocationID IS NOT NULL",
)
@dp.expect_or_drop("non_negative_fare", "base_passenger_fare >= 0")
@dp.expect_or_drop("positive_distance", "trip_miles > 0")
@dp.expect_or_drop("dropoff_after_pickup", "dropoff_datetime > pickup_datetime")
def silver_trips():
    bronze = dp.read("bronze_trips")
    deduped = bronze.dropDuplicates(KEY_COLUMNS)
    enriched = enrich_trips(deduped)
    zone_lookup = spark.read.option("header", True).option("inferSchema", True).csv(zone_lookup_path)
    return add_zone_names(enriched, zone_lookup)


@dp.materialized_view(
    cluster_by=["pickup_date", "pickup_zone"],
)
def gold_hourly_demand():
    silver = dp.read("silver_trips")
    return silver.groupBy("pickup_date", "pickup_hour", "pickup_zone").agg(
        F.count("*").alias("trip_count"),
        F.round(F.avg("trip_miles"), 2).alias("average_distance"),
        F.round(F.avg("base_passenger_fare"), 2).alias("average_fare"),
    )


@dp.materialized_view(
    cluster_by=["pickup_date", "pickup_zone"],
)
def gold_zone_revenue():
    silver = dp.read("silver_trips").withColumn(
        "total_revenue_per_trip",
        F.col("base_passenger_fare")
        + F.col("tolls")
        + F.col("bcf")
        + F.col("sales_tax")
        + F.col("congestion_surcharge")
        + F.col("airport_fee"),
    )
    revenue = silver.groupBy("pickup_date", "pickup_zone").agg(
        F.count("*").alias("trip_count"),
        F.round(F.sum("total_revenue_per_trip"), 2).alias("total_revenue"),
        F.round(F.avg("base_passenger_fare"), 2).alias("average_fare"),
        F.round(F.avg("tips"), 2).alias("average_tip"),
    )
    revenue_rank_window = Window.partitionBy("pickup_date").orderBy(F.desc("total_revenue"))
    return revenue.withColumn("revenue_rank", F.rank().over(revenue_rank_window))


@dp.materialized_view(
    comment="Daily trip KPIs — same shape as ridepulse.gold.trip_kpis.",
    cluster_by=["date"],
)
def gold_trip_kpis():
    silver = dp.read("silver_trips").withColumn(
        "total_revenue_per_trip",
        F.col("base_passenger_fare")
        + F.col("tolls")
        + F.col("bcf")
        + F.col("sales_tax")
        + F.col("congestion_surcharge")
        + F.col("airport_fee"),
    )
    return (
        silver.groupBy("pickup_date")
        .agg(
            F.count("*").alias("total_trips"),
            F.round(F.sum("total_revenue_per_trip"), 2).alias("total_revenue"),
            F.round(F.avg("base_passenger_fare"), 2).alias("average_fare"),
            F.round(F.avg("trip_miles"), 2).alias("average_distance"),
            F.round(F.avg("trip_duration_minutes"), 2).alias("average_duration"),
        )
        .withColumnRenamed("pickup_date", "date")
    )


@dp.materialized_view(
    comment="Demand level (Low/Medium/High/Very High) by date/hour/zone — same shape as ridepulse.gold.peak_demand.",
    cluster_by=["date", "zone"],
)
def gold_peak_demand():
    base = (
        dp.read("silver_trips")
        .groupBy("pickup_date", "pickup_hour", "pickup_zone")
        .agg(F.count("*").alias("trip_count"))
        .withColumnRenamed("pickup_date", "date")
        .withColumnRenamed("pickup_hour", "hour")
        .withColumnRenamed("pickup_zone", "zone")
    )
    quantiles = base.approxQuantile("trip_count", [0.25, 0.5, 0.75], 0.01)
    if len(quantiles) < 3:
        # approxQuantile returns [] (not three NaNs) on an empty DataFrame --
        # e.g. this view materializing before bronze_trips has ingested
        # anything yet on a first run. Fall back to a single bucket instead
        # of crashing; the next refresh recomputes real buckets once there's
        # data to quantile.
        return base.withColumn("demand_level", F.lit("Unknown"))

    q1, q2, q3 = quantiles
    return base.withColumn(
        "demand_level",
        F.when(F.col("trip_count") <= q1, "Low")
        .when(F.col("trip_count") <= q2, "Medium")
        .when(F.col("trip_count") <= q3, "High")
        .otherwise("Very High"),
    )

