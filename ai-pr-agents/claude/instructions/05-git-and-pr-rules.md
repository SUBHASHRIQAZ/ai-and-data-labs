# Git and pull request rules

- The GitHub issue is the definition of done. If something is unclear, make a sensible
  choice and write it under "Assumptions" in the PR.
- Branch name: `claude/issue-<number>-<short-description>`
  (for example `claude/issue-12-drop-negative-fares`).
- Commit message: short and in the imperative mood, ending with the issue,
  for example `Drop trips with negative fares (Fixes #12)`.
- Add files one by one with `git add <file>`. Never `git add -A` or `git add .`.
- Before opening or updating a PR, always run the format check, the security check and
  the project's tests, and fix what they report.
- Fill in every section of the PR template: Summary, Changes, Acceptance criteria,
  Testing, Checks, Assumptions.
