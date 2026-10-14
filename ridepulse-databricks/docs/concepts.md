# Concepts

Everything below is something this project actually does, not a general
glossary — each entry says where to look in the repo to see it running.
Read it alongside the code; it won't make much sense on its own.

## PySpark

**Joins.** `add_zone_names()` in `notebooks/transformations.py` does two
left joins — trips to the zone lookup, once on pickup location and once on
dropoff. Left, not inner, on purpose: a trip with a location ID that's
missing from the lookup table should still show up in Silver (with a NULL
zone name) rather than silently disappear. An inner join would have made
that data loss invisible.

**Broadcast joins.** Same function: the zone lookup is ~265 rows, so it gets
wrapped in `broadcast()` before the join. Spark ships that whole table to
every executor instead of shuffling the (much bigger) trips DataFrame
across the cluster to line up matching keys. Below
`spark.sql.autoBroadcastJoinThreshold` (30MB by default) Spark would
probably choose this plan on its own — being explicit just means it's not
guessing, especially since this table gets joined against twice in the same
function.

**Window functions.** Two different uses:
- `03_gold_aggregations.py` ranks each zone's revenue against other zones
  *on the same day* — `Window.partitionBy("pickup_date").orderBy(F.desc("total_revenue"))`
  with `F.rank()`. A window function doesn't collapse rows the way
  `groupBy` does; every input row keeps its place, it just gets a rank
  number attached.
- `06_simulate_batches.py` uses `Window.orderBy("pickup_datetime")` with
  `F.row_number()` to assign each trip a position in chronological order,
  which is how batches get carved out in pickup-time order.

**groupBy and shuffles.** Every aggregation in `03_gold_aggregations.py` is
a `groupBy(...).agg(...)`, and every one of those is a shuffle: Spark has to
physically move rows so that rows sharing a grouping key end up on the same
executor before it can count or average them. That's the expensive part of
an aggregation, not the counting itself. Worth being precise about what
this project actually does about that cost, since "avoided groupBy" would
be an overclaim — Gold's whole job *is* aggregation, so the `groupBy` calls
themselves aren't optional. What's actually avoided is a *redundant
second* one: `gold_zone_revenue`'s `revenue_rank` uses a window function
over the already-grouped result instead of grouping again and joining
that back (see Window functions above) — one shuffle instead of two for
that column. That's the honest scope of "avoiding expensive groupBy" here:
not fewer aggregations, fewer redundant ones.

**Skew.** HVFHV trip volume is heavily concentrated in Manhattan zones, so
grouping by `pickup_zone` doesn't split work evenly — some shuffle
partitions get way more rows than others, and the slowest partition sets
the pace for the whole stage. Adaptive Query Execution (on by default in
Databricks Runtime; check with
`spark.conf.get("spark.sql.adaptive.enabled")`) detects this at runtime and
splits oversized partitions automatically. Without AQE, the manual fix is
salting: append a random suffix to the skewed key, group by the salted key,
then aggregate the partial results a second time.

**Repartition vs coalesce.** `02_silver_transformations.py` calls
`.repartition("pickup_date")` right before writing a table partitioned by
that same column — a full shuffle that groups rows by date so each output
partition gets its own clean file instead of every task scattering a
handful of rows into every date's directory. `coalesce()` is the cheaper,
narrower tool: no shuffle, only reduces partition count, can't reorganize
rows by key. Use `coalesce` to cut down a large number of small partitions
after a filter; use `repartition` when you actually need rows grouped by a
specific key, like right before a partitioned write.

**Caching.** `06_simulate_batches.py` calls `.cache()` on the DataFrame it
then reads from in a loop, once per batch. DataFrames are lazy — without
caching, every `.filter(batch_id == n).toPandas()` in that loop would redo
the full read, sort, and row-numbering from scratch. Caching after the
expensive shared work and before the repeated reads is the pattern; caching
something you only touch once just burns memory for nothing.

**UDF vs built-in functions.** None of the transformation code uses a
Python UDF — `to_date`, `hour`, `dayofweek`, `unix_timestamp` in
`transformations.py` are all Spark built-ins that run inside the JVM as
part of the query plan Catalyst optimizes. A Python UDF is a black box to
Catalyst: it can't push filters through it, can't vectorize it without a
pandas UDF, and has to serialize every row out to a Python process and
back. Reach for a UDF when the logic genuinely can't be expressed with
built-ins — not by default.

## Delta Lake

