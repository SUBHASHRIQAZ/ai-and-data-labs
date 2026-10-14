---
name: security-check
description: Scan changed code for vulnerabilities and secrets (bandit, pip-audit, gitleaks-style grep) and triage results. Use before opening a PR or when asked for a security check.
---

# Security check

```bash
pip install -q bandit pip-audit
FILES=$(git diff --name-only --diff-filter=ACMR origin/main...HEAD -- '*.py')

# 1. Static analysis (medium+ severity and confidence)
[ -n "$FILES" ] && bandit -ll -ii -c ai-pr-agents/config/bandit.yaml $FILES

# 2. Dependency vulnerabilities for any changed requirements file
for req in $(git diff --name-only origin/main...HEAD -- '*requirements*.txt'); do
  pip-audit -r "$req" --progress-spinner off
done

# 3. Secret patterns in the diff (CI also runs gitleaks on full history of the PR)
git diff origin/main...HEAD | grep -nEi \
  '(api[_-]?key|secret|token|password|passwd|access[_-]?key)\s*[:=]\s*["'"'"'][^"'"'"']{8,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|sk-ant-[A-Za-z0-9_-]{20,}|dapi[0-9a-f]{32}' \
  || echo "No secret patterns found"
```

Then delegate the scanner output and diff to the `security-reviewer` agent for triage
and manual review.

Rules:
- Fix every confirmed finding. For a false positive, add `# nosec <TEST_ID>` with a
  reason on the same line — only after the security-reviewer confirms it is false.
- If a real secret was committed, do not just delete it: flag it in the PR so the owner
  rotates it.
