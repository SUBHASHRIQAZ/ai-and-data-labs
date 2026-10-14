# RidePulse

A Bronze → Silver → Gold lakehouse built on NYC's public High Volume
For-Hire Vehicle (HVFHV) trip data — the Uber/Lyft-style dataset the TLC
publishes every month — extended into a near-real-time pipeline with Auto
Loader, Structured Streaming, and Kafka.

It runs end to end on **Databricks Free Edition**, with no external cloud
account, no Kafka broker required for the core pipeline, and no data files
committed to this repo. If you're using this to learn PySpark/Delta/Streaming
rather than just to run it, `docs/concepts.md` is the part worth reading —
it walks through joins, MERGE, watermarks, clustering, and everything else
this project actually uses, pointing at the exact line of code each one
shows up in. `docs/pipeline_logic.md` is the companion to that: not *why*
each choice was made, just *what* each notebook's logic actually does,
step by step, table by table.

Two ways to run it: click through the workspace UI notebook by notebook
(`docs/execution_guide.md`), or deploy it as a **Databricks Asset Bundle**
and run it as Jobs with two CLI commands (`docs/asset_bundle.md`). The
bundle is faster if you already have the CLI set up; the manual path is
worth doing at least once if you're still learning your way around the
Databricks UI. If something errors while running it in your workspace,
check `docs/troubleshooting.md` first — it's a real log of errors hit
running this project (mostly Unity Catalog/Auto Loader specific ones on
`bronze_trips`) with root cause and the fix already applied to the code.

The bundle also deploys a second, declarative implementation of the same
Bronze → Silver → Gold logic as a **Lakeflow Declarative Pipeline**
(`pipelines/lakeflow_etl.py`), published to a separate schema so it doesn't
collide with the notebook-based tables. It's there specifically so you can
read it next to `notebooks/01-03` and see, concretely, what a declarative
pipeline buys you over hand-orchestrated notebooks — not as a replacement
for the primary implementation.

## Why HVFHV

The TLC also publishes Yellow Taxi, Green Taxi, and regular FHV data.
HVFHV was the right pick here specifically because it's app-dispatched —
same shape of data an Uber/Lyft-style backend would actually produce
(request time, on-scene time, driver pay, shared-ride flags), which makes
the "simulate a live ride feed" phases later in the project feel less
artificial.

## Architecture

```
        TLC HVFHV parquet
                │
                ▼
        Bronze (raw + ingestion metadata)
                │
                ▼
        Silver (cleaned, deduped, enriched)
                │
                ▼
        Gold (business aggregates)
                │
                ▼
        SQL dashboard
```

Auto Loader/Structured Streaming and Kafka bolt onto the same Bronze/Silver/Gold
tables later — see [docs/architecture.md](docs/architecture.md) for the full
diagram and the reasoning behind the phase order.

```
ridepulse (catalog)
  ├── landing         — Volumes: uploaded raw files, streaming checkpoints
  ├── bronze
  ├── silver
  ├── gold
  └── lakeflow_demo   — bronze_trips/silver_trips/gold_* from the Lakeflow Pipeline comparison
```

## Concepts covered

Each of these is implemented in the code, not just described — see
[docs/concepts.md](docs/concepts.md) for the full write-up with file/line
pointers.

| Area | Topics |
|---|---|
| PySpark | joins, broadcast joins, window functions, groupBy/shuffles, skew, repartition vs coalesce, caching, UDF vs built-in functions |
| Delta Lake | ACID, MERGE, time travel, OPTIMIZE, schema evolution, partitioning, liquid clustering |
| Structured Streaming | checkpoints, watermarks, late data, duplicate events, exactly-once processing, trigger intervals |
| Databricks | Unity Catalog, Auto Loader, Lakeflow, Workflows, SQL Warehouses, monitoring |
| Architecture | idempotency, failure recovery, scalability, data quality, observability |

## Running this on Databricks Free Edition

This is the part most portfolio write-ups skip, and it's where things
actually go wrong, so it's worth being specific. For a literal
checkbox-by-checkbox version of what follows, see
[docs/execution_guide.md](docs/execution_guide.md).

**1. Get the data.** Free Edition workspaces restrict outbound internet, so
you can't `wget` the TLC file from inside a notebook. Download it on your
own machine instead:
- https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page → "High
  Volume For-Hire Vehicle Trip Records" → one month, e.g.
  `fhvhv_tripdata_2026-01.parquet`.
- Same page → "Taxi Zone Lookup Table" → `taxi_zone_lookup.csv` (small,
  needed to resolve `pickup_zone`/`dropoff_zone` names in Silver).

**2. Set up the catalog and upload the data.** Open a SQL editor or notebook
attached to a SQL Warehouse and run:

```sql
CREATE CATALOG IF NOT EXISTS ridepulse;
CREATE SCHEMA IF NOT EXISTS ridepulse.landing;
CREATE VOLUME IF NOT EXISTS ridepulse.landing.raw;
```

(`01_bronze_ingestion.py` does this too, so you can skip this step and let
the notebook create everything on first run — but you still need the
`raw` Volume to exist before you can upload into it.) Then, in the
Catalog Explorer UI, navigate to `ridepulse → landing → raw` and upload
`fhvhv_tripdata_2026-01.parquet` and `taxi_zone_lookup.csv` there directly
(drag-and-drop works). If you have the Databricks CLI configured instead:

