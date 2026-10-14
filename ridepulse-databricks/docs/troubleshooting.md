# Troubleshooting log

Real errors hit running this in an actual Databricks workspace, in the
order they came up, with root cause and the fix that's now in the code.
None of this was caught by local review or syntax checks (see the honesty
notes in `docs/asset_bundle.md` and `pipelines/lakeflow_etl.py`'s
docstring) — it only surfaced by actually running the Lakeflow Pipeline
end to end. Keeping this list is more useful than pretending the first
version worked: every entry below is something the code used to get wrong.

If you hit an error running this that isn't listed here, it's worth adding
once you've fixed it — this file is meant to grow.

---

## 1. Auto Loader pointed at a file instead of a directory

**Error:**
```
silver_trips
Failed to read dataset 'ridepulse.lakeflow_demo.bronze_trips'. Dataset is
defined in the pipeline but could not be resolved.
```

**Where:** Running `ridepulse_lakeflow_pipeline` (`pipelines/lakeflow_etl.py`).
The error surfaces on `silver_trips`, but the real failure is upstream, in
`bronze_trips`.

**Root cause:** `resources/pipelines.yml` was passing the pipeline the same
`source_path` variable `01_bronze_ingestion.py` uses for its batch read —
an exact file path
(`/Volumes/ridepulse/landing/raw/hvfhv/fhvhv_tripdata_2026-01.parquet`).
`bronze_trips()` in `lakeflow_etl.py` doesn't do a batch read, though — it
uses Auto Loader (`cloudFiles`), which needs a **directory** to watch and
list, not one exact file. Pointed at a file, Auto Loader never finds
anything to list, `bronze_trips` never materializes a single batch, and
`silver_trips` — which reads `bronze_trips` — fails with the generic
"could not be resolved" message. That message is always a downstream
symptom; the actual cause is whichever upstream table never successfully
ran.

**Fix:** Added a dedicated `lakeflow_source_dir` variable
(`databricks.yml`) defaulting to the *directory* containing the file
(`/Volumes/ridepulse/landing/raw/hvfhv/`), and pointed
`resources/pipelines.yml`'s `configuration.source_path` at that instead of
reusing `var.source_path`. Mirrors the pattern `05_streaming_ingestion.py`
/ `06_simulate_batches.py` already used with their own
`stream_source_path` variable, kept separate from `01`'s file path for the
same reason.

**Status:** Fixed. Needs a **full refresh** the first time after
redeploying — `bronze_trips`'s checkpoint from the failed attempt won't
re-list files on its own against the corrected path otherwise
(`databricks bundle run ridepulse_lakeflow_pipeline --full-refresh`, or
"Full refresh all" in the Pipelines UI).

---

## 2. `timestampNtz` Delta feature not enabled

**Error:**
```
bronze_trips (line 30)
Your table schema requires manually enablement of the following table
feature(s): timestampNtz.

To do this, run the following command for each of features listed above:
  ALTER TABLE table_name SET TBLPROPERTIES ('delta.feature.feature_name' = 'supported')
```

**Where:** Running `ridepulse_lakeflow_pipeline` — `bronze_trips` itself
this time, not a downstream table.

**Root cause:** Recent TLC HVFHV parquet files write their timestamp
columns (`pickup_datetime`, `dropoff_datetime`, `request_datetime`,
`on_scene_datetime`) with `isAdjustedToUTC=false`. Spark infers that as
`TimestampNTZType` rather than the older `TimestampType` — and
`TimestampNTZType` is a newer Delta table feature that Unity
Catalog-managed tables don't auto-enable on first write. Worse, this
creates a circular dependency once `bronze_trips` already exists in a
broken state: the fix would normally be `ALTER TABLE ... SET
TBLPROPERTIES ('delta.feature.timestampNtz' = 'supported')`, but
`bronze_trips` is a **streaming table** managed by the pipeline — it needs
a refresh to pick up an `ALTER TABLE` change, and a refresh is exactly
what keeps failing. A config change tried first,
`delta.properties.defaults.feature.timestampNtz`, didn't help either: it
only sets the feature as a *default* for tables created after the config
is set, it doesn't retroactively fix a table (or a table definition) that
already has the problem.

**Fix:** Stopped `TimestampNTZType` from ever entering the schema in the
first place, at the read step, in all three places raw TLC parquet gets
read into a new Delta table:

```python
spark.conf.set("spark.sql.parquet.inferTimestampNTZ.enabled", "false")
```

