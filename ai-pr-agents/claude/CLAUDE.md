# Instructions for Claude

Claude reads this file automatically at the start of every run. The rules are split into
small files in `instructions/`. The `@` lines below include them.

@instructions/01-project-overview.md
@instructions/02-python-coding-rules.md
@instructions/03-testing-rules.md
@instructions/04-security-rules.md
@instructions/05-git-and-pr-rules.md
@instructions/06-databricks-notebooks.md

## What you have to work with

| Type | Where | What it is |
|---|---|---|
| Commands | `commands/` | Entry points such as `/implement 12` or `/review 6`. Each one says which skill to follow. |
| Skills | `skills/` | Step-by-step procedures (implement an issue, review a PR, run checks). |
| Agents | `agents/` | Specialist helpers you can hand a focused task to: `developer`, `test-writer`, `pr-reviewer`, `security-reviewer`. |
