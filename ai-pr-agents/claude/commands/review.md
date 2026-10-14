---
description: Review a pull request for bugs and missing tests, and post comments
argument-hint: <PR number>
---

Review pull request #$ARGUMENTS.

Follow the `review-pr` skill: read the PR and its linked issue, have the `pr-reviewer`
agent check the changes, then post inline comments plus one summary comment.

Focus on bugs, unmet acceptance criteria and missing tests. Skip formatting, because
ruff checks that.
