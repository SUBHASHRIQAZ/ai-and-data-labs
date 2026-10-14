"""Pure PySpark Silver-layer transformation logic.

Kept as a plain module (no `# Databricks notebook source` header) separate
from `02_silver_transformations.py` so it can be imported and unit tested
with a local SparkSession — no Databricks runtime needed. See
`tests/test_transformations.py`.

When run as a Databricks Repo / Git folder, notebooks can import modules
from the same directory directly, e.g.:

    from transformations import clean_trips, enrich_trips, add_zone_names

Everything here uses Spark's built-in functions rather than a Python UDF.
`to_date`, `hour`, `dayofweek` and friends run inside the JVM as part of the
Catalyst-optimized plan; a Python UDF would mean serializing every row out to
a Python process and back, which is usually the slower choice unless the
logic genuinely can't be expressed with built-ins (regex-heavy parsing,
calling an external library, etc).
"""

from pyspark.sql import DataFrame
from pyspark.sql.functions import broadcast, col, to_date, hour, dayofweek, unix_timestamp, round as spark_round

KEY_COLUMNS = [
    "hvfhs_license_num",
    "dispatching_base_num",
    "pickup_datetime",
    "dropoff_datetime",
    "PULocationID",
    "DOLocationID",
]


def clean_trips(df: DataFrame) -> DataFrame:
    """Drop NULL/invalid/duplicate trips per the Silver cleaning rules."""
    return (
        df.dropna(subset=["pickup_datetime", "dropoff_datetime", "PULocationID", "DOLocationID"])
        .filter(col("base_passenger_fare") >= 0)
        .filter(col("trip_miles") > 0)
        .filter(col("dropoff_datetime") > col("pickup_datetime"))
        .dropDuplicates(KEY_COLUMNS)
    )


def enrich_trips(df: DataFrame, max_trip_duration_minutes: int = 180) -> DataFrame:
    """Add pickup_date/pickup_hour/day_of_week/trip_duration_minutes/average_speed,
    dropping trips whose duration falls outside (0, max_trip_duration_minutes]."""
    enriched = (
        df.withColumn("pickup_date", to_date("pickup_datetime"))
        .withColumn("pickup_hour", hour("pickup_datetime"))
        .withColumn("day_of_week", dayofweek("pickup_datetime"))
        .withColumn(
            "trip_duration_minutes",
            spark_round((unix_timestamp("dropoff_datetime") - unix_timestamp("pickup_datetime")) / 60, 2),
        )
        .filter(col("trip_duration_minutes") > 0)
        .filter(col("trip_duration_minutes") <= max_trip_duration_minutes)
    )
    return enriched.withColumn(
        "average_speed", spark_round(col("trip_miles") / (col("trip_duration_minutes") / 60), 2)
    )


def add_zone_names(df: DataFrame, zone_lookup: DataFrame) -> DataFrame:
    """Join PULocationID/DOLocationID against a taxi zone lookup (LocationID, Zone)
    table to add pickup_zone/dropoff_zone columns.

    The zone lookup is ~265 rows — a few KB. Broadcasting it means every
    executor gets a local copy and the join runs with no shuffle at all,
    instead of Spark shuffling the (much bigger) trips DataFrame across the
    cluster to co-locate matching keys. `broadcast()` is a hint; Spark would
    likely pick this plan on its own for a table this size once
    `spark.sql.autoBroadcastJoinThreshold` kicks in, but it's cheap to be
    explicit about it, especially since we join twice (pickup and dropoff).
    """
    zones = broadcast(zone_lookup.select(col("LocationID"), col("Zone")))
    result = (
        df.join(zones.withColumnRenamed("Zone", "pickup_zone"), df["PULocationID"] == zones["LocationID"], "left")
        .drop("LocationID")
    )
    result = (
        result.join(
            zones.withColumnRenamed("Zone", "dropoff_zone"), result["DOLocationID"] == zones["LocationID"], "left"
        )
        .drop("LocationID")
    )
    return result
