---
name: format-check
description: Run ruff format and ruff lint on changed Python files and fix issues. Use before committing or when CI's format/lint job fails.
---

# Format and lint check

Config: `ai-pr-agents/config/ruff.toml`. Scope: only files changed vs. `main`, so
legacy code is not reformatted in unrelated PRs.

```bash
pip install -q ruff
FILES=$(git diff --name-only --diff-filter=ACMR origin/main...HEAD -- '*.py')
[ -z "$FILES" ] && echo "No Python changes" && exit 0

ruff format --config ai-pr-agents/config/ruff.toml $FILES
ruff check  --config ai-pr-agents/config/ruff.toml --fix $FILES
ruff check  --config ai-pr-agents/config/ruff.toml $FILES   # must exit 0
```

Rules:
- Fix remaining lint errors by changing the code, not by adding `# noqa`. A `noqa` is
  acceptable only with a specific rule code and a reason comment.
- For Databricks notebooks, never let formatting remove `# MAGIC` prefixes or
  `# COMMAND ----------` separators — check the diff afterwards.
- Report: files formatted, lint errors fixed, any remaining with reason.
