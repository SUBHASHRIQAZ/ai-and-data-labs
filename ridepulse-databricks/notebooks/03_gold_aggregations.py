# Databricks notebook source
# MAGIC %md
# MAGIC # Gold aggregations
# MAGIC
# MAGIC Reads `ridepulse.silver.trips` and builds the four tables the dashboard
# MAGIC queries in `sql/` run against:
# MAGIC
# MAGIC - `gold.hourly_demand` — pickup_date, pickup_hour, pickup_zone, trip_count, average_distance, average_fare
# MAGIC - `gold.zone_revenue` — pickup_date, pickup_zone, trip_count, total_revenue, average_fare, average_tip, revenue_rank
# MAGIC - `gold.trip_kpis` — date, total_trips, total_revenue, average_fare, average_distance, average_duration
# MAGIC - `gold.peak_demand` — date, hour, zone, trip_count, demand_level
# MAGIC
# MAGIC `total_revenue` = `base_passenger_fare + tolls + bcf + sales_tax +
# MAGIC congestion_surcharge + airport_fee` — everything charged to the rider,
# MAGIC excluding tips and driver pay. Tips are tracked separately since they're
# MAGIC not platform revenue in the same sense.
# MAGIC
# MAGIC Every table here is a full `overwrite` of Silver, not an incremental
# MAGIC MERGE like `02_silver_transformations.py` uses. That's a deliberate choice,
# MAGIC not an oversight: these are aggregates, so "only the new rows" doesn't
# MAGIC really mean anything — adding one day of trips can shift `revenue_rank`
# MAGIC for zones on other days too. Recomputing the whole thing from Silver is
# MAGIC simpler to reason about and, for a table this size, cheap enough not to
# MAGIC bother optimizing. It's also naturally idempotent: run it twice, get the
# MAGIC same table both times.

# COMMAND ----------

dbutils.widgets.text("catalog", "ridepulse", "Catalog name")
catalog = dbutils.widgets.get("catalog")

silver_table = f"{catalog}.silver.trips"

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

silver = spark.table(silver_table)

revenue_expr = (
    F.col("base_passenger_fare")
    + F.col("tolls")
    + F.col("bcf")
    + F.col("sales_tax")
    + F.col("congestion_surcharge")
    + F.col("airport_fee")
)

silver = silver.withColumn("total_revenue_per_trip", revenue_expr)


def write_gold(df, table_name, cluster_by):
    """Overwrite a Gold table and (re)apply liquid clustering.

    Liquid clustering (`CLUSTER BY`) is the modern alternative to
    `partitionBy` for tables like these: a few hundred rows to a few
    thousand, with no single column large enough to justify Hive-style
    partition directories. It gets set once per table and Databricks keeps
    the data organized as you write more into it — no manual `OPTIMIZE
    ... ZORDER BY` maintenance required (`OPTIMIZE` still compacts files,
    it just also respects the clustering keys now). Silver uses classic
    `partitionBy("pickup_date")` instead because it's a genuinely large,
    date-partitioned fact table where partition pruning pays off on every
    query that filters by date.
    """
    full_name = f"{catalog}.gold.{table_name}"
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_name)
    spark.sql(f"ALTER TABLE {full_name} CLUSTER BY ({', '.join(cluster_by)})")


# COMMAND ----------

# MAGIC %md
# MAGIC ## gold.hourly_demand
# MAGIC
# MAGIC A straightforward `groupBy` + `agg`. Under the hood this is a shuffle:
# MAGIC Spark has to bring rows with the same `(pickup_date, pickup_hour,
# MAGIC pickup_zone)` together before it can count/average them, and with HVFHV
# MAGIC data that grouping key is skewed — Manhattan zones have far more trips
# MAGIC than an outer-borough zone, so some shuffle partitions do a lot more work
# MAGIC than others. Adaptive Query Execution (on by default in Databricks
# MAGIC Runtime) detects that at runtime and splits the oversized partitions back
# MAGIC up automatically; without AQE the usual fix is salting the skewed keys
# MAGIC before grouping. Worth checking `spark.conf.get("spark.sql.adaptive.enabled")`
# MAGIC if you ever see one task in the Spark UI taking far longer than the rest.

