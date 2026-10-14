# AI dev workflow — shared instructions

These instructions are loaded by every Claude run in GitHub Actions (the workflow
copies `ai-pr-agents/claude/` to `.claude/` before Claude starts).

## Repository layout
- This is a monorepo of independent Python projects, one per top-level folder
  (e.g. `ridepulse-databricks/`). Treat each folder as its own project: its own
  `tests/`, its own `requirements.txt` / `tests/requirements.txt`.
- `ai-pr-agents/` holds this automation. Do not modify it unless the issue asks.
- Files starting with `# Databricks notebook source` are Databricks notebooks in
  source format. Keep the header line, the `# COMMAND ----------` separators and the
  `# MAGIC ` prefix on every line of `%md` / `%sql` cells. `spark`, `dbutils` and
  `display` are globals provided by the runtime.

## Engineering standards (Python)
- Python 3.11+. Type hints on public functions. Docstrings only where intent is not obvious.
- Formatting and linting: `ruff format` and `ruff check` with `ai-pr-agents/config/ruff.toml`.
- Tests: `pytest`, placed in `<project>/tests/test_<module>.py`. Pure logic must be
  unit-testable without a cluster — factor Spark-independent logic into functions.
  PySpark tests use a local `SparkSession` fixture from `conftest.py`.
- Security: no secrets, tokens or credentials in code, notebooks or config — read them
  from environment variables or Databricks secret scopes. No `eval`/`exec`, no
  `shell=True`, no SQL built by string concatenation from external input, no
  `verify=False`, no pickle/yaml.load on untrusted data.
- Never commit data files (`*.csv`, `*.parquet`, `data/`, checkpoints).

## Workflow rules
- Work from the GitHub issue: its acceptance criteria are the definition of done.
  If the issue is ambiguous, state the assumption you made in the PR description.
- Keep changes minimal and scoped to the issue. No drive-by refactors.
- Branch name: `claude/issue-<number>-<short-slug>`.
- Commit messages: imperative mood, reference the issue (`Fixes #<n>`).
- Before opening or updating a PR, run the `format-check` and `security-check` skills
  and the project's tests, and fix what they report.

## Available skills and agents
- Skills: `implement-issue`, `write-tests`, `review-pr`, `format-check`, `security-check`.
- Agents: `developer`, `test-writer`, `pr-reviewer`, `security-reviewer`.
  Delegate to an agent when its focused context helps (e.g. write tests with
  `test-writer` after `developer` finishes the change).
