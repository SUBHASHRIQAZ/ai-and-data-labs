# Execution guide

A literal step-by-step checklist for running this project on Databricks
Free Edition, start to finish. Follow it in order — each part assumes the
one before it is done. If you just want the "why" behind any of this,
that's in the README and `docs/architecture.md`; this file is only the
"what to click / what to run."

Total time: 30–45 minutes for Part 1 through Part 5 (the core pipeline).
Parts 6–8 are optional.

If you already have the Databricks CLI set up, Parts 4 and 6 (running the
notebooks, setting up a Workflow) can be replaced entirely by deploying the
Databricks Asset Bundle in this repo instead — see `docs/asset_bundle.md`.
Parts 1–3 (getting the data in) are still required either way.

---

## Part 0 — Before you start

- [ ] A Databricks Free Edition account. Sign up at databricks.com if you
      don't have one yet — it's free, no credit card.
- [ ] A web browser. That's it for Parts 1–6; nothing installed locally is
      required to run the pipeline itself.

---

## Part 1 — Get the data (on your own computer, not in Databricks)

Free Edition workspaces block outbound internet access, so you can't
download TLC's files from inside a Databricks notebook — get them on your
laptop first, then upload them in Part 3.

- [ ] Open https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- [ ] Under **High Volume For-Hire Vehicle Trip Records**, download **one
      month only** — e.g. `fhvhv_tripdata_2026-01.parquet`. Don't grab a
      whole year; you can add more months later once the pipeline works.
- [ ] On the same page, find **Taxi Zone Lookup Table** and download
      `taxi_zone_lookup.csv`. It's small (a few KB) — this is what turns
      location IDs into readable zone names like "Midtown" later.
- [ ] Confirm you now have two files on your machine:
      `fhvhv_tripdata_2026-01.parquet` and `taxi_zone_lookup.csv`.

---

## Part 2 — Get this repo into your Databricks workspace

Pick **one** of these two options.

### Option A — Git folder (recommended, easiest to keep in sync)

- [ ] Push/host this repo somewhere Databricks can reach it (GitHub, GitLab,
      etc.) if it isn't already.
- [ ] In the Databricks workspace sidebar: **Workspace → your user folder →
      Add → Git folder**.
- [ ] Paste the repo URL, confirm.
- [ ] You should now see `ridepulse-databricks/notebooks/*.py` as actual
      notebooks in the workspace file browser.

### Option B — Manual import (no Git needed)

- [ ] In the workspace sidebar: **Workspace → your user folder → Import**.
- [ ] Upload each file under `notebooks/` one at a time:
      `01_bronze_ingestion.py`, `02_silver_transformations.py`,
      `03_gold_aggregations.py`, `04_data_quality.py`,
      `05_streaming_ingestion.py`, `06_simulate_batches.py`,
      `07_kafka_streaming_ingestion.py`, and `transformations.py`.
- [ ] Make sure they all land in the **same folder** — `02` and `04` import
      `transformations.py` from alongside them, and that only works if it's
      in the same workspace folder.

---

## Part 3 — Set up the catalog and upload the data

- [ ] Open a new notebook or the SQL editor, attach it to a SQL Warehouse
      (Free Edition gives you a default serverless one), and run:

  ```sql
  CREATE CATALOG IF NOT EXISTS ridepulse;
  CREATE SCHEMA IF NOT EXISTS ridepulse.landing;
  CREATE VOLUME IF NOT EXISTS ridepulse.landing.raw;
  ```

  - [ ] If `CREATE CATALOG` fails with a permission error, your workspace
        doesn't allow creating new catalogs. That's fine — use whatever
        catalog you already have access to (the workspace default one
        works) instead of `ridepulse` for every widget in the notebooks
        from here on, and re-run just the `CREATE SCHEMA` /
        `CREATE VOLUME` lines against that catalog.

- [ ] Go to **Catalog** in the left sidebar → find your catalog → `landing`
      → `raw`. This is a Volume — a regular file browser.
