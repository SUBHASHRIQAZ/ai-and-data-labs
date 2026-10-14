---
description: Security review of a PR
argument-hint: <PR number> [base branch]
---

Security review of PR $ARGUMENTS. Compare against the base branch if one is given,
otherwise `origin/main`.

Run the `security-check` skill, then have the `security-reviewer` agent go through the
scanner output and the diff.

Post each confirmed issue as an inline comment, and one summary comment headed
"## Security review". If there's nothing to report, the summary can be one line.
Don't modify files.
