# Git and PRs

- The issue's acceptance criteria define done. If something is ambiguous, pick the
  sensible option and list it under Assumptions in the PR.
- Branch: `claude/issue-<n>-<short-slug>`, e.g. `claude/issue-12-drop-negative-fares`.
- Commit messages are short and imperative and reference the issue:
  `Drop trips with negative fares (Fixes #12)`.
- Stage files by name. No `git add -A` or `git add .`.
- Before opening or updating a PR: format check, security check, tests.
- Fill in every section of `.github/pull_request_template.md`.
