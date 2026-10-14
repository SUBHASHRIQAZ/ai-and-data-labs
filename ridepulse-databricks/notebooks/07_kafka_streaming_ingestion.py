# Databricks notebook source
# MAGIC %md
# MAGIC # Kafka streaming ingestion
# MAGIC
# MAGIC Consumes the `ride-events` topic published by `kafka/ride_producer.py` and
# MAGIC lands deduplicated events in `ridepulse.bronze.ride_events`.
# MAGIC
# MAGIC This is a separate table from `ridepulse.bronze.trips` — the Kafka event
# MAGIC payload is a simplified live-ride shape (`trip_id`, `pickup_time`,
# MAGIC `pickup_zone`, `dropoff_zone`, `distance`, `fare`), not the full HVFHV
# MAGIC record used by the batch/Auto Loader path.
# MAGIC
# MAGIC Databricks Free Edition restricts outbound internet access, so this
# MAGIC notebook likely won't run there unless your Kafka broker happens to be
# MAGIC reachable from the workspace. Get Phase 1 and Phase 2 working first — see
# MAGIC the README for why Kafka is deliberately last.

# COMMAND ----------

dbutils.widgets.text("catalog", "ridepulse", "Catalog name")
dbutils.widgets.text("kafka_bootstrap_servers", "localhost:9092", "Kafka bootstrap servers")
dbutils.widgets.text("kafka_topic", "ride-events", "Kafka topic")
dbutils.widgets.text("checkpoint_path", "/Volumes/ridepulse/landing/checkpoints/bronze_ride_events/", "Checkpoint location")
dbutils.widgets.text("watermark_delay", "10 minutes", "How long to tolerate late-arriving events")

catalog = dbutils.widgets.get("catalog")
kafka_bootstrap_servers = dbutils.widgets.get("kafka_bootstrap_servers")
kafka_topic = dbutils.widgets.get("kafka_topic")
checkpoint_path = dbutils.widgets.get("checkpoint_path")
watermark_delay = dbutils.widgets.get("watermark_delay")

target_table = f"{catalog}.bronze.ride_events"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read from Kafka and parse the JSON payload

# COMMAND ----------

from pyspark.sql.functions import col, current_timestamp, from_json
from pyspark.sql.types import StringType, StructField, StructType, DoubleType, TimestampType

event_schema = StructType([
    StructField("trip_id", StringType()),
    StructField("pickup_time", TimestampType()),
    StructField("pickup_zone", StringType()),
    StructField("dropoff_zone", StringType()),
    StructField("distance", DoubleType()),
    StructField("fare", DoubleType()),
])

raw_kafka = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", kafka_bootstrap_servers)
    .option("subscribe", kafka_topic)
    .option("startingOffsets", "latest")
    .load()
)

ride_events = (
    raw_kafka
    .select(from_json(col("value").cast("string"), event_schema).alias("event"), col("timestamp").alias("kafka_timestamp"))
    .select("event.*", "kafka_timestamp")
    .withColumn("ingestion_timestamp", current_timestamp())
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Watermark + dedup
# MAGIC
# MAGIC A real ride-event feed can redeliver the same event (producer retries,
# MAGIC consumer rebalances) or deliver it late relative to when the ride
# MAGIC actually happened. Two separate problems, two separate tools:
# MAGIC
# MAGIC - **Duplicates** — `dropDuplicates(["trip_id"])` drops repeats of the same
# MAGIC   `trip_id`. That's the "exactly-once" half of the story on the read side;
# MAGIC   the write side (`toTable` with a checkpoint) already guarantees
# MAGIC   exactly-once delivery of whatever this query decides to emit, so
# MAGIC   together you get end-to-end exactly-once processing.
# MAGIC - **State growth** — `dropDuplicates` on an unbounded stream has to
# MAGIC   remember every `trip_id` it's ever seen, forever, or it can't tell a
# MAGIC   duplicate from a new event. `withWatermark("pickup_time", ...)` bounds
# MAGIC   that: it tells Spark "once an event's `pickup_time` falls more than
# MAGIC   `watermark_delay` behind the latest `pickup_time` seen so far, stop
# MAGIC   waiting for more events at or before that time." Spark can then safely
# MAGIC   drop the dedup state for anything older than the watermark instead of
# MAGIC   keeping it in memory indefinitely. The trade-off: an event that arrives
# MAGIC   *later* than `watermark_delay` gets silently dropped rather than
# MAGIC   deduplicated correctly. Widening the delay catches more late data at
# MAGIC   the cost of more state kept around and a longer lag before results are
# MAGIC   final — there's no setting that's right for every workload.

# COMMAND ----------

ride_events = ride_events.withWatermark("pickup_time", watermark_delay).dropDuplicates(["trip_id"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to Bronze
# MAGIC
# MAGIC `processingTime="10 seconds"` is the trigger interval: how often Spark
# MAGIC wakes up, checks Kafka for new records, and processes a micro-batch. A
# MAGIC shorter interval means lower end-to-end latency and more small
# MAGIC micro-batches (more overhead per batch); a longer one trades latency for
# MAGIC fewer, larger batches. `trigger(availableNow=True)` (used in
# MAGIC `05_streaming_ingestion.py`) is the other end of that spectrum —
# MAGIC process what's there right now and stop, rather than run continuously.

# COMMAND ----------

(
    ride_events.writeStream
    .format("delta")
    .option("checkpointLocation", checkpoint_path)
    .trigger(processingTime="10 seconds")
    .toTable(target_table)
)
