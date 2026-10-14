# Deploying with a Databricks Asset Bundle

`databricks.yml` (repo root) plus `resources/jobs.yml` and
`resources/pipelines.yml` turn this project into a
[Databricks Asset Bundle](https://docs.databricks.com/dev-tools/bundles/index.html) —
run `databricks bundle deploy` and the notebooks get synced to your
workspace and wired up as two Jobs plus a Lakeflow Declarative Pipeline,
instead of importing files and clicking through Workflows by hand.

This is an alternative to the manual walkthrough in
[execution_guide.md](execution_guide.md), not a replacement for it — Parts
1–3 of that guide (download the TLC data, set up the catalog, upload into
the landing Volume) are still a one-time manual step. Free Edition
workspaces block outbound internet, so nothing running *inside* Databricks
— bundle-deployed or not — can fetch the TLC files itself. The bundle picks
up from "the data is already in the Volume" onward.

I haven't been able to run `databricks bundle validate` against a real
workspace while writing this (no Databricks access from where this was
built) — the YAML is syntactically valid and follows the documented
resource schema, but run `databricks bundle validate` yourself before your
first deploy, and treat this doc as a starting point you may need to adjust
rather than a guarantee. This applies more to `resources/pipelines.yml`
than `resources/jobs.yml` — pipeline resources are a newer, faster-moving
part of the bundle schema, and a couple of fields there (`target` vs.
`schema`, the `file:` library type) are my best understanding rather than
something I've confirmed against a current CLI. If `bundle validate`
complains about `pipelines.yml` specifically, run `databricks bundle
schema` and adjust the field names to match.

## What's in the bundle

- **`ridepulse_batch_etl`** — one scheduled Job with five tasks. Four are
  the notebook chain `01` → `02` → `03` → `04`, same order and intent as
  the manual Workflow setup in `execution_guide.md` Part 6. The fifth,
  `lakeflow_pipeline_refresh`, is a `pipeline_task` — a Databricks Jobs
  task type that triggers an update of `ridepulse_lakeflow_pipeline`
  (below) rather than running a notebook. It has no `depends_on`: the
  pipeline reads the landing Volume directly, not the notebook chain's
  Bronze table, so it runs concurrently with `bronze_ingestion` instead of
  waiting on it. One `bundle run` (or one scheduled firing) refreshes both
  implementations against the same source data — see "Automation" below
  for why that's worth doing here specifically, not as a general pattern.
- **`ridepulse_lakeflow_pipeline`** — the same Bronze → Silver → Gold logic
  reimplemented as a Lakeflow Declarative Pipeline (`pipelines/lakeflow_etl.py`,
  using the `pyspark.pipelines` API), publishing into `ridepulse.lakeflow_demo`
  so it never collides with the tables the notebooks write to
  `ridepulse.bronze/silver/gold`. This exists specifically as a comparison
  — see the docstring at the top of `lakeflow_etl.py` for what's genuinely
  different (Bronze as an explicit streaming table, Silver/Gold as explicit
  materialized views, declarative `@dp.expect_or_drop` constraints instead
  of imperative filters, the pipeline engine deciding incremental vs. full
  refresh instead of a hand-written `MERGE`) versus what's identical (the
  same `enrich_trips`/`add_zone_names` functions from `transformations.py`,
  imported directly, not reimplemented). It's still an independent
  resource, not just a task inside the job — `bundle run
  ridepulse_lakeflow_pipeline` triggers it on its own too.
- **`ridepulse_streaming_demo`** — `06_simulate_batches.py` (writes a
  handful of batch files) then `05_streaming_ingestion.py` with
  `trigger_mode=availableNow` (so the job actually completes rather than
  running forever). This is a correctness check that Auto Loader processes
  the batches end to end, not a live demo — for watching Auto Loader react
  to files in real time, run `05` and `06` manually side by side instead,
  with `05` set to `trigger_mode=continuous` (`execution_guide.md` Part 7).
  Not scheduled — it's a demo you run when you want to see it, not
  something you want firing on a cron.

The notebook tasks are plain orchestration, not a Lakeflow Pipeline —
that's still the primary implementation in this repo (see
`05_streaming_ingestion.py`'s own note on why raw Auto Loader/Structured
Streaming was chosen there), with the pipeline included specifically so you
can read both and see the trade-off directly instead of taking it on faith.
`docs/concepts.md` → Databricks → Lakeflow has more on this.

## Automation

`ridepulse_batch_etl` has a `schedule:` block (`resources/jobs.yml`) — `0 0
6 * * ?` UTC, daily, arbitrary starting point — but it deploys **paused**
on purpose. A bundle you `deploy` for the first time shouldn't silently
start running on a schedule you didn't explicitly turn on. Turn it on once
you've confirmed a manual run works:

