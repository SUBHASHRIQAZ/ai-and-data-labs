# Databricks notebooks

A `.py` file whose first line is `# Databricks notebook source` is a Databricks
notebook saved as plain text. When you edit one:

- Keep the first line `# Databricks notebook source` exactly.
- Keep the `# COMMAND ----------` lines. They separate the cells.
- Keep the `# MAGIC ` prefix on every line of `%md` and `%sql` cells, including blank
  lines (`# MAGIC` on its own).
- `spark`, `dbutils` and `display` are provided by Databricks. Don't import or define them.
