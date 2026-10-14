# Architecture

Everything below describes the primary implementation: hand-orchestrated
notebooks (`notebooks/01-07`), deployable as Databricks Jobs
(`resources/jobs.yml`, `docs/asset_bundle.md`). `pipelines/lakeflow_etl.py`
is a separate, declarative reimplementation of the batch phase kept
specifically for comparison — see its docstring or
`docs/concepts.md` → Lakeflow for what's different about it.

## Medallion pipeline (Phase 1 — batch)

```
        TLC HVFHV Parquet
                │
                ▼
     Bronze  (ridepulse.bronze.trips)
     raw records + ingestion_timestamp + source_file
                │
                ▼
     Silver  (ridepulse.silver.trips)
     cleaned, deduplicated, enriched with pickup_date,
     pickup_hour, day_of_week, trip_duration_minutes, average_speed
                │
                ▼
     Gold  (ridepulse.gold.*)
     hourly_demand, zone_revenue, trip_kpis, peak_demand
                │
                ▼
     SQL Dashboard (sql/dashboard.sql)
```

## Phase 2 — near-real-time simulation

```
new parquet batch arrives
          │
          ▼
   Auto Loader (cloudFiles)
          │
          ▼
   Structured Streaming
          │
          ▼
   Bronze → Silver → Gold (same tables as Phase 1)
```

TLC historical data is replayed as small batches (`batch_000.parquet`,
`batch_001.parquet`, ...) via `notebooks/06_simulate_batches.py`, to
simulate files arriving over time without pretending the TLC source itself
is a live API.

## Phase 3 — Kafka

```
        TLC Data
           │
           ▼
    Python Producer
           │
           ▼
         Kafka  (topic: ride-events)
           │
           ▼
  Structured Streaming (readStream.format("kafka"))
           │
           ▼
     Bronze → Silver → Gold
           │
           ▼
     SQL Dashboard
```

## Why this order

Databricks Free Edition has limited serverless compute and restricted
outbound internet access, so Kafka is built last:

| Phase | Pipeline |
|-------|----------|
| 1 | TLC → Parquet → PySpark → Delta |
| 2 | TLC → Auto Loader → Structured Streaming → Delta |
| 3 | TLC → Python producer → Kafka → Databricks |

This keeps the project fully demonstrable even if Kafka connectivity isn't
available in a given environment.

## Design principles

The choices that show up throughout the code, not just at the phase level:

- **Idempotency.** Every write is safe to re-run. Batch Bronze checks
  `source_file` before appending; Silver uses `MERGE` instead of append;
  Gold does a full overwrite because it's cheap enough to just recompute.
  Three different mechanisms, same property, chosen per notebook because
  each one has a different failure mode.
- **Failure recovery.** Streaming checkpoints (`05`, `07`) resume without
  reprocessing or dropping data. `MERGE`'s atomicity means a crash mid-write
  leaves Silver exactly as it was, not half-updated.
- **Scalability.** Broadcast joins, partitioning, liquid clustering, and
  Adaptive Query Execution's automatic skew handling are all things that
  don't matter at one month of HVFHV data and start to matter well before
  you get to a year of it.
- **Data quality as a gate, not a suggestion.** `04_data_quality.py` raises
  on failure instead of just printing a warning, so it can actually block a
  Workflow run rather than get ignored in a log.
- **Observability.** Every notebook prints what it did — rows in, rows out,
  rows dropped — and `DESCRIBE HISTORY` gives a version-level audit trail
  for free, courtesy of Delta's transaction log.

See [docs/concepts.md](concepts.md) for where each of these is implemented,
line by line.

## Diagram

[architecture/architecture.png](../architecture/architecture.png) is the
rendered version of the three phases above, laid out as one diagram — same
information as the ASCII diagrams here, easier to take in at a glance and
what you'd actually drop into a portfolio write-up or a slide. The ASCII
diagrams in this file stay the source of truth if the two ever drift; the
PNG is regenerated from a small matplotlib script when the pipeline
changes enough to be worth re-drawing.
