---
name: implement-issue
description: Takes a GitHub issue through to an open PR (branch, code, tests, checks, PR). Use when asked to implement or fix an issue.
---

# Implement an issue

Input: issue number. Do every step.

1. `gh issue view <n> --comments`. Note the goal, the acceptance criteria and the
   project folder. If there are no criteria, write your own and put them in the PR.
2. `git checkout -b claude/issue-<n>-<short-slug>` from the default branch.
3. Hand the issue and its criteria to the `developer` agent.
4. Hand the developer's summary to the `test-writer` agent. Every criterion needs a
   test. If the tests find a bug, send it back to `developer`.
5. Run the `format-check` skill and fix everything it reports.
6. Run the `security-check` skill and fix every confirmed finding.
7. Stage the changed files by name, then commit with
   `git commit -m "<summary> (Fixes #<n>)"` and push with `git push -u origin HEAD`.
8. Run `gh pr create --base main --title "<summary>" --body-file <file>`, using this
   body:

   ```markdown
   ## Summary
   What changed and why, in a few sentences.

   Fixes #<n>

   ## Changes
   - `<file>`: <change>

   ## Acceptance criteria
   - [x] <criterion> (`<test name>`)

   ## Testing
   <pytest summary line>

   ## Checks
   - ruff format / ruff check: pass
   - security check: pass, or findings and how they were handled

   ## Assumptions
   None, or a list.
   ```

9. Post the PR link as a comment on the issue.
