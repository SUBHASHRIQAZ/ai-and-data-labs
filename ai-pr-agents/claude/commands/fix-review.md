---
description: Address review comments on a PR and push
argument-hint: <PR number>
---

Address the review comments on PR #$ARGUMENTS.

1. Read the conversation (`gh pr view $ARGUMENTS --comments`) and the inline comments
   (`gh api repos/{owner}/{repo}/pulls/$ARGUMENTS/comments`).
2. Fix the valid ones on the PR branch. Where you disagree, leave the code and explain
   in a reply.
3. Run `/check`.
4. Commit, push, and reply on the PR saying what changed for each comment.
