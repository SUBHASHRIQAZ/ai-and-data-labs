---
description: Run the format, lint, test and security checks on this branch and fix problems
---

Run all checks on the files changed on this branch and fix what they report:

1. `format-check` skill (ruff format and ruff lint)
2. The project's tests with pytest
3. `security-check` skill (bandit, pip-audit, secret scan)

Finish with a short table: check | result | what you fixed.