### Why the scheduled job runs both implementations

Worth being direct about this: there's no production benefit to running
the notebook ETL and the Lakeflow Pipeline together on every scheduled
firing. It's two copies of the same computation, written to two schemas,
neither one covering for the other if it fails. If this were a real system
you'd pick one implementation and schedule that.

The reason they're combined here is narrower — it keeps the *comparison*
current. `pipelines/lakeflow_etl.py` exists so you can read it next to
`notebooks/01-03` and see the trade-off between hand-orchestrated notebooks
and a declarative pipeline concretely. A comparison you ran once and never
again goes stale the moment you add February's data through the scheduled
notebook path and the Lakeflow side doesn't see it. Running both on the
same trigger keeps them looking at the same data, for as long as you're
still using this project to learn from that comparison. It's also
genuinely cheap right now — one month of HVFHV data on serverless compute.

If you're past the comparison and just want the pipeline you'd actually
run going forward, delete the `lakeflow_pipeline_refresh` task from
`ridepulse_batch_etl` (and drop `resources/pipelines.yml` /
`pipelines/lakeflow_etl.py` if you're not keeping the Lakeflow version
around at all) rather than leaving a job that pays for redundant compute
indefinitely.

```
# One-off, via the CLI (or use the Jobs UI's pause toggle)
databricks jobs update <job-id> --json '{"settings": {"schedule": {"pause_status": "UNPAUSED"}}}'
```

Or, the bundle-native way — durable, tracked in git, survives a redeploy —
edit `resources/jobs.yml`, change `pause_status: PAUSED` to `UNPAUSED`,
and `databricks bundle deploy` again.

## Prerequisites

- The Databricks CLI installed and authenticated (`databricks auth login`,
  or an existing profile) against the workspace you want to deploy to.
- Parts 1–3 of `execution_guide.md` already done: catalog/schema/Volume
  exist, `fhvhv_tripdata_2026-01.parquet` and `taxi_zone_lookup.csv` are
  uploaded to `/Volumes/ridepulse/landing/raw/...`.

## Commands

From the `ridepulse-databricks/` directory (where `databricks.yml` lives):

```
# Check the bundle resolves and the resource definitions are valid
databricks bundle validate

# Sync notebooks/pipeline source to the workspace, create/update the
# two Jobs and the Pipeline
databricks bundle deploy -t dev

# Run the batch ETL job and wait for it to finish
databricks bundle run ridepulse_batch_etl

# Run the streaming demo job
databricks bundle run ridepulse_streaming_demo

# Trigger a pipeline update and stream its status back
databricks bundle run ridepulse_lakeflow_pipeline

# Tear down what this bundle deployed (the Jobs and the Pipeline; doesn't
# touch your catalog, tables, or the Volume — those aren't bundle-managed)
databricks bundle destroy
```

`databricks bundle run` streams status back to your terminal and exits
non-zero on failure — for the Jobs that includes `04_data_quality.py`
raising on a failed check, so a bad run shows up as a failed job rather
than a green checkmark you'd have to notice was wrong. For the pipeline,
check the Data Engineering → Pipelines → `ridepulse_lakeflow_pipeline` →
data quality tab in the workspace UI afterward to see the
`@dp.expect_or_drop` pass/fail counts per rule.

## Overriding variables

The paths and catalog name are bundle variables
(`databricks.yml` → `variables:`), not hardcoded — override them per run
without editing YAML:

```
databricks bundle run ridepulse_batch_etl --var="catalog=my_catalog"
```

Or set a default for a specific target by adding a `variables:` block under
that target in `databricks.yml`.

## The dashboard / report

This bundle doesn't include a dashboard resource. Databricks dashboards
(Lakeview) are stored as a JSON format that's meant to be authored by
building the dashboard once in the workspace UI, then captured into the
bundle — not hand-written. To add one:

1. Deploy and run `ridepulse_batch_etl` at least once so the Gold tables
   exist.
2. In the workspace, build a dashboard against `ridepulse.gold.*` (the
   queries in `sql/dashboard.sql`, `sql/demand_analysis.sql`, and
   `sql/revenue_analysis.sql` are a good starting point for what to chart —
   busiest zones, peak hours, revenue by zone, trip KPIs over time).
3. Once you're happy with it, run:
   ```
   databricks bundle generate dashboard --existing-dashboard-id <id-from-the-dashboard-url>
   ```
   This pulls the dashboard's JSON definition into `resources/` and adds a
   `dashboards:` entry to reference it, so future `bundle deploy` runs keep
   it in sync with the rest of the bundle.
4. Commit the generated `.lvdash.json` and the updated resource YAML.

From that point on, the dashboard deploys along with the jobs — it just
has to be authored once, same as any other Lakeview dashboard.