**Why Delta instead of plain Parquet.** Every table in this project is
Delta, not raw Parquet, and it's worth being explicit about why, since
Parquet is the file format Delta is built on top of — it's not a
replacement, it's Parquet plus a transaction log (`_delta_log/`) that
tracks which files make up which version of the table. That log is what
plain Parquet doesn't have, and everything below in this section is a
consequence of it existing:
- **MERGE** — plain Parquet has no concept of "update this row in place";
  you'd have to rewrite whole files yourself. Delta's log makes an atomic
  upsert possible at all (`02_silver_transformations.py`).
- **Time travel** — Parquet files just sit there; nothing records what the
  table looked like an hour ago unless you kept old files around yourself
  and tracked which ones matched which point in time.
- **ACID writes** (next entry) — a failed Parquet write can leave partial
  files in place with nothing to tell a reader they're incomplete. Delta's
  log means a reader only ever sees a fully-committed version.
- **Schema evolution tracking** — Auto Loader's `cloudFiles.schemaLocation`
  (`05_streaming_ingestion.py`) builds on the same idea: a durable record
  of what the schema was and how it changed, not just "whatever columns
  happen to be in today's files."
Plain Parquet would work for this project if none of that mattered — a
single write-once, read-only table has no need for any of it. It stops
working the moment you need to update rows, recover from a partial write,
or reprocess history, which is most of what Silver and Gold actually do
here.

**ACID transactions.** Every write to a Delta table — the `MERGE` in
`02_silver_transformations.py`, the `overwrite` writes in
`03_gold_aggregations.py` — either fully commits as one new table version or
doesn't happen at all. That's enforced by the transaction log
(`_delta_log/`) sitting next to the data files. It's what makes it safe to
re-run a failed job: there's no such thing as a half-applied write to clean
up.

**MERGE.** `02_silver_transformations.py` upserts into `silver.trips`
instead of overwriting it:
`whenMatchedUpdateAll().whenNotMatchedInsertAll()` keyed on the same
natural key (`KEY_COLUMNS` in `transformations.py`) used for dedup during
cleaning. The match condition uses `<=>` (null-safe equals) instead of `=`
— with plain `=`, `NULL = NULL` is unknown rather than true, so a row with
a NULL in a key column would never match an existing row and MERGE would
insert a duplicate instead of updating it.

**Time travel.** `sql/maintenance.sql` has the query forms —
`VERSION AS OF` / `TIMESTAMP AS OF`. This works because Delta doesn't
delete old files immediately; a given table version is just a manifest
pointing at a subset of files in the transaction log. `DESCRIBE HISTORY`
(also in `maintenance.sql`) lists every version and what operation produced
it.

**OPTIMIZE.** Compacts small files into larger ones. `sql/maintenance.sql`
runs it against Bronze and Silver, both of which accumulate small files
over many `MERGE`/append runs. For a `CLUSTER BY` table (the Gold tables),
`OPTIMIZE` also reorganizes data around the clustering keys — one command
does both jobs.

**Schema evolution.** `05_streaming_ingestion.py` sets
`cloudFiles.schemaEvolutionMode = "addNewColumns"` explicitly. If TLC adds
a column to HVFHV mid-project, this stream stops itself on the batch that
first sees it instead of quietly dropping the new field — you restart the
same query from the same checkpoint and it picks up with the wider schema.

**Partitioning.** `silver.trips` is partitioned by `pickup_date`
(`02_silver_transformations.py`). At the row counts this project deals
with, the benefit is partition pruning: a query filtered to one week only
reads that week's files. Partitioning by a high-cardinality column, or one
with too few distinct values, both backfire — too many tiny partition
directories in the first case, no pruning benefit in the second.

**Liquid clustering.** The Gold tables use `CLUSTER BY` instead of
`partitionBy` (`write_gold()` in `03_gold_aggregations.py`). They're small —
a few hundred to a few thousand rows — with no column that has the right
cardinality for Hive-style partitioning. Liquid clustering keeps data
organized around the clustering keys as you write more into the table,
without the manual `ZORDER BY` maintenance that would previously have been
needed on top of `OPTIMIZE`.

## Structured Streaming

