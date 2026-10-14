# Interview Q&A

Direct answers to the questions below, as you'd actually say them out loud
— not the deep-dive versions. For the full reasoning behind any of these,
`docs/concepts.md` has the same material organized by concept instead of by
question, with exact file/line pointers; `docs/pipeline_logic.md` has the
step-by-step "what the code does." This file is the condensed, rehearsable
version.

Not every answer here is "yes, and here's the code" — a few are honestly
"no, and here's why / here's what would need to change." Overclaiming on
these in an actual interview is worse than a clear "I didn't build that
part, here's how I'd approach it."

## PySpark

**How did you handle skew?**
HVFHV trip volume is heavily concentrated in Manhattan zones, so grouping
by `pickup_zone` doesn't split work evenly across shuffle partitions. I
relied on Adaptive Query Execution — on by default in Databricks Runtime —
which detects oversized partitions at runtime and splits them
automatically. I didn't hand-write salting for this project; if I couldn't
rely on AQE, the fix would be salting the skewed key (append a random
suffix, group on the salted key, aggregate the partial results a second
time) to spread the hot key across more partitions.

**How did you optimize joins?**
The one join in this pipeline — trips to the taxi zone lookup — is a
broadcast join (`transformations.py` → `add_zone_names()`). The lookup is
~265 rows, so every executor gets a local copy and the join runs with no
shuffle of the much larger trips DataFrame at all.

**When would you use broadcast join?**
When one side of a join is small enough to hold in memory on every
executor — roughly under `spark.sql.autoBroadcastJoinThreshold` (30MB by
default). It trades a shuffle of the large side for shipping a small
table to every node. I would *not* use it between two large fact tables —
that's a sort-merge (shuffle) join, no way around it.

**How did you handle nulls?**
Two layers. `clean_trips()` drops rows with NULL pickup/dropoff timestamps
or location IDs before anything downstream sees them (`dropna(subset=[...])`).
Separately, `04_data_quality.py` re-checks that Silver has zero NULLs in
those same columns afterward — so a regression in the cleaning logic gets
caught as a failed check, not silently passed through.

**How did you partition the data?**
Silver is partitioned by `pickup_date` (`partitionBy("pickup_date")`) —
it's a large, date-driven fact table where partition pruning helps on
every date-filtered query. Gold tables are small aggregates instead, so I
used liquid clustering (`CLUSTER BY`) there rather than partitioning — they
don't have the row count to justify Hive-style partition directories.

**How did you avoid expensive groupBy operations?**
I didn't avoid `groupBy` itself — Gold's whole job is aggregation, so those
calls are necessary. What I avoided was a *redundant second* one:
`zone_revenue`'s `revenue_rank` uses a window function over the
already-grouped result instead of grouping again and joining it back — one
shuffle instead of two for that column. Precise framing matters here; "we
don't aggregate" would be wrong.

## Databricks

**Why Delta instead of Parquet?**
Delta is Parquet plus a transaction log that tracks which files make up
which version of a table. That log is what makes `MERGE` possible (atomic
upsert, not manually rewriting files), what makes time travel possible
(old versions stay addressable), what makes writes ACID (no reader ever
sees a half-applied write), and what Auto Loader's schema tracking builds
on. Plain Parquet is fine for a write-once, read-only table; it stops
working the moment you need updates, crash recovery, or history — which is
most of what Silver and Gold do here.

**What is Auto Loader?**
A Databricks Structured Streaming source (`cloudFiles`) that incrementally
discovers new files in cloud storage or a Volume without you tracking
what's already been read — that bookkeeping lives in a checkpoint. Used in
`05_streaming_ingestion.py`, and again as the `bronze_trips` streaming
table in the Lakeflow Pipeline comparison.

