---
name: write-tests
description: Add or extend pytest tests for changed Python code and run them. Use when a change lacks tests, or when asked to write/fix tests for a PR or issue.
---

# Write tests

1. Find what changed: `git diff --name-only origin/main...HEAD -- '*.py'`.
2. Map each changed source file to its project folder (first path segment) and its
   test file `<project>/tests/test_<module>.py` (create it if missing).
3. Delegate to the `test-writer` agent with the list of changed functions and the
   acceptance criteria (from the issue or PR body).
4. Run the suite yourself to confirm:

   ```bash
   pip install -q pytest
   [ -f <project>/tests/requirements.txt ] && pip install -q -r <project>/tests/requirements.txt
   pytest <project>/tests -q
   ```

5. Report the pytest summary line. Never mark a test `skip`/`xfail` to make the run green
   without saying why in the PR.

## PySpark test pattern

```python
def test_clean_trips_drops_negative_fares(spark):
    df = spark.createDataFrame(
        [(1, 12.5), (2, -3.0)],
        "trip_id INT, fare_amount DOUBLE",
    )
    result = clean_trips(df).collect()
    assert [r.trip_id for r in result] == [1]
```
