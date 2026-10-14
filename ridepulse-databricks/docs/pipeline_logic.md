# Pipeline logic reference

What each file actually does, in order — not why (that's `docs/concepts.md`),
not how to run it (that's `docs/execution_guide.md`), just: read top to
bottom, here's the sequence of operations. Useful when you want to know
"does Silver drop this row or not" without re-reading the source.

## At a glance

| File | Reads | Writes | Role |
|---|---|---|---|
| `01_bronze_ingestion.py` | `source_path` (parquet in the landing Volume) | `ridepulse.bronze.trips` (append) | Land raw data, untouched, plus two metadata columns |
| `transformations.py` | — (a library, not a notebook) | — | Shared cleaning/enrichment/join functions used by `02` and by the tests |
| `02_silver_transformations.py` | `ridepulse.bronze.trips`, taxi zone lookup CSV | `ridepulse.silver.trips` (MERGE) | Clean, deduplicate, enrich, resolve zone names |
| `03_gold_aggregations.py` | `ridepulse.silver.trips` | `ridepulse.gold.hourly_demand` / `zone_revenue` / `trip_kpis` / `peak_demand` (overwrite) | Business aggregates the dashboard queries run against |
| `04_data_quality.py` | Bronze, Silver, all four Gold tables | Nothing (a report + raises on failure) | Gate: verify the above actually did what it claims |
| `05_streaming_ingestion.py` | A directory of parquet files (Auto Loader watches it) | `ridepulse.bronze.trips_stream` (streaming append) | Same job as `01`, but incremental — only processes files it hasn't seen |
| `06_simulate_batches.py` | One full month's parquet file | Small `batch_NNN.parquet` files, written one at a time with a pause between | Not ingestion — generates the trickle of files `05` needs to have something to react to |
| `07_kafka_streaming_ingestion.py` | The `ride-events` Kafka topic | `ridepulse.bronze.ride_events` (streaming append) | Consumes live ride events, deduplicates them, handles ones that arrive late |
| `kafka/ride_producer.py` | One full month's parquet file | Messages published to the `ride-events` Kafka topic | Not part of Databricks at all — a standalone script that pretends to be a live ride-hailing backend |

---

## `01_bronze_ingestion.py`

**In:** `source_path` widget, default `/Volumes/ridepulse/landing/raw/hvfhv/fhvhv_tripdata_2026-01.parquet`.
**Out:** `ridepulse.bronze.trips`.

1. Read the `catalog` and `source_path` widgets.
2. Create the catalog and all five schemas if they don't exist yet
   (`landing`, `bronze`, `silver`, `gold`, `lakeflow_demo`), plus the two
   Volumes under `landing` (`raw`, `checkpoints`). Runs every time; `IF NOT
   EXISTS` makes it a no-op after the first run.
3. `spark.read.parquet(source_path)` — the full HVFHV schema, no column
   selection, no filtering.
4. Add two columns: `ingestion_timestamp` (`current_timestamp()`, when this
   run happened) and `source_file` (`col("_metadata.file_path")`, which
   physical file each row came from — the older `input_file_name()`
   function is blocked under Unity Catalog, so this uses Spark's built-in
   `_metadata` struct column instead).
5. **Idempotency check**: if `bronze.trips` already exists, collect the
   distinct `source_file` values already in it, and filter the new data
   down to rows whose `source_file` *isn't* in that list. On a fresh table,
   everything is "new."
6. If there's at least one new row, append it (`mode("append")`). If not,
   skip the write and say so.
7. Print the total row count and show 10 sample rows.

Nothing here drops, renames, or recomputes anything — that's the point of
Bronze. The only "logic" is steps 4 (tagging) and 5 (the idempotency
filter).

---

## `transformations.py`

Not a notebook — a plain module, imported by `02_silver_transformations.py`
and by `tests/test_transformations.py`. Three functions plus one constant.

**`KEY_COLUMNS`** = `hvfhs_license_num, dispatching_base_num,
pickup_datetime, dropoff_datetime, PULocationID, DOLocationID`. HVFHV has
no trip ID, so this combination stands in for one. Reused in three places:
dedup here, the `MERGE` key in `02`, and the duplicate check in `04` — one
definition, three consumers, so they can't drift out of sync with each
other.

**`clean_trips(df)`** — drops rows, in this order:
1. `dropna` on `pickup_datetime`, `dropoff_datetime`, `PULocationID`, `DOLocationID` — any NULL in these, the row's gone.
2. `base_passenger_fare >= 0`
3. `trip_miles > 0`
4. `dropoff_datetime > pickup_datetime`
5. `dropDuplicates(KEY_COLUMNS)`

**`enrich_trips(df, max_trip_duration_minutes=180)`** — adds columns, then
filters on one of them:
1. `pickup_date` = `to_date(pickup_datetime)`
2. `pickup_hour` = `hour(pickup_datetime)`
3. `day_of_week` = `dayofweek(pickup_datetime)`
4. `trip_duration_minutes` = `(unix_timestamp(dropoff) - unix_timestamp(pickup)) / 60`, rounded to 2 decimals
5. Filter: `0 < trip_duration_minutes <= max_trip_duration_minutes` (default 180)
6. `average_speed` = `trip_miles / (trip_duration_minutes / 60)`, rounded to 2 decimals

**`add_zone_names(df, zone_lookup)`**:
1. `broadcast()` the zone lookup (just `LocationID`, `Zone` columns).
2. Left join on `PULocationID == LocationID`, rename the joined `Zone` to `pickup_zone`, drop the extra `LocationID`.
3. Left join again on `DOLocationID == LocationID`, rename to `dropoff_zone`, drop `LocationID` again.

`clean_trips` is *not* used by `pipelines/lakeflow_etl.py` — see that
file's docstring for why (its four filters get re-expressed as `@dp.expect_or_drop`
constraints there instead). `enrich_trips` and `add_zone_names` are used
unchanged by both.

---

## `02_silver_transformations.py`

**In:** `ridepulse.bronze.trips`, the taxi zone lookup CSV.
**Out:** `ridepulse.silver.trips`.

1. Read widgets: `catalog`, `zone_lookup_path`, `max_trip_duration_minutes`.
2. Read the full Bronze table, count it.
3. `clean_trips(bronze)` → `enrich_trips(cleaned, max_trip_duration_minutes)` → `add_zone_names(..., zone_lookup)`, in that order — this is the entire transformation, just calling the three functions above.
4. `repartition("pickup_date")` on the result, to line up rows by date before a partitioned write.
5. If `silver.trips` doesn't exist yet: plain write, `partitionBy("pickup_date")`.
6. If it does exist: `MERGE INTO` via the Delta API — match on all of `KEY_COLUMNS` using null-safe equals (`<=>`), `whenMatchedUpdateAll()`, `whenNotMatchedInsertAll()`.
7. Print Bronze row count vs. Silver row count, show 10 sample rows.

Every run reprocesses *all* of Bronze (not just new rows) — the `MERGE`
makes that idempotent, not incremental. See the notebook's own comments and
`docs/concepts.md` → MERGE for the reasoning.

---

## `03_gold_aggregations.py`

**In:** `ridepulse.silver.trips`.
**Out:** `ridepulse.gold.hourly_demand`, `zone_revenue`, `trip_kpis`, `peak_demand`.

1. Read the `catalog` widget, read Silver.
2. Add `total_revenue_per_trip` = `base_passenger_fare + tolls + bcf + sales_tax + congestion_surcharge + airport_fee` to the Silver DataFrame (used by two of the four tables below).
3. A `write_gold(df, table_name, cluster_by)` helper: overwrite the table (`mode("overwrite")`, `overwriteSchema=true`), then run `ALTER TABLE ... CLUSTER BY (...)` to (re)apply liquid clustering. Every table below goes through this.
4. **`hourly_demand`** — `groupBy(pickup_date, pickup_hour, pickup_zone)` → `trip_count` (count), `average_distance` (avg `trip_miles`), `average_fare` (avg `base_passenger_fare`). Clustered by `(pickup_date, pickup_zone)`.
5. **`zone_revenue`** — `groupBy(pickup_date, pickup_zone)` → `trip_count`, `total_revenue` (sum), `average_fare`, `average_tip` (avg `tips`). Then a window function: `Window.partitionBy(pickup_date).orderBy(desc(total_revenue))`, `rank()` → `revenue_rank` (each zone's rank within its own day). Clustered by `(pickup_date, pickup_zone)`.
6. **`trip_kpis`** — `groupBy(pickup_date)` → `total_trips`, `total_revenue`, `average_fare`, `average_distance`, `average_duration` (avg `trip_duration_minutes`). `pickup_date` renamed to `date`. Clustered by `(date)`.
7. **`peak_demand`** — `groupBy(pickup_date, pickup_hour, pickup_zone)` → `trip_count`, columns renamed to `date`/`hour`/`zone`. `approxQuantile("trip_count", [0.25, 0.5, 0.75])` computes the three quartile cutoffs across *all* rows, then `demand_level` is assigned Low/Medium/High/Very High based on which quartile bucket each row's `trip_count` falls into. Clustered by `(date, zone)`.
8. Print row counts for all four tables, show `trip_kpis` ordered by date.

Every table here is a full recompute of Silver, every run — no MERGE, no
incremental logic. Deliberate: see the notebook's top comment for why that's
the right call for aggregates specifically.

---

## `04_data_quality.py`

**In:** `ridepulse.bronze.trips`, `ridepulse.silver.trips`, all four Gold tables.
**Out:** nothing written — a printed report, and an `AssertionError` if anything failed.

Every check calls the same `check(name, passed, detail)` helper, which
appends one row (`PASS`/`FAIL` + a detail string) to a `results` list.

1. **Row counts**: Bronze > 0, Silver > 0, Silver ≤ Bronze.
2. **NULL checks**: for each of `pickup_datetime`, `dropoff_datetime`, `PULocationID`, `DOLocationID` in Silver — zero NULLs expected.
3. **Duplicates**: `silver_count - silver.dropDuplicates(KEY_COLUMNS).count()` should be 0. Imports `KEY_COLUMNS` from `transformations.py` — the same key `02` merges on, so this check is directly verifying the thing `02` is supposed to guarantee.
4. **Bounds**: no negative `base_passenger_fare`, no `trip_miles <= 0`, `trip_duration_minutes` within `(0, max_trip_duration_minutes]`, `dropoff_datetime` always after `pickup_datetime`.
5. **Gold reconciliation**: `SUM(total_trips)` from `trip_kpis` and `SUM(trip_count)` from each of the other three Gold tables should all equal Silver's row count — verifying the aggregates in `03` account for every Silver row, none dropped or double-counted.
6. Build a small DataFrame from `results` and `display()` it, print `N/M checks passed`, and if anything failed: print each failure's name and detail, then `raise AssertionError` — which is what turns a bad run into a failed task in a Workflow/Job instead of a silently-ignored warning.

---

## `05_streaming_ingestion.py`

**In:** `source_path` widget, default `/Volumes/ridepulse/landing/raw/hvfhv_stream/` — note this is a *folder*, not one file, because this notebook watches it for new files rather than reading a fixed file once.
**Out:** `ridepulse.bronze.trips_stream`.

This does the same job as `01_bronze_ingestion.py` — land raw HVFHV data in
Bronze, tagged with metadata — but with a different mechanism called
**Auto Loader**, Databricks' tool for watching a folder and automatically
picking up files as they appear, instead of you telling it exactly which
file to read.

**`01` vs. `05`, side by side:**

| | `01` (batch) | `05` (Auto Loader) |
|---|---|---|
| How it reads | `spark.read.parquet(...)` — reads whatever's at `source_path` *right now*, once | `spark.readStream.format("cloudFiles")` — watches `source_path`, keeps picking up new files |
| How it avoids re-processing a file | Manual: filters out rows whose `source_file` is already in the Bronze table before appending | A **checkpoint** — Auto Loader's own saved memory of which files it's already read; nothing hand-written |
| When it runs | Only when something triggers it (a click, a scheduled Job task) | Either runs once and stops (`availableNow`) or keeps running and reacting (`continuous`) |
| Best fit | An infrequent, chunky arrival — "a new file shows up once a month" | A source that trickles files continuously and you want the table to stay caught up without re-triggering anything |
| Cost of the simplicity/reactivity trade-off | Simple, but not reactive — new files sit unprocessed until the next run | Reactive, but there's more to manage — a checkpoint location, a schema location, and (in `continuous` mode) a query that keeps running instead of finishing |

Neither is "better" in the abstract — `01` is the honest fit for this
project's actual source (a monthly TLC file dump), which is why it's the
primary Bronze path. `05` exists to demonstrate the mechanism you'd
actually reach for if the source genuinely trickled files in continuously,
with `06_simulate_batches.py` manufacturing that trickle so there's
something for it to react to.

1. Read widgets: `catalog`, `source_path` (the folder to watch),
   `checkpoint_path`, and `trigger_mode` (a dropdown — `availableNow` or
   `continuous`, explained in step 5).
2. `spark.readStream.format("cloudFiles")` — `cloudFiles` is the name of
   Auto Loader inside Spark. `.load(source_path)` points it at the folder.
   Two options matter here: `cloudFiles.schemaLocation` is a folder where
   Auto Loader writes down what columns/types it saw, so it doesn't have
   to re-guess every time it runs; `cloudFiles.schemaEvolutionMode =
   "addNewColumns"` means if a file shows up with an extra column nobody's
   seen before, the run stops with an error on purpose (rather than
   quietly ignoring the new column) — you'd restart it and it picks up
   with the new column included.
3. Same two metadata columns as `01`: `ingestion_timestamp`,
   `source_file`.
4. Write to `bronze.trips_stream` with `checkpointLocation` set. A
   **checkpoint** is Auto Loader's memory — a small amount of state it
   saves that records exactly which files it has already processed. This
   is the entire reason `05` doesn't need `01`'s manual "have I seen this
   file before" check: the checkpoint already knows.
5. `trigger_mode` decides how long this notebook keeps running:
   `availableNow` processes every file currently in `source_path` and then
   **stops** — good for "run this once a day and catch up on whatever
   showed up." `continuous` keeps the notebook running forever, checking
   for new files every 30 seconds (`processingTime="30 seconds"`) — good
   for actually watching it react to files in real time.
6. Print the row count, show the 10 most recently ingested rows.

Writes to a separate table (`trips_stream`, not `trips`) on purpose, so it
never collides with what `01` writes — they're two different
demonstrations of the same idea, not two things feeding the same table.

---

## `06_simulate_batches.py`

**In:** one full month's parquet file (the same one `01` reads).
**Out:** a folder full of small parquet files, `batch_000.parquet`,
`batch_001.parquet`, ... written one at a time with a pause in between.

This notebook doesn't ingest anything into a table at all — it's a
**data-prep script that manufactures the "files trickling in over time"
scenario `05` needs in order to have something to demonstrate.** Without
it, `05`'s `source_path` folder would just be empty. Think of it as a
stand-in for a real system that would be dropping new trip files into
storage continuously — since TLC only publishes one file a month, this is
how the project fakes "new data arriving" without pretending TLC itself is
a live feed.

1. Read widgets: `input_path` (the full month's file), `output_dir` (same
   folder `05` watches), `batch_size` (rows per small file, default 100),
   `num_batches` (how many small files to write — `0` means "all of
   them"), `sleep_seconds` (pause between writes, default 10).
2. Read the whole input file, sort every row by `pickup_datetime` (so
   trips get replayed in the order they actually happened), and number
   them: `batch_id = row_number / batch_size`, so the first 100 rows are
   batch 0, the next 100 are batch 1, and so on. `.cache()` here means
   "keep this in memory" — the loop below reads from this same data up to
   `num_batches` times, and without caching, Spark would redo the entire
   read-and-sort from scratch on every single one of those reads.
3. Loop over each batch number: filter down to just that batch's 100
   rows, convert to a pandas DataFrame (small enough — just 100 rows),
   write it out as one parquet file (`batch_000.parquet`, etc.), print a
   confirmation, then pause for `sleep_seconds` before moving to the next
   one (no pause after the very last batch).

Run this in one tab and `05` (with `trigger_mode = continuous`) in
another, and you can watch `05` pick up each file within seconds of `06`
writing it — that's the actual point of the exercise: proving the
incremental behavior happens, not just reading about it.

---

## `07_kafka_streaming_ingestion.py`

**In:** the `ride-events` Kafka topic (published to by
`kafka/ride_producer.py`, below).
**Out:** `ridepulse.bronze.ride_events`.

**Kafka** is a message queue — a system other applications can publish
small pieces of data ("events") to, and that other applications can read
from continuously. It's the tool of choice when data is genuinely
live and never-ending (like real ride requests coming into a real
ride-hailing app), as opposed to files that get dropped somewhere
periodically. This notebook is the Databricks side: it reads whatever
events are flowing through the topic.

1. Read widgets: `catalog`, `kafka_bootstrap_servers` (the address of the
   Kafka server), `kafka_topic` (which topic to read — `ride-events`),
   `checkpoint_path`, `watermark_delay` (explained in step 4).
2. Define the shape of one event as a schema (`trip_id`, `pickup_time`,
   `pickup_zone`, `dropoff_zone`, `distance`, `fare`) — Kafka messages
   arrive as raw text (JSON), so Spark needs to be told how to parse them
   into columns.
3. `spark.readStream.format("kafka")` connects to the topic;
   `from_json(...)` parses each message's text into the columns from step
   2, and `ingestion_timestamp` gets added, same idea as every other file
   in this project.
4. **Handle duplicates and late events** — two different problems:
   - A real event feed can deliver the same event twice (a producer
     retrying after a network hiccup). `dropDuplicates(["trip_id"])` drops
     repeats.
   - An event can also arrive *late* — its `pickup_time` says it happened
     a while ago, even though Spark is only seeing it now.
     `withWatermark("pickup_time", watermark_delay)` tells Spark how long
     to keep waiting for late events before giving up on them (default 10
     minutes) — this is also what lets Spark safely forget old `trip_id`s
     instead of remembering every single one forever, which it would
     otherwise have to do to catch duplicates on a never-ending stream.
5. Write to `bronze.ride_events` with a checkpoint (same idea as `05`) and
   `trigger(processingTime="10 seconds")` — check Kafka for new messages
   and process them every 10 seconds, running continuously (there's no
   `availableNow` option here, because Kafka doesn't really have a
   "everything that's there right now" — it's just a continuous flow).

Won't run on Databricks Free Edition unless your Kafka broker happens to
be reachable from the workspace — see the README for why.

---

## `kafka/ride_producer.py`

Not a Databricks notebook — a plain Python script meant to run on your own
computer, standing in for "the backend of a real ride-hailing app" that
would normally be sending live ride events to Kafka. `07` above is the
thing on the other end, reading what this script sends.

**In:** the same one month's parquet file, plus optionally the taxi zone
lookup CSV.
**Out:** JSON messages published to the `ride-events` Kafka topic.

1. Load the trip data, sorted by `pickup_datetime` (so events get sent out
   in the order the rides actually happened), and make up a `trip_id` for
   each row since HVFHV doesn't have one.
2. For each trip, build a small JSON event: `trip_id`, `pickup_time`,
   `pickup_zone`, `dropoff_zone`, `distance`, `fare`.
3. Two command-line flags exist specifically to give `07`'s duplicate- and
   late-event-handling code something real to react to, instead of it
   sitting there untested:
   - `--late-rate` — for some percentage of events, backdate `pickup_time`
     by `--late-minutes` before sending, so the event looks like it
     happened earlier than it's actually arriving. With the default
     10-minute watermark on the consumer side, a late enough event gets
     dropped rather than processed — you can go watch that actually
     happen in the `ride_events` table.
   - `--duplicate-rate` — for some percentage of events, immediately
     resend the *previous* event too, simulating the kind of retry a real
     system might do.
4. Send each event to Kafka, pause based on `--rate` (events per second),
   move to the next trip.

Without these two flags, every event would be unique and perfectly on
time, and `07`'s `dropDuplicates`/`withWatermark` logic would never
actually be exercised — it'd be code you'd just have to trust works.