**How does schema evolution work?**
Auto Loader tracks the inferred schema in `cloudFiles.schemaLocation` so it
isn't re-inferred on every run. With `cloudFiles.schemaEvolutionMode =
"addNewColumns"` (set explicitly, not left as a default), a new column
showing up in a later file stops the stream on that batch with an
exception instead of silently dropping data — restarting from the same
checkpoint picks up with the wider schema.

**What is checkpointing?**
A durable record of exactly what a streaming query has already processed —
which Kafka offsets, which files — so a restart after a crash resumes from
the last committed point instead of reprocessing or dropping anything.
It's what makes the streaming notebooks idempotent and failure-recoverable
without any manual bookkeeping (contrast with Bronze's batch path, which
needs a manual `source_file` check for the same property).

**What is Delta MERGE?**
An atomic upsert — match source rows against target rows on a key, update
what matches, insert what doesn't, as one transaction. Used to write
Silver, keyed on the same natural key used for dedup during cleaning, with
null-safe equals (`<=>`) instead of `=` since two NULLs should count as a
match for merge purposes.

**What is OPTIMIZE?**
Compacts small Delta files into larger ones — matters after many small
writes from streaming, `MERGE`, or repeated appends. On a liquid-clustered
table it also reorganizes data around the clustering keys in the same
pass.

**What is Z-ORDER?**
The older technique for co-locating related data within files, run via
`OPTIMIZE ... ZORDER BY (...)`. I didn't use it in this project — I used
liquid clustering instead, which is the newer replacement: set the
clustering columns once, and the engine keeps data organized as more gets
written, without repeated manual `ZORDER` maintenance.

**What is liquid clustering?**
The modern alternative to Hive-style partitioning and Z-ORDER for tables
without an obvious high-cardinality partition column. Declare `CLUSTER BY`
once; the engine keeps files organized around those columns over time. All
four Gold tables use it, clustered on the columns the dashboard queries
actually filter on.

**What is Unity Catalog?**
Databricks' governance layer on top of Delta — a three-level
`catalog.schema.table` namespace plus access control, lineage, and audit
logging. `ridepulse.bronze/silver/gold` is a Unity Catalog namespace, not
just a naming convention.

## Architecture

**Why Bronze/Silver/Gold?**
Mainly three things this project actually exercised: reprocessing from raw
without re-touching the source (the Silver cleaning rules changed more
than once while building this, and Bronze meant never needing to re-read
the original parquet); blast-radius isolation (a bug in a Gold aggregation
is fixed by rebuilding Gold from Silver in seconds, not by re-running
cleaning); and different guarantees per layer, independently checked by
`04_data_quality.py`. Honest caveat: at one month of data none of this pays
for itself yet — it's justified by what happens as the data and the
cleaning logic keep changing over time, not by today's row counts.

**How would you handle late-arriving data?**
A watermark. The Kafka consumer uses `withWatermark("pickup_time",
watermark_delay)` to bound how long it waits for a late event before
treating that point in time as final — events within the delay process
correctly, ones later than that get dropped rather than corrupting an
already-finalized result. The producer can actually generate late events
(`--late-rate`) to prove this, not just assert it works.

**How would you make the pipeline idempotent?**
Differently per layer, because each has a different failure mode. Bronze
has no checkpoint (it's a batch read), so it checks `source_file` against
what's already ingested before appending. Silver reprocesses all of Bronze
every run, so it uses `MERGE` instead of append to avoid duplicating on
re-runs. The streaming paths get idempotency for free from their
checkpoint. Gold is a full overwrite every run — trivially idempotent since
it's a pure function of Silver.

**How would you handle duplicate events?**
In Silver, `dropDuplicates` on the natural key. In the Kafka stream
specifically, `dropDuplicates(["trip_id"])` combined with the watermark,
since an unbounded stream needs a bounded window to know how long to
remember a `trip_id` before it's safe to forget it. The producer's
`--duplicate-rate` flag simulates Kafka's at-least-once delivery
redelivering an event, so the dedup logic gets actually exercised, not
just trusted.

**What happens if the pipeline fails halfway?**
Depends on the layer. A batch write to Bronze or Silver is one atomic
Delta transaction — a crash mid-write leaves the table exactly as it was
before the run, nothing half-applied. A streaming query resumes from its
last checkpoint instead of reprocessing or losing data.
`04_data_quality.py` is the other half of this: it raises on a failed
check instead of logging a warning, so a bad run fails visibly as a
task/job failure instead of silently producing wrong numbers downstream.

**How would you monitor it?**
Honestly, lightweight right now: every notebook prints row counts in/out,
`04_data_quality.py` produces a PASS/FAIL report per layer, and `DESCRIBE
HISTORY` gives a version-level audit trail for free via Delta's
transaction log. Not built: Databricks' Query History/warehouse metrics
and Lakehouse Monitoring (table-level drift/quality tracking) would be the
real next step — they're UI-configured, not something wired into this
repo.

## Real-time

**How would you process millions of events per minute?**
Nothing in this project has been built or tested at that scale — the
Kafka producer defaults to 5 events/second, and this path exists to
demonstrate correctness mechanics (watermarks, dedup, checkpointing), not
throughput. Getting to real volume is mostly changes upstream of the Spark
code: a Kafka topic with enough partitions to parallelize consumption
(keyed on something that doesn't skew the way `pickup_zone` would), a
trigger interval tuned for the latency/overhead trade-off at that volume,
and cluster sizing for the sustained rate.

**Would you use Kafka?**
For a genuinely live, continuously-arriving event feed — yes, which is why
it's Phase 3 here. For this project's actual data source (a monthly TLC
file dump) — no, which is why Phase 1/2 exist first: Auto Loader over
files already gets incremental, checkpointed ingestion without needing a
message broker. Kafka earns its complexity when the source is genuinely a
live stream, not a file that happens to update periodically.

**How would you handle out-of-order events?**
Same mechanism as late data — a watermark bounds how long the pipeline
waits for an event with an earlier timestamp before treating that point in
time as final.

**How would you manage checkpoints?**
A distinct `checkpointLocation` per streaming query, stored in a Volume
(`ridepulse.landing.checkpoints`) separate from the data itself. Each
checkpoint belongs to one specific query's source+sink pairing — you don't
share one across different streams, and deleting it forces a full
reprocess from the beginning.

**How would you handle schema changes?**
`cloudFiles.schemaEvolutionMode = "addNewColumns"` — the stream fails
loudly on the batch that first sees a new column rather than silently
dropping it, and resuming from the same checkpoint picks up with the new
column included. Set explicitly rather than left as whatever the default
happens to be.
