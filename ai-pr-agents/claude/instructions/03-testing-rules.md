# Testing rules

- Use `pytest`. Put tests in `<project>/tests/test_<module>.py`.
- Every acceptance criterion in the issue needs at least one test.
- Also test edge cases: empty input, nulls, invalid values, error handling.
- One behaviour per test, with a descriptive name:
  `test_<function>_<situation>_<expected result>`.
- For PySpark code, use the `spark` fixture from `conftest.py`, build small
  DataFrames with explicit schemas, and check the collected rows.
- Tests must not use the network, cloud services or real credentials. Mock them.
- Run the tests before you finish:
  `pytest <project>/tests -q`
- Never skip or weaken a test just to make it pass. If a test finds a real bug,
  report it.
