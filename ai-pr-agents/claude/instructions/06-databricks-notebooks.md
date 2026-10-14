# Databricks notebooks

Files starting with `# Databricks notebook source` are notebooks exported in source
format. When editing them:

- keep that first line as is
- keep the `# COMMAND ----------` cell separators
- keep the `# MAGIC ` prefix on every line of `%md` and `%sql` cells, blank lines
  included
- don't import or define `spark`, `dbutils` or `display`; the runtime provides them
