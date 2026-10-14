"""RidePulse, reimplemented as a Lakeflow Declarative Pipeline.

This is a side-by-side comparison, not a replacement. notebooks/01-03 stay
the primary, hand-orchestrated implementation of Bronze -> Silver -> Gold
(a Databricks Job with notebook tasks — see resources/jobs.yml); this file
implements the same three layers declaratively instead, publishing into a
separate ridepulse.lakeflow_demo schema so it doesn't collide with the
tables the notebooks write to ridepulse.bronze/silver/gold.

Uses `pyspark.pipelines` (the module Databricks ships as it open-sources
Declarative Pipelines into Apache Spark), not the older `import dlt` API —
`dp.table` for Bronze, `dp.materialized_view` for Silver/Gold, explicitly,
rather than inferring "streaming table vs. materialized view" from whether
a query happens to call readStream or not. I haven't been able to run this
against a live workspace, and pyspark.pipelines is new enough that I'm
genuinely less certain about it than I am about the rest of this repo. If
`dp.materialized_view` / `dp.table` / `dp.expect_or_drop` don't match your
runtime's API surface, the fallback is the older, extremely stable `import
dlt` module: `@dlt.table(...)` for both roles (it infers streaming vs.
materialized from the query itself), `dlt.read(...)` in place of
`dp.read(...)`, same decorator arguments otherwise.

Worth reading next to notebooks/01-03 rather than instead of them — most of
the value here is in what's DIFFERENT, not what's the same:

- Bronze is a **streaming table** (`@dp.table`, incremental, append-only) —
  the pipeline's own checkpointing makes it idempotent automatically, same
  as 05_streaming_ingestion.py, minus writing the checkpoint plumbing
  yourself. This is the same role a streaming table plays in
  01_bronze_ingestion.py's batch path, just without the manual "have I
  already ingested this file" check that notebook needs.
- Silver and all four Gold tables are **materialized views**
  (`@dp.materialized_view`) — batch-recomputed, not incrementally appended.
  That's a deliberate, explicit choice here, not an accident of which read
  API got used: cleaning drops rows (not appendable), dedup and the
  window-function rank in gold_zone_revenue need to see the whole table at
  once, and 02_silver_transformations.py's hand-written `MERGE INTO` exists
  specifically to make a full-table recompute idempotent — a materialized
  view gets that idempotency from the pipeline engine deciding
  incremental-vs-full-refresh itself, no MERGE required.
- Cleaning in the notebook path is imperative — transformations.clean_trips()
  calls .filter() four times. Cleaning here is four @dp.expect_or_drop
  decorators instead: the same four rules, but declared as constraints the
  pipeline enforces and reports on (Data Engineering -> Pipelines -> this
  pipeline -> the data quality tab shows pass/fail counts per rule), rather
  than lines of imperative code you have to read to know what's enforced.
- partition_cols / cluster_by below are the exact same partitioning
  (Silver, by pickup_date) and liquid clustering (Gold, by the columns
  queries actually filter on) decisions made in notebooks/02 and
  notebooks/03 — declared as decorator arguments here instead of a
  `.write.partitionBy(...)` call or a separate `ALTER TABLE ... CLUSTER BY`.

enrich_trips() and add_zone_names() are imported from transformations.py
unchanged — same broadcast join, same derived columns, proof the two
implementations aren't secretly doing different things. clean_trips() is
NOT imported, on purpose: its filtering logic is what got re-expressed as
expectations above.

If the import below doesn't resolve in your workspace (pipeline source file
resolution can behave differently from a regular notebook's), copy
enrich_trips/add_zone_names/KEY_COLUMNS from notebooks/transformations.py
directly into this file instead — same logic, just not shared by reference.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "notebooks"))
from transformations import KEY_COLUMNS, add_zone_names, enrich_trips  # noqa: E402

from pyspark import pipelines as dp  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402
from pyspark.sql.window import Window  # noqa: E402

source_path = spark.conf.get("source_path")
zone_lookup_path = spark.conf.get("zone_lookup_path")
# source_path must be a directory here, not an exact file path -- Auto
# Loader (cloudFiles) below watches/lists it. resources/pipelines.yml maps
# this to var.lakeflow_source_dir specifically for that reason, not the
# var.source_path notebooks/01_bronze_ingestion.py reads as one exact file.

# Same fix as notebooks/01_bronze_ingestion.py and 05_streaming_ingestion.py:
# recent TLC parquet writes timestamp columns with isAdjustedToUTC=false,
# which Spark would otherwise infer as TimestampNTZType -- a Delta table
# feature Unity Catalog doesn't auto-enable, so the first write to
# bronze_trips fails asking for a manual ALTER TABLE ... SET TBLPROPERTIES.
spark.conf.set("spark.sql.parquet.inferTimestampNTZ.enabled", "false")

# ---------------------------------------------------------------- bronze --

@dp.table(
    comment="Raw HVFHV trips via Auto Loader — declarative equivalent of "
            "notebooks/05_streaming_ingestion.py. Checkpointing and "
            "idempotency are handled by the pipeline, not hand-written.",
)
def bronze_trips():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .load(source_path)
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("source_file", F.col("_metadata.file_path"))
    )


# ---------------------------------------------------------------- silver --

@dp.materialized_view(
    comment="Cleaned, deduplicated, enriched trips — declarative equivalent "
            "of notebooks/02_silver_transformations.py, minus the hand-written MERGE.",
    partition_cols=["pickup_date"],
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


# ------------------------------------------------------------------ gold --

@dp.materialized_view(
    comment="Trip counts/fares/distance by date, hour, zone — same shape as ridepulse.gold.hourly_demand.",
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
    comment="Revenue by date/zone with the same window-function revenue_rank as ridepulse.gold.zone_revenue.",
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
