---
name: security-check
description: Runs bandit, pip-audit and a secret-pattern grep on changed code and triages the results. Use before opening a PR or when asked for a security check.
---

# Security check

```bash
pip install -q bandit pip-audit
FILES=$(git diff --name-only --diff-filter=ACMR origin/main...HEAD -- '*.py')

# bandit: medium severity and confidence and up
[ -n "$FILES" ] && bandit -ll -ii -c ai-pr-agents/config/bandit.yaml $FILES

# pip-audit for any requirements file that changed
for req in $(git diff --name-only origin/main...HEAD -- '*requirements*.txt'); do
  pip-audit -r "$req" --progress-spinner off
done

# quick secret grep on the diff (CI also runs gitleaks)
git diff origin/main...HEAD | grep -nEi \
  '(api[_-]?key|secret|token|password|passwd|access[_-]?key)\s*[:=]\s*["'"'"'][^"'"'"']{8,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|sk-ant-[A-Za-z0-9_-]{20,}|dapi[0-9a-f]{32}' \
  || echo "No secret patterns found"
```

Pass the output and the diff to the `security-reviewer` agent.

- Fix confirmed findings. Only add `# nosec <TEST_ID>` with a reason after the reviewer
  agrees it's a false positive.
- If a real secret was committed, flag it in the PR so it gets rotated.
