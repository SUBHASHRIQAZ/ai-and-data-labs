# Python coding rules

- Python 3.11 or newer.
- Add type hints to public functions.
- Write docstrings only where the purpose isn't obvious from the name.
- Match the style of the file you are editing: naming, structure, comment density.
- Keep changes small and focused on the issue. No unrelated refactors.
- Put logic in small pure functions so it can be tested without Spark or a cluster.
  Keep reading and writing data (Spark, files, APIs) at the edges.
- Formatting and linting use `ruff` with `ai-pr-agents/config/ruff.toml`.
  Run `ruff format` and `ruff check --fix` on the files you changed.
- Don't add new libraries unless the issue needs them. If you add one, pin its version
  in the project's `requirements.txt`.
