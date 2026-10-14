# Tests

- pytest, in `<project>/tests/test_<module>.py`.
- At least one test per acceptance criterion in the issue, plus empty input, nulls and
  bad values where they apply.
- Name tests after the behaviour, e.g. `test_clean_trips_drops_negative_fares`.
- PySpark: use the `spark` fixture from `conftest.py` and small DataFrames with an
  explicit schema. Assert on collected rows.
- No network calls, cloud services or real credentials. Mock them.
- Run `pytest <project>/tests -q` before finishing. If a test exposes a real bug, report
  it rather than changing the test or marking it skip/xfail.