# COMMAND ----------

hourly_demand = silver.groupBy("pickup_date", "pickup_hour", "pickup_zone").agg(
    F.count("*").alias("trip_count"),
    F.round(F.avg("trip_miles"), 2).alias("average_distance"),
    F.round(F.avg("base_passenger_fare"), 2).alias("average_fare"),
)

write_gold(hourly_demand, "hourly_demand", cluster_by=["pickup_date", "pickup_zone"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## gold.zone_revenue
# MAGIC
# MAGIC Adds `revenue_rank`: each zone's rank by revenue *within its own day*,
# MAGIC using a window function instead of a second groupBy + join. `Window
# MAGIC .partitionBy("pickup_date").orderBy(desc("total_revenue"))` says "for each
# MAGIC day, order zones by revenue" — `rank()` then assigns 1, 2, 3... per
# MAGIC partition without collapsing the rows the way an aggregate would. This is
# MAGIC what backs the "top zone per day" query in `sql/revenue_analysis.sql`.

# COMMAND ----------

zone_revenue = silver.groupBy("pickup_date", "pickup_zone").agg(
    F.count("*").alias("trip_count"),
    F.round(F.sum("total_revenue_per_trip"), 2).alias("total_revenue"),
    F.round(F.avg("base_passenger_fare"), 2).alias("average_fare"),
    F.round(F.avg("tips"), 2).alias("average_tip"),
)

revenue_rank_window = Window.partitionBy("pickup_date").orderBy(F.desc("total_revenue"))
zone_revenue = zone_revenue.withColumn("revenue_rank", F.rank().over(revenue_rank_window))

write_gold(zone_revenue, "zone_revenue", cluster_by=["pickup_date", "pickup_zone"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## gold.trip_kpis

# COMMAND ----------

trip_kpis = (
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

write_gold(trip_kpis, "trip_kpis", cluster_by=["date"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## gold.peak_demand
# MAGIC
# MAGIC `demand_level` buckets trip counts into Low/Medium/High/Very High using
# MAGIC the quartiles of `trip_count` across all date/hour/zone rows, computed
# MAGIC with `approxQuantile` — so it adapts to whatever volume of data you've
# MAGIC actually loaded instead of hardcoding thresholds that only make sense for
# MAGIC one month of Manhattan-heavy HVFHV data.

# COMMAND ----------

peak_demand_base = (
    silver.groupBy("pickup_date", "pickup_hour", "pickup_zone")
    .agg(F.count("*").alias("trip_count"))
    .withColumnRenamed("pickup_date", "date")
    .withColumnRenamed("pickup_hour", "hour")
    .withColumnRenamed("pickup_zone", "zone")
)

quantiles = peak_demand_base.approxQuantile("trip_count", [0.25, 0.5, 0.75], 0.01)

if len(quantiles) < 3:
    # approxQuantile returns [] (not three NaNs) if Silver is empty --
    # e.g. running 03 before 02 has ever populated it. Fall back to a
    # single bucket instead of crashing; re-running after Silver has data
    # produces real buckets.
    peak_demand = peak_demand_base.withColumn("demand_level", F.lit("Unknown"))
else:
    q1, q2, q3 = quantiles
    peak_demand = peak_demand_base.withColumn(
        "demand_level",
        F.when(F.col("trip_count") <= q1, "Low")
        .when(F.col("trip_count") <= q2, "Medium")
        .when(F.col("trip_count") <= q3, "High")
        .otherwise("Very High"),
    )

write_gold(peak_demand, "peak_demand", cluster_by=["date", "zone"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sanity check

# COMMAND ----------

for tbl in ["hourly_demand", "zone_revenue", "trip_kpis", "peak_demand"]:
    full_name = f"{catalog}.gold.{tbl}"
    print(f"{full_name}: {spark.table(full_name).count():,} rows")

display(spark.table(f"{catalog}.gold.trip_kpis").orderBy("date"))