**Batch vs. streaming, in general.** Batch means a fixed, complete pile of
data — you read all of it (or a defined chunk), process it, and the job
stops. Beginning and end. There's no built-in awareness of "what's new
since last time" unless you write that yourself. Streaming means the data
has no defined endpoint — new records keep arriving (files landing,
messages on a queue) — so instead of running once against a fixed pile,
the job stays running or wakes on an interval and processes only what's
new since it last checked. The mechanical difference that makes this
possible is the checkpoint (below): streaming tracks exactly what it's
already processed, so it never re-reads old data and never needs to be
told "just the new stuff" — batch has no equivalent unless you build one.

Three examples in this repo, same underlying idea, three different
answers to "does this have a checkpoint":
- `01_bronze_ingestion.py` is pure batch — reads one file, once, no
  checkpoint. That's exactly why it needs the manual `source_file` check
  (Architecture → idempotency below): without a checkpoint, nothing
  remembers what it already ingested.
- `05_streaming_ingestion.py` is streaming via Auto Loader, but runnable
  two ways: `trigger(availableNow=True)` catches up on everything sitting
  in `source_path` right now and then stops (a one-shot catch-up you can
  schedule, keeping the checkpoint's safety without running forever), or
  `trigger(processingTime="30 seconds")` stays running indefinitely.
- `07_kafka_streaming_ingestion.py` is streaming with no `availableNow`
  option that makes sense — Kafka is a genuinely continuous flow with no
  "everything sitting there right now" to catch up on.

Worth knowing: Structured Streaming is technically implemented as a series
of small batches under the hood ("micro-batching") — the trigger interval
is literally "how often do I run one tiny batch." The batch/streaming line
is really about checkpointing and incrementality, not "streaming handles
one record at a time and batch doesn't."

**Checkpoints.** Both streaming notebooks (`05`, `07`) write to a
`checkpointLocation`. It tracks which Kafka offsets / which files have
already been processed and committed. Kill either query mid-run and
restart it — it resumes from the last committed checkpoint instead of
reprocessing or dropping anything. That checkpoint is also what makes the
Auto Loader path idempotent without the manual "have I seen this file"
check that the batch Bronze notebook needs (see Architecture → idempotency
below).

**Watermarks.** `07_kafka_streaming_ingestion.py` calls
`withWatermark("pickup_time", watermark_delay)`. It bounds how long Spark
waits for a late event before deciding a given point in event time is
"done." `05_streaming_ingestion.py` deliberately has no watermark — it's a
pass-through ingestion stream with no windowed aggregation, so there's
nothing for a watermark to bound.

**Late data.** In the Kafka path, an event's `pickup_time` (when the ride
happened) can lag behind when it's actually processed. `kafka/ride_producer.py`
can simulate this on purpose with `--late-rate` / `--late-minutes` — with a
10-minute consumer watermark and `--late-minutes 20`, those events land
outside the watermark and get dropped rather than processed, which you can
go watch happen in `ridepulse.bronze.ride_events`.

**Duplicate events.** Kafka's at-least-once delivery means the same event
can arrive twice (producer retry, consumer rebalance).
`kafka/ride_producer.py --duplicate-rate` simulates that; the consumer
handles it with `dropDuplicates(["trip_id"])` in `07_kafka_streaming_ingestion.py`.

**Exactly-once processing.** Not one setting — it's `dropDuplicates` (drops
repeats on the read side) plus a checkpointed write to an idempotent sink
(Delta, on the write side) working together. Read-side dedup without a
reliable, checkpointed write would still let a crash-and-retry duplicate
data; a reliable write without dedup would still double-count a
Kafka-level retry.

**Trigger intervals.** `07_kafka_streaming_ingestion.py` uses
`trigger(processingTime="10 seconds")` — wake up, check for new records,
process a micro-batch, every 10 seconds. `05_streaming_ingestion.py`
defaults to `trigger(availableNow=True)` instead — process whatever's
there right now and stop, which is the better fit for "run this
periodically as a job" rather than "keep a query running continuously."

**Scaling to high-throughput event streams.** Worth being direct about
this: nothing in this project has been built or tested for anything close
to millions of events per minute. `kafka/ride_producer.py` defaults to 5
events/second, and the whole Kafka path exists to demonstrate the
mechanics (watermarks, dedup, checkpointing), not to prove out throughput.
If this needed to handle real high-volume traffic, the changes wouldn't be
in the Spark code at all — they'd be upstream of it:
- **Kafka topic partitioning.** A single-partition topic caps throughput at
  whatever one consumer can process; the topic would need enough
  partitions that Spark can consume it in parallel, partitioned by a key
  that spreads load evenly (not `pickup_zone` — see Skew above, the same
  imbalance that skews a `groupBy` would skew partition assignment too).
