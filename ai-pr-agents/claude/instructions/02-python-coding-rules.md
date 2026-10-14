# Python

- Python 3.11. Type hints on public functions.
- Follow the style of the file you're in. Docstrings only where the name doesn't say
  enough.
- Keep the diff to what the issue needs. No unrelated cleanup.
- Keep transformation logic in plain functions that take and return DataFrames, so they
  can be tested with a local SparkSession. Reads and writes stay in the notebook or job.
- Run `ruff format` and `ruff check --fix` on changed files, using
  `ai-pr-agents/config/ruff.toml`.
- New dependencies only if the issue needs them, pinned in the project's
  `requirements.txt`.
