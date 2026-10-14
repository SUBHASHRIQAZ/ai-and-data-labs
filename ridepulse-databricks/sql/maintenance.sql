-- Delta table maintenance. Run these ad hoc (or on a schedule via a
-- Workflow task) — they're not part of the normal notebook pipeline.

-- OPTIMIZE compacts small files into larger ones and, for gold.* tables
-- (which use CLUSTER BY — see 03_gold_aggregations.py), also reorganizes
-- data around the clustering keys. Worth running after a batch of writes
-- has produced a lot of small files, e.g. after several 06_simulate_batches
-- runs have fed the streaming path.
OPTIMIZE ridepulse.bronze.trips;
OPTIMIZE ridepulse.silver.trips;
OPTIMIZE ridepulse.gold.zone_revenue;

-- VACUUM removes data files no longer referenced by the table's current
-- version, once they're older than the retention window (default 7 days).
-- This is what actually reclaims storage after OPTIMIZE rewrites files, or
-- after old MERGE versions age out. The default retention exists so that
-- time travel queries and concurrent readers on an older snapshot don't
-- have their files yanked out from under them — don't drop it below a day
-- or two without a real reason.
VACUUM ridepulse.silver.trips;

-- Every write to a Delta table is a new, atomic version — that's what makes
-- MERGE in 02_silver_transformations.py safe to re-run without corrupting
-- the table even if it fails partway through. DESCRIBE HISTORY shows that
-- version log directly.
DESCRIBE HISTORY ridepulse.silver.trips;

-- Time travel: query the table as it looked at an older version or
-- timestamp, without needing a separate backup. Useful for "what did this
-- look like before yesterday's MERGE" style debugging.
-- SELECT * FROM ridepulse.silver.trips VERSION AS OF 3;
-- SELECT * FROM ridepulse.silver.trips TIMESTAMP AS OF '2026-01-15T00:00:00Z';