- **Consumer parallelism** — `spark.readStream.format("kafka")` scales
  automatically with the number of Kafka partitions and executors; the
  ceiling is set by the topic's partition count, not by anything in
  `07_kafka_streaming_ingestion.py` itself.
- **Trigger interval trade-off** — `processingTime="10 seconds"` batches
  10 seconds of events per micro-batch. At real volume, a shorter interval
  processes smaller, more frequent batches (lower latency, more overhead);
  a longer one does the opposite. Neither is free.
- **Cluster sizing** — the actual compute doing the work, sized to the
  sustained event rate, not something the pipeline code controls.
None of this is implemented here — the codebase demonstrates the
correctness patterns (exactly-once, late data, schema evolution) that
still matter at any scale, but the scale itself is a capacity-planning
problem this project doesn't take on.

## Databricks

**Unity Catalog.** The `catalog.schema.table` three-level namespace behind
`ridepulse.bronze.trips` etc. is Unity Catalog, not Delta itself — it's
what adds access control, lineage, and audit logging on top of the tables.
`01_bronze_ingestion.py` has a note on what to do if your workspace doesn't
let you create a new catalog.

**Auto Loader.** `05_streaming_ingestion.py`. `cloudFiles` incrementally
discovers new files in `source_path` — either by listing the directory or,
on cloud storage, via file notifications — without you tracking what's
already been read; that bookkeeping lives in the checkpoint.