This makes Spark (and Auto Loader, which uses the same Parquet reader
underneath) always infer Parquet timestamp columns as the regular
`TimestampType`, regardless of the file's `isAdjustedToUTC` flag — so the
`timestampNtz` feature requirement never comes up at all, instead of being
worked around after the fact. Set in:
- `notebooks/01_bronze_ingestion.py` (before `spark.read.parquet(...)`)
- `notebooks/05_streaming_ingestion.py` (before the Auto Loader read)
- `pipelines/lakeflow_etl.py` (before `bronze_trips()`'s Auto Loader read)

**Status:** Fixed. If a table already exists half-created from before this
fix, it needs to be dropped and recreated (or full-refreshed) rather than
patched — a table that never completed its first successful write doesn't
have a clean state to `ALTER`.

---

## 3. `input_file_name()` blocked under Unity Catalog

**Error:**
```
bronze_trips
The command(s): input_file_name are not supported in Unity Catalog. Please
use _metadata.file_path instead.
```

**Where:** Running `ridepulse_lakeflow_pipeline` — `bronze_trips`, same
function as error #2, next error in line once that one was fixed.

**Root cause:** `input_file_name()` is an older Spark function that
returns the path of the file a row came from. Unity Catalog blocks it on
governed compute (it can be used to read file paths outside UC's
access-control model) and requires the newer built-in `_metadata` struct
column instead, which UC can govern properly.

**Fix:** Replaced every `input_file_name()` call with
`col("_metadata.file_path")`:
- `notebooks/01_bronze_ingestion.py`
- `notebooks/05_streaming_ingestion.py`
- `pipelines/lakeflow_etl.py`

**Status:** Fixed.

---

## 4. `ValueError: not enough values to unpack (expected 3, got 0)` in `gold_peak_demand`

**Error:**
```
PYTHON.VALUE_ERROR
gold_peak_demand
not enough values to unpack (expected 3, got 0)
```

**Where:** Running `ridepulse_lakeflow_pipeline` — `gold_peak_demand`, the
last of the four Gold materialized views.

**Root cause:**
```python
q1, q2, q3 = base.approxQuantile("trip_count", [0.25, 0.5, 0.75], 0.01)
```
`approxQuantile` returns `[]` — not three `NaN`s — when the DataFrame it's
called on has zero rows. That means `silver_trips` was empty at the moment
`gold_peak_demand` materialized, most likely because this ran shortly
after the fixes above, before `bronze_trips` had finished ingesting
anything. Unpacking `[]` into `q1, q2, q3` is what throws. The other three
Gold tables don't hit this: a plain `groupBy().agg()` on zero rows just
produces an empty (but valid) table — only the quantile call breaks on
empty input. The identical bug exists in `notebooks/03_gold_aggregations.py`
too (same `approxQuantile` call), just less likely to trigger there since
`02` normally runs and populates Silver before `03` does.

**Fix:** Check the length of the returned quantile list before unpacking,
in both places:
```python
quantiles = base.approxQuantile("trip_count", [0.25, 0.5, 0.75], 0.01)
if len(quantiles) < 3:
    return base.withColumn("demand_level", F.lit("Unknown"))
q1, q2, q3 = quantiles
...
```
An empty upstream table now produces an empty (or `"Unknown"`-bucketed)
Gold table instead of crashing the run. The next refresh, once Silver
actually has data, recomputes real Low/Medium/High/Very High buckets.

**Status:** Fixed in both `pipelines/lakeflow_etl.py` (`gold_peak_demand`)
and `notebooks/03_gold_aggregations.py`.

---

## Pattern worth noticing

Errors #1-#3 all hit the exact same function, `bronze_trips()` /
`01_bronze_ingestion.py`'s Bronze read, because that's the one place in
the pipeline that touches raw, unmodified TLC parquet directly — every
other table reads from an already-clean upstream table. If you extend this
project to a different data source, this is the function most likely to
need adjusting again.

Error #4 is a different category: not a Databricks/Unity Catalog quirk,
but a genuine gap in the original code — `approxQuantile` on an empty
DataFrame was never handled, in either implementation. Worth remembering
that "the Lakeflow Pipeline and the notebooks share `transformations.py`"
only guarantees the *shared* logic matches; `peak_demand`'s bucketing
logic was duplicated by hand in both places (not shared via import), so it
had to be fixed in two files, not one.