```
databricks fs cp fhvhv_tripdata_2026-01.parquet dbfs:/Volumes/ridepulse/landing/raw/hvfhv/
databricks fs cp taxi_zone_lookup.csv dbfs:/Volumes/ridepulse/landing/raw/
```

(needs a reasonably current Databricks CLI — `databricks -v` should show
0.200+ — since that's what added Unity Catalog Volume support to `fs cp`.
The UI upload always works regardless of CLI version.)

**3. Import the notebooks.** Workspace → your user folder → Import, and
either upload the `.py` files from `notebooks/` one at a time, or connect
this repo as a Databricks Git folder (Repos) and get all of them at once
plus easy pulls when you update the code.

**4. Run them in order:** `01_bronze_ingestion.py` → `02_silver_transformations.py`
→ `03_gold_aggregations.py` → `04_data_quality.py`. Each one exposes widgets
at the top (catalog name, source paths) — set those instead of editing the
code. All-purpose compute isn't available on Free Edition, so you're
running these on serverless compute either way; that's already the
assumption everywhere in this repo.

**5. Query the results.** Open `sql/*.sql` against a Serverless SQL
Warehouse (Free Edition gives you one by default) — SQL Editor → pick the
warehouse → paste a query.

**6. Optional: chain it into a Workflow.** Databricks UI → Workflows →
Create Job → add four Notebook tasks, one per notebook from step 4, each
depending on the one before it. That gets you a one-click (or scheduled)
run of the whole pipeline instead of clicking through notebooks by hand —
`docs/concepts.md` has more on why this matters for a real pipeline (retry
behavior, `04`'s data quality check actually gating the rest of the job).

**7. Auto Loader / streaming (`05`, `06`).** These work on Free Edition too,
against the same Volume paths — `06_simulate_batches.py` drops small
parquet files into a directory over time, `05_streaming_ingestion.py`
watches that directory with Auto Loader. No external services needed.

**8. Kafka (`07`, `kafka/ride_producer.py`).** This is the one phase that
genuinely doesn't work inside Free Edition on its own — the outbound
internet restriction that blocked step 1's download also blocks reaching
an external Kafka broker from the workspace. You'd need a broker Databricks
can actually reach (self-managed on a reachable host, or a managed Kafka
service with network access configured), which is more infrastructure than
a portfolio project needs. It's included here to complete the
architecture and because the producer/consumer code is worth reading even
if you don't run it — see `docs/architecture.md` for why this phase is
built last regardless of which Databricks tier you're on.

## Repo structure

```
ridepulse-databricks/
│
├── README.md
├── databricks.yml                    # Asset Bundle definition
├── resources/
│   ├── jobs.yml                      # Job resources deployed by the bundle
│   └── pipelines.yml                 # Lakeflow Declarative Pipeline resource
├── pipelines/
│   └── lakeflow_etl.py               # Bronze/Silver/Gold as a declarative pipeline (comparison)
├── notebooks/
│   ├── 01_bronze_ingestion.py
│   ├── 02_silver_transformations.py
│   ├── 03_gold_aggregations.py
│   ├── 04_data_quality.py
│   ├── 05_streaming_ingestion.py
│   ├── 06_simulate_batches.py
│   ├── 07_kafka_streaming_ingestion.py
│   └── transformations.py            # Silver logic — imported by 02 and by tests/
├── sql/
│   ├── demand_analysis.sql
│   ├── revenue_analysis.sql
│   ├── dashboard.sql
│   └── maintenance.sql               # OPTIMIZE / VACUUM / time travel
├── kafka/
│   ├── ride_producer.py
│   └── requirements.txt
├── tests/
│   ├── conftest.py
│   ├── requirements.txt
│   └── test_transformations.py
├── architecture/
│   ├── architecture.png
│   └── render_diagram.py             # regenerates architecture.png (matplotlib)
├── docs/
│   ├── architecture.md
│   ├── asset_bundle.md               # deploying/running the pipeline as a bundle
│   ├── concepts.md                   # PySpark/Delta/Streaming/Databricks concepts, tied to this code
│   ├── data_dictionary.md
│   ├── execution_guide.md            # step-by-step checklist to run the whole thing
│   ├── interview_qa.md               # condensed Q&A version of docs/concepts.md
│   ├── pipeline_logic.md             # what each notebook's logic does, step by step
│   └── troubleshooting.md            # real workspace errors hit running this, with root cause + fix
└── screenshots/
```

## Running the notebooks locally (outside Databricks)

You can't actually execute a Databricks notebook outside Databricks (no
`dbutils`, no managed `spark` session), but the files are plain, readable
Python — they open fine in any editor.

`kafka/ride_producer.py` is different: it's a normal script meant to run
*outside* Databricks (your laptop, a small VM — wherever your Kafka broker
is reachable from):

```
pip install -r kafka/requirements.txt
python kafka/ride_producer.py --source-path /path/to/fhvhv_tripdata_2026-01.parquet
```

## Running the tests

`notebooks/transformations.py` holds the Silver cleaning/enrichment logic
as a plain, importable module — no `dbutils`, no notebook markers — so it's
unit-testable with a local SparkSession. No Databricks workspace or TLC
data required:

```
pip install -r tests/requirements.txt
pytest tests/
```

PySpark needs a JVM. If `pytest` fails with `JAVA_GATEWAY_EXITED`, install
a JDK first (`brew install openjdk` on macOS).