- [ ] Upload `fhvhv_tripdata_2026-01.parquet` into a `hvfhv/` subfolder
      inside it (create the subfolder if the UI doesn't do it for you), and
      upload `taxi_zone_lookup.csv` directly into `raw`.
- [ ] Confirm the two files show up when you browse:
      `.../landing/raw/hvfhv/fhvhv_tripdata_2026-01.parquet` and
      `.../landing/raw/taxi_zone_lookup.csv`.

---

## Part 4 — Run the core pipeline

Run these four notebooks **in this exact order**. Each one has widgets at
the top (catalog name, file paths) — check them before running, they
default to the paths from Part 3.

### 4.1 — `01_bronze_ingestion.py`

- [ ] Open the notebook, attach it to serverless compute.
- [ ] Check the `catalog` widget (default `ridepulse` — change it if you
      hit the permission issue in Part 3) and `source_path` widget (should
      point at the parquet file you uploaded).
- [ ] Run All.
- [ ] Confirm: the last cell prints something like
      `ridepulse.bronze.trips: N rows total` with N in the millions (HVFHV
      is a big dataset even for one month).

### 4.2 — `02_silver_transformations.py`

- [ ] Check the `zone_lookup_path` widget points at the CSV you uploaded.
- [ ] Run All.
- [ ] Confirm: the last cell prints
      `bronze: X rows, silver: Y rows after cleaning`, with Y noticeably
      smaller than X (that's the cleaning filters working, not a bug).

### 4.3 — `03_gold_aggregations.py`

- [ ] Run All.
- [ ] Confirm: the last cell prints row counts for all four Gold tables
      (`hourly_demand`, `zone_revenue`, `trip_kpis`, `peak_demand`), all
      non-zero, plus a preview table of `trip_kpis`.

### 4.4 — `04_data_quality.py`

- [ ] Run All.
- [ ] Confirm: you see a report table of checks, and the final print line
      says something like `N/N checks passed`. If any check fails, the
      notebook raises an error and tells you exactly which check and by how
      much — fix that before moving on rather than ignoring it.

At this point the batch pipeline (Phase 1) is fully built and verified.

---

## Part 5 — Query the results

- [ ] Open **SQL Editor** in the sidebar, pick your SQL Warehouse.
- [ ] Open and run `sql/dashboard.sql` — you should get back real numbers:
      trip counts, top zones, revenue.
- [ ] Try `sql/demand_analysis.sql` and `sql/revenue_analysis.sql` too.

If these return results, the whole batch pipeline works end to end.

---

## Part 6 — Optional: automate with a Workflow

This is the manual, click-through way to get what `databricks bundle
deploy` + `databricks bundle run ridepulse_batch_etl` gives you in two
commands (`docs/asset_bundle.md`). Do this part by hand if you don't have
the CLI set up, or if you want to see how a Job's built before letting a
bundle do it for you.

- [ ] **Workflows** in the sidebar → **Create Job**.
- [ ] Add four **Notebook** tasks, one per notebook from Part 4, in order:
      `01` → `02` → `03` → `04`.
- [ ] Set each task's **Depends on** field to the previous task, so they
      run in sequence and stop if one fails.
- [ ] Run the Job once manually to confirm it works, then optionally add a
      schedule (Job details → Schedule).

---

## Part 7 — Optional: streaming simulation (Auto Loader)

This replaces the one-shot batch read in `01` with an incremental,
checkpointed stream. Doesn't require anything outside Databricks.

- [ ] Open `06_simulate_batches.py`. Check `input_path` points at your
      uploaded parquet file, and `output_dir` at
      `/Volumes/ridepulse/landing/raw/hvfhv_stream/`.
- [ ] Set `num_batches` to something small first (e.g. `5`) so you're not
      waiting long, and run it. It'll pause between batches — that's the
      point, it's simulating files arriving over time. Leave it running.
- [ ] In a **second** notebook tab, open `05_streaming_ingestion.py`. Point
      `source_path` at the same `hvfhv_stream/` directory, set
      `trigger_mode` to `continuous`, and run it.
- [ ] Watch `05` pick up each batch `06` drops — that's Auto Loader working.
      Stop `05` manually (it runs continuously by design) once you've seen
      it process a few batches.

---

## Part 8 — Optional: Kafka

Read this before attempting it: Free Edition's outbound internet
restriction (the same one from Part 1) also blocks reaching an external
Kafka broker, so this phase typically **won't run inside Free Edition**
unless your broker happens to be reachable from the workspace. It's here
for completeness and because the code is worth reading either way.

If you do have a reachable Kafka broker:

- [ ] On your own machine: `pip install -r kafka/requirements.txt`
- [ ] Run the producer:
      ```
      python kafka/ride_producer.py \
        --source-path fhvhv_tripdata_2026-01.parquet \
        --zone-lookup-path taxi_zone_lookup.csv \
        --bootstrap-servers <your-broker>:9092 \
        --late-rate 0.1 --duplicate-rate 0.05
      ```
- [ ] In Databricks, open `07_kafka_streaming_ingestion.py`, point
      `kafka_bootstrap_servers` at the same broker, run it.
- [ ] Confirm rows land in `ridepulse.bronze.ride_events`.

---

## Part 9 — Optional: run the tests locally

Only relevant if you're modifying `notebooks/transformations.py` and want
to check your changes before pushing them back into the notebook — doesn't
touch Databricks or the TLC data at all.

- [ ] On your own machine: `pip install -r tests/requirements.txt`
- [ ] `pytest tests/`
- [ ] If you get `JAVA_GATEWAY_EXITED`, install a JDK first
      (`brew install openjdk` on macOS) — PySpark needs a JVM even for a
      local test run.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `CREATE CATALOG` permission error | Your workspace doesn't allow new catalogs — use an existing one (see Part 3). |
| `Path does not exist` reading the parquet/CSV | Check the widget value matches exactly where you uploaded the file in Part 3 — including the `hvfhv/` subfolder for the parquet file. |
| `02` fails with "table or view not found" for `transformations` | `transformations.py` isn't in the same workspace folder as `02_silver_transformations.py` — see Part 2, Option B. |
| `04_data_quality.py` fails a check | Read the printed detail — it tells you which check and the exact count. Usually means `02`/`03` didn't finish cleanly, or you're running `04` against stale data from a previous attempt. |
| Nothing happens / very slow | Confirm the notebook is attached to compute (serverless, since Free Edition has no classic clusters) — an unattached notebook won't run at all. |
| Kafka notebook can't connect | Expected on Free Edition — see Part 8. |
