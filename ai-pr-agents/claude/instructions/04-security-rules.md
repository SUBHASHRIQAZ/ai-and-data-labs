# Security

- No secrets in code, notebooks or config. Use environment variables or a Databricks
  secret scope (`dbutils.secrets.get`).
- No `eval`/`exec`, no `subprocess(..., shell=True)`.
- No SQL assembled from user input or widget values with f-strings. Use parameters.
- No `verify=False`. Use `yaml.safe_load`, and don't unpickle anything you didn't write.
- Don't log or print personal data.
- If a secret has already been committed, say so in the PR. It needs rotating, not just
  deleting.
