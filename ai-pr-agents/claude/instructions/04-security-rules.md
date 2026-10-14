# Security rules

- Never put secrets in code, notebooks or config files (passwords, tokens, API keys,
  connection strings). Read them from environment variables or Databricks secret scopes.
- Don't use `eval` or `exec`.
- Don't use `subprocess` with `shell=True`.
- Don't build SQL by joining strings with user input. Use parameters.
- Don't turn off certificate checks (`verify=False`).
- Don't load untrusted data with `pickle` or `yaml.load` (use `yaml.safe_load`).
- Don't print or log personal data.
- If a real secret was ever committed, say so in the PR so the owner can rotate it.
  Deleting it from the file is not enough.
