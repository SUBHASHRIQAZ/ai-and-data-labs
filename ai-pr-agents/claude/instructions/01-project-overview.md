# Project overview

- This repository holds several independent Python projects, one per top-level folder
  (for example `ridepulse-databricks/`).
- Treat each folder as its own project, with its own `tests/` folder and its own
  `requirements.txt` or `tests/requirements.txt`.
- `ai-pr-agents/` is the automation that runs you. Do not change it unless the issue
  asks you to.
- Never commit data files: `*.csv`, `*.parquet`, `data/`, streaming `checkpoints/`.
