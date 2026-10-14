---
name: format-check
description: Runs ruff format and ruff check on the changed Python files and fixes the results. Use before committing, or when the format-lint CI job fails.
---

# Format and lint

Only check files changed against `main`, so unrelated old code isn't reformatted.

```bash
pip install -q ruff
FILES=$(git diff --name-only --diff-filter=ACMR origin/main...HEAD -- '*.py')
[ -z "$FILES" ] && echo "No Python changes" && exit 0

ruff format --config ai-pr-agents/config/ruff.toml $FILES
ruff check  --config ai-pr-agents/config/ruff.toml --fix $FILES
ruff check  --config ai-pr-agents/config/ruff.toml $FILES   # should exit 0
```

- Fix lint errors in the code itself. A `# noqa` needs a rule code and a reason.
- For Databricks notebooks, check the diff afterwards to make sure the `# MAGIC` and
  `# COMMAND ----------` lines are still there.
- Report which files were formatted, what was fixed, and anything left with the reason.
