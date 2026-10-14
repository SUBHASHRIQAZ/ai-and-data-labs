---
description: Fix the review comments on a pull request and push the changes
argument-hint: <PR number>
---

Address the review comments on pull request #$ARGUMENTS.

1. Read every comment: `gh pr view $ARGUMENTS --comments`, and the inline comments with
   `gh api repos/{owner}/{repo}/pulls/$ARGUMENTS/comments`.
2. Fix each real problem on the PR's branch. If you disagree with a comment, don't change
   the code. Explain why in your reply instead.
3. Run the `/check` steps.
4. Commit, push, and reply on the PR with what you changed for each comment.
