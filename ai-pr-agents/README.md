# AI PR agents

A GitHub-native workflow that turns GitHub issues into reviewed pull requests, using
[Claude Code GitHub Actions](https://github.com/anthropics/claude-code-action) driven
by version-controlled **instructions**, **skills** and **subagents**.

```
 Issue (agent-task template)
   │  label: claude:implement
   ▼
 claude-implement-issue.yml ── implement-issue skill
   │     developer agent → test-writer agent → format-check → security-check
   ▼
 Pull request ──────────────┬─ pr-quality-checks.yml   (deterministic gates)
                            │    ruff format · ruff lint · pytest · bandit · pip-audit · gitleaks
                            └─ claude-pr-review.yml    (AI review)
                                 code-review job  → pr-reviewer agent
                                 security-review  → security-reviewer agent
   │  "@claude fix the review comments"
   ▼
 claude-implement-issue.yml (interactive job) pushes fixes → checks rerun → human merges
```

## Layout

| Path | Purpose |
|---|---|
| `claude/CLAUDE.md` | Shared instructions: repo layout, Python standards, workflow rules |
| `claude/agents/` | Subagents: `developer`, `test-writer`, `pr-reviewer`, `security-reviewer` |
| `claude/skills/` | Skills: `implement-issue`, `write-tests`, `review-pr`, `format-check`, `security-check` |
| `config/ruff.toml` | Format + lint rules (Databricks-notebook aware) |
| `config/bandit.yaml` | Security scanner config |
| `../.github/workflows/` | The three workflows (GitHub only runs workflows from the repo root) |
| `../.github/ISSUE_TEMPLATE/agent-task.yml` | Issue form with acceptance criteria |

Each workflow copies `ai-pr-agents/claude/` to `.claude/` before running Claude, so
skills and agents are discovered exactly as they are in local Claude Code. The review
workflows copy them from the **base** branch so a PR cannot rewrite its own reviewer.

## One-time setup

1. **Install the Claude GitHub App** on the repo: run `/install-github-app` in Claude
   Code, or install https://github.com/apps/claude. The app's token is what lets the
   PRs Claude opens trigger the review and check workflows (PRs opened with the default
   `GITHUB_TOKEN` don't trigger other workflows).
2. **Add the secret** `ANTHROPIC_API_KEY` under *Settings → Secrets and variables → Actions*.
3. **Allow Actions to create PRs**: *Settings → Actions → General → Workflow permissions →*
   "Read and write" + "Allow GitHub Actions to create and approve pull requests".
4. **Create the label**:
   `gh label create "claude:implement" --color 7057ff --description "Claude implements this issue"`
5. **Branch protection** on `main`: require PR, require the `PR quality checks` jobs to pass,
   require 1 human approval. The AI review comments; it never approves.

## Usage

- **New work** – open an issue with the *Agent task* template, then add the
  `claude:implement` label. Claude opens a PR linked to the issue.
- **Iterate** – comment `@claude <request>` on the PR or issue (only users with write
  access can trigger it).
- **Review any PR** – opening or pushing to a non-draft PR runs the code and security
  review automatically, plus the quality checks.

## Customising

- Model / cost: change `--model` and `--max-turns` in each workflow's `claude_args`.
- Standards: edit `claude/CLAUDE.md` — every agent reads it.
- Lint strictness: edit `config/ruff.toml`. Checks run only on changed files, so you can
  tighten rules without reformatting the whole repo.
- New stack: add a skill under `claude/skills/<name>/SKILL.md` and reference it from
  `CLAUDE.md`.
