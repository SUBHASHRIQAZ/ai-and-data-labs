---
name: review-pr
description: Review a pull request and post the result to GitHub as inline comments plus one summary comment. Use when asked to review a PR.
---

# Review a pull request

Input: PR number (in CI it is provided in the prompt).

1. Gather context:
   `gh pr view <n> --json title,body,files,baseRefName,headRefName` and
   `gh pr diff <n>`. If the body references an issue (`Fixes #x`), read it with
   `gh issue view x`.
2. Delegate to the `pr-reviewer` agent with the diff, PR body and issue criteria.
3. If the diff touches auth, secrets, SQL, subprocess, deserialization, dependencies or
   `.github/workflows/`, also delegate to the `security-reviewer` agent.
4. Post results:
   - One **inline comment** per blocker/major finding, on the exact changed line
     (use the inline-comment tool; include a ```suggestion block when the fix is
     small and certain).
   - One **summary comment** on the PR:

   ```markdown
   ## 🤖 Claude PR review
   **Verdict:** ✅ Looks good | ⚠️ Changes suggested | ❌ Blocking issues

   | Severity | Location | Finding |
   |---|---|---|
   | blocker | `path.py:42` | ... |

   **Tests:** <adequate / missing for X>
   **Acceptance criteria:** <met / not met: ...>
   ```

5. Do not comment on formatting or import order (CI's ruff job covers that). Do not
   approve or request changes via the review API — comments only; humans decide.
