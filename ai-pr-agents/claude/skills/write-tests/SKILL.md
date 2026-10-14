---
name: write-tests
description: Adds or extends pytest tests for the Python code changed on a branch, and runs them. Use when a change is missing tests.
---

# Write tests

1. List the changed files: `git diff --name-only origin/main...HEAD -- '*.py'`.
2. For each one, the project is the first path segment and the tests go in
   `<project>/tests/test_<module>.py`. Create the file if it doesn't exist.
3. Give the `test-writer` agent the changed functions and the acceptance criteria from
   the issue or PR.
4. Run the tests yourself to confirm:

   ```bash
   pip install -q pytest
   [ -f <project>/tests/requirements.txt ] && pip install -q -r <project>/tests/requirements.txt
   pytest <project>/tests -q
   ```

5. Report the pytest summary line. If anything had to be marked skip or xfail, say why
   in the PR.

PySpark example:

```python
def test_clean_trips_drops_negative_fares(spark):
    df = spark.createDataFrame(
        [(1, 12.5), (2, -3.0)],
        "trip_id INT, fare_amount DOUBLE",
    )
    result = clean_trips(df).collect()
    assert [r.trip_id for r in result] == [1]
```
