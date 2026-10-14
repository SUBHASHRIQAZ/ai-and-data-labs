---
name: implement-issue
description: End-to-end flow from a GitHub issue to an open pull request — branch, implement, test, format, security-check, open PR. Use when asked to implement or fix a GitHub issue.
---

# Implement a GitHub issue

Input: an issue number. Run every step; do not skip checks.

1. **Read the issue**
   `gh issue view <n> --comments`. Extract goal, acceptance criteria, affected project.
   If the issue has no acceptance criteria, derive them and list them in the PR body.

2. **Branch**
   `git checkout -b claude/issue-<n>-<short-slug>` from the default branch.

3. **Implement** — delegate to the `developer` agent with the issue text and
   acceptance criteria.

4. **Test** — delegate to the `test-writer` agent with the developer's summary.
   Every acceptance criterion needs at least one test. If tests expose a bug, send it
   back to `developer` and repeat.

5. **Format** — run the `format-check` skill on changed files and fix everything.

6. **Security** — run the `security-check` skill; fix every confirmed finding.

7. **Commit and push**
   `git add <specific files>` (never `git add -A`; never commit data files),
   `git commit -m "<imperative summary> (Fixes #<n>)"`, `git push -u origin HEAD`.

8. **Open the PR**
   `gh pr create --base main --title "<summary>" --body-file <file>` using this body:

   ```markdown
   ## Summary
   <what and why, 2–4 sentences>

   Fixes #<n>

   ## Changes
   - <file>: <change>

   ## Acceptance criteria
   - [x] <criterion> — covered by `<test name>`

   ## Testing
   <pytest summary line>

   ## Checks
   - ruff format / ruff check: pass
   - security-check: <pass, or findings + resolution>

   ## Assumptions
   <or "None">
   ```

9. Comment on the issue with the PR link.
