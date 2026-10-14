---
name: review-pr
description: Reviews a PR and posts inline comments plus a summary. Use when asked to review a PR.
---

# Review a PR

Input: PR number.

1. Run `gh pr view <n> --json title,body,files,baseRefName,headRefName` and
   `gh pr diff <n>`. If the body says `Fixes #x`, read the issue with `gh issue view x`.
2. Give the diff, the PR body and the issue criteria to the `pr-reviewer` agent.
3. Post the results:
   - An inline comment on the changed line for each blocker or major finding. If the fix
     is small and certain, add a ```suggestion block.
   - One summary comment:

   ```markdown
   ## Code review
   Verdict: looks good / changes suggested / blocking issues

   | Severity | Location | Finding |
   |---|---|---|
   | blocker | `path.py:42` | ... |

   Tests: adequate, or what's missing
   Acceptance criteria: met, or which aren't
   ```

4. Don't comment on formatting or import order. Don't approve or request changes through
   the review API. Comments only; merging is a human decision.
