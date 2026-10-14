---
description: Check a pull request for security problems and post comments
argument-hint: <PR number> <base branch, default origin/main>
---

Do a security review of pull request $ARGUMENTS.
If a base branch is given, compare against it instead of `origin/main`.

Follow the `security-check` skill: run the scanners on the changed files, then have the
`security-reviewer` agent confirm the results and review the changes by hand.

Post each confirmed problem as an inline comment, plus one summary comment that starts
with "## 🔒 Claude security review". If nothing is found, post a one-line summary
saying so. Do not change any files.