**Jobs vs. pipelines, in general.** Worth separating before the
Databricks-specific names below. A **Job** orchestrates *steps*, and the
steps can be anything — run a notebook, run SQL, train a model, call a
script, send an alert, trigger a pipeline. The DAG is at the task level:
"run A, then B and C in parallel, then D." A Job doesn't know what's inside
each step; it just handles sequencing, retries, scheduling, and alerting
across whatever heterogeneous work you give it. A **pipeline** (Lakeflow
Declarative Pipelines here, but the same idea applies to dbt, Airflow's
data-aware scheduling, etc.) is narrower: you declare *datasets* and how
each is derived from the others, and the engine resolves the DAG *between
tables*, not steps you sequence by hand — plus takes over incremental
processing, checkpointing, and data-quality enforcement that you'd
otherwise write yourself. Rule of thumb: reach for a pipeline when the work
*is* moving data through transformation layers (that's its whole job);
reach for a Job when you need to coordinate things across systems or kinds
of work, including triggering a pipeline as one piece of something bigger.
They're not competitors — a Job is often the thing that *calls* a pipeline.
That's exactly what `lakeflow_pipeline_refresh` is in `resources/jobs.yml`:
the Job is the scheduler/coordinator, the Pipeline is the thing being
coordinated.

**Lakeflow.** Databricks' current umbrella term for its data engineering
stack: Lakeflow Connect (ingestion), Lakeflow Pipelines (the evolution of
Delta Live Tables, a declarative `@dlt.table` API for streaming/batch ETL),
and Lakeflow Jobs (orchestration, née Workflows). For new streaming ETL,
Databricks now generally points people at Lakeflow Pipelines rather than
hand-written `readStream`/`writeStream`. The notebooks in this repo use the
raw Auto Loader/Structured Streaming APIs on purpose (see the note at the
top of `05_streaming_ingestion.py`) — the goal there is to understand the
mechanics Lakeflow Pipelines would otherwise hide behind a decorator.

`pipelines/lakeflow_etl.py` is the other half of that comparison: the same
Bronze/Silver/Gold logic, written declaratively, deployed by
`resources/pipelines.yml` as `ridepulse_lakeflow_pipeline` into a separate
`ridepulse.lakeflow_demo` schema. It uses `pyspark.pipelines` (`dp`), the
newer Spark-native API, rather than the classic `import dlt` module — see
that file's docstring for the fallback if your runtime doesn't have it yet.
Reading it next to `notebooks/01-03` makes the trade-off concrete rather
than abstract:
- Bronze's idempotency comes from the pipeline's own checkpoint, same as
  `05`, instead of the manual `source_file` check `01` needs.
- `02_silver_transformations.py`'s four `.filter()` calls in `clean_trips()`
  become four `@dp.expect_or_drop` decorators — same rules, but declared
  as constraints the pipeline reports pass/fail metrics on (Data
  Engineering → Pipelines → the data quality tab), not lines of imperative
  code you have to read to know what's enforced.
- The hand-written `MERGE INTO` in `02` (see Delta Lake → MERGE above)
  isn't needed at all — Silver and every Gold table are declared as
  `@dp.materialized_view`, explicitly (not inferred from the query the way
  classic `dlt` does it), and the pipeline engine decides
  incremental-vs-full-refresh itself instead of you writing either path by
  hand. Bronze, by contrast, is `@dp.table` — a streaming table, since it's
  genuinely append-only.
- `enrich_trips()` and `add_zone_names()` are imported from
  `transformations.py` unchanged in both — proof the two implementations
  aren't secretly doing different transformation logic, only different
  orchestration.

**Batch ETL vs. streaming Job vs. Lakeflow Pipeline, side by side.** This
project actually implements all three ways of moving the same HVFHV data
into Bronze, so it's worth comparing them directly instead of only in the
abstract:

- **Batch ETL** (`01` → `02` → `03` → `04`, as the `ridepulse_batch_etl`
  Job). You tell it "go read this file, right now," it processes
  everything in one pass, and then it's done — like manually refreshing a
  spreadsheet. `01_bronze_ingestion.py` does one `spark.read.parquet(...)`
  of a file that already exists; nothing happens again until something
  re-triggers it. *Benefits:* simple to reason about, easy to re-run and
  get the same result, nothing running in the background between runs.
  *Tradeoffs:* not reactive — new data sits unprocessed until the next
  trigger — and you own the "have I already processed this" bookkeeping
  yourself (the manual `source_file` check in `01`).
- **Streaming Job** (`06` → `05`, as the `ridepulse_streaming_demo` Job).
  Instead of "read this file once," it's "watch this folder, and react
  every time something new lands" — like a guard watching a door instead
  of checking it once a day. `05_streaming_ingestion.py` uses Auto Loader
  to watch a directory, with a checkpoint remembering what it's already
  seen so a restart resumes instead of reprocessing. *Benefits:* reactive,
  automatic failure recovery via the checkpoint, no hand-written
  "have I seen this" logic. *Tradeoffs:* more moving parts to manage
  (checkpoint location, schema location, a query that keeps running in
  `continuous` mode), and you're still writing the read/write mechanics by
  hand — same imperative Python either way, just triggered differently.
- **Lakeflow Pipeline** (`pipelines/lakeflow_etl.py`, as
  `ridepulse_lakeflow_pipeline`). Instead of writing the *steps* ("read,
  then filter, then write"), you declare the *end state* — "this table
  should contain the result of this query" — for every table, and a
  separate engine figures out how to keep them all current, in what order,
  incrementally or fully, on its own. *Benefits:* the engine owns
  dependency ordering, retries, and incremental-vs-full-refresh decisions;
  data quality is part of the table definition (`@dp.expect_or_drop`)
  instead of a script that checks afterward like `04_data_quality.py`
  does; noticeably less code, since there's no hand-written `MERGE` or
  checkpoint plumbing. *Tradeoffs:* less direct control — you're trusting
  the engine's judgment on *how* to refresh rather than writing that
  decision yourself — and it's a newer, faster-moving part of Databricks
  (see the uncertainty flagged at the top of `resources/pipelines.yml`).

One-line version: Batch ETL = *you pull, on demand, all at once.*
Streaming Job = *it watches and reacts, but you wrote the reactions by
hand.* Lakeflow Pipeline = *you declare the destination, the engine writes
and runs the reactions for you.*

**Workflows (Lakeflow Jobs).** `resources/jobs.yml` defines two of these as
bundle resources (`ridepulse_batch_etl`, `ridepulse_streaming_demo`) rather
than clicking through the UI — see `docs/asset_bundle.md`. `ridepulse_batch_etl`
mixes task types in one DAG: `01 → 02 → 03 → 04` (notebook tasks, `04`
gating the run by raising on a failed check) plus `lakeflow_pipeline_refresh`,
a `pipeline_task` that triggers the Lakeflow Pipeline above with no
dependency on the notebook chain — it reads the same landing Volume
directly, so it runs concurrently rather than waiting. The whole job has a
daily `schedule:`, deployed paused on purpose (see `docs/asset_bundle.md` →
"Automation" for why running both implementations together is a
comparison-freshness choice, not something to imitate in production).

**SQL Warehouse.** The compute the `sql/*.sql` files are meant to run
against — serverless SQL compute, separate from the all-purpose/job compute
the notebooks use, sized for interactive queries and dashboards. Free
Edition provisions one by default.

**Monitoring.** What this project has: the print-based row counts in every
notebook, the PASS/FAIL report `04_data_quality.py` produces, and
`DESCRIBE HISTORY` for table-level audit. What Databricks offers beyond
that: Query History and warehouse metrics in the workspace UI, and
Lakehouse Monitoring — Unity Catalog table monitors that track data drift
and quality over time without you writing the checks by hand. That's a
natural next step past what `04_data_quality.py` does today.

## Architecture

**Why Bronze/Silver/Gold instead of one table.** The medallion split isn't
free — it's three tables and three (or five, counting the streaming/Kafka
variants) jobs to maintain instead of one. It earns that cost on a few
specific axes this project actually exercises, not as a rule to follow
blindly:
- **Reprocessing from raw.** `02_silver_transformations.py`'s cleaning
  rules changed more than once while this repo was being built — the
  duration cutoff, the dedup key, the zone join. Every time, Silver could
  be rebuilt from Bronze without re-touching the source parquet, because
  Bronze kept an untouched copy. If Bronze had already been cleaned on the
  way in, a change to the cleaning logic would mean re-reading the
  original files (or, on Free Edition, they might not even be re-fetchable
  — see the README on outbound internet being blocked).
- **Blast radius.** A bug in a Gold aggregation (say, the `revenue_rank`
  window logic) can be fixed and Gold rebuilt from Silver in seconds,
  without touching Bronze or re-running cleaning. A bug in cleaning is
  contained to Silver and Gold, without corrupting the raw record. One
  flat table would mean one bug potentially requiring a full rebuild from
  source.
- **Different consumers, different contracts.** `04_data_quality.py`
  checks Bronze/Silver/Gold with different rules because they're supposed
  to guarantee different things — Bronze guarantees nothing but "this row
  came from the source file," Silver guarantees "this row is clean,"
  Gold guarantees "this number is a correct aggregate of Silver." Collapsing
  them into one table would collapse those guarantees into one, harder to
  express as separate checks.
- **Cost of getting it wrong isn't uniform.** Bronze is append-only and
  cheap to keep forever (it's raw file copies). Gold is small and cheap to
  fully recompute on every run (see `03_gold_aggregations.py`'s own
  comment on why it doesn't bother with incremental writes). Treating all
  three the same way — same write strategy, same recompute cost — would
  mean either over-engineering Gold (it doesn't need MERGE) or
  under-engineering Silver (a full overwrite there gets expensive as the
  data grows, which is why `02` uses MERGE instead).

The honest counterpoint, if asked: at one month of data, none of this pays
for itself yet. The split is justified by what happens as this scales to a
year of data and a changing set of cleaning rules, not by today's row
counts.

**Idempotency.** Handled two different ways on purpose, because the two
notebooks have different failure modes:
- `01_bronze_ingestion.py` has no checkpoint (it's a plain batch read), so
  it checks `source_file` against what's already in the table before
  appending — re-running it against the same file is a no-op.
- `02_silver_transformations.py` reprocesses all of Bronze every run, so a
  plain overwrite would technically also be idempotent — but `MERGE` is
  used instead because it's the pattern that still works once you stop
  reprocessing everything and start filtering Bronze to just new rows.

**Failure recovery.** Streaming checkpoints (`05`, `07`) resume after a
crash without reprocessing or dropping data. `MERGE`'s atomicity (`02`)
means a job that dies mid-write leaves the table exactly as it was before
the run, not half-updated. Auto Loader's checkpoint also protects against
transient failures in the underlying file listing.

**Scalability.** Broadcasting the zone lookup avoids shuffling the large
side of a join. Partitioning Silver by date and clustering Gold tables both
mean queries don't have to scan data they don't need. AQE handles the
skewed zone distribution without manual salting. None of this matters at
one month of data — the point is the pattern still holds at twelve months.

**Data quality.** `04_data_quality.py` runs checks across all three
layers — row counts, NULL checks, duplicate detection, fare/distance/duration
bounds, and Gold-vs-Silver reconciliation — and raises if anything fails,
so it can gate a Workflow rather than just print a warning nobody reads.

**Observability.** Every notebook prints what it did (rows in, rows out,
rows dropped) rather than running silently. Combined with `DESCRIBE
HISTORY` for the "what changed and when" story and Query History in the
workspace UI for the "how long did it take and did it fail" story, that
covers the basics without needing an external monitoring stack for a
project this size.
