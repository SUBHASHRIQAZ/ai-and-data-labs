# AI PR agents: beginner guide

This folder makes Claude your **AI teammate on GitHub**:

1. You write a GitHub **issue** describing what you want.
2. You add a label, and Claude **writes the code and tests** and opens a **pull request** (PR).
3. Every PR, whether you or Claude wrote it, gets an **AI code review**, an
   **AI security review** and **automatic checks** (formatting, tests, security scanners).
4. You read the review, ask Claude for fixes if needed, and **you** merge.

You don't run anything on your computer. It all runs on GitHub.

---

## 1. Words you'll see

| Word | Meaning |
|---|---|
| **Issue** | A task written on GitHub ("Add X", "Fix Y"). |
| **Pull request (PR)** | A proposed code change you review before merging into `main`. |
| **GitHub Actions** | GitHub's robot. It runs scripts on its own computers when something happens in your repo. |
| **Workflow** | One robot script, a `.yml` file in `.github/workflows/`. |
| **Job / step** | A workflow is made of jobs, and each job is a list of steps run in order. |
| **Secret** | A password stored safely in GitHub settings, here your Anthropic API key. |
| **Instructions** | Rules Claude always follows (coding style, testing, security). |
| **Command** | A shortcut such as `/review 6`, written as a `.md` file. |
| **Skill** | A step-by-step recipe a command follows, for example "how to implement an issue". |
| **Agent** | A specialist helper with one job, for example `test-writer`. |

How they fit together:

```
Workflow (.yml)  ── starts Claude with ──▶  Command (/implement 12)
                                               │ follows
                                               ▼
                                            Skill (implement-issue)
                                               │ hands work to
                                               ▼
                                            Agents (developer, test-writer)
                                               │ always obey
                                               ▼
                                            Instructions (coding, testing, security rules)
```

---

## 2. Where everything is

```
ai-and-data-labs/
│
├── .github/                         ← GitHub only reads workflows from here
│   ├── workflows/
│   │   ├── claude-implement-issue.yml  label an issue → Claude opens a PR; "@claude …" replies
│   │   ├── claude-pr-review.yml        AI code review + AI security review on every PR
│   │   └── pr-quality-checks.yml       ruff, pytest, bandit, pip-audit, gitleaks (no AI)
│   ├── ISSUE_TEMPLATE/agent-task.yml   the form you fill in for a new task
│   └── pull_request_template.md        the sections every PR description has
│
└── ai-pr-agents/
    ├── README.md                    ← you are here
    ├── claude/                      ← everything Claude reads
    │   ├── CLAUDE.md                   main file: Claude reads it first; it includes instructions/
    │   ├── instructions/               RULES (edit these to change how Claude codes)
    │   │   ├── 01-project-overview.md
    │   │   ├── 02-python-coding-rules.md
    │   │   ├── 03-testing-rules.md
    │   │   ├── 04-security-rules.md
    │   │   ├── 05-git-and-pr-rules.md
    │   │   └── 06-databricks-notebooks.md
    │   ├── commands/                   COMMANDS (what you or the workflows ask for)
    │   │   ├── implement.md               /implement <issue>
    │   │   ├── review.md                  /review <PR>
    │   │   ├── security-review.md         /security-review <PR>
    │   │   ├── test.md                    /test
    │   │   ├── check.md                   /check
    │   │   └── fix-review.md              /fix-review <PR>
    │   ├── skills/                     RECIPES the commands follow
    │   │   ├── implement-issue/SKILL.md
    │   │   ├── review-pr/SKILL.md
    │   │   ├── write-tests/SKILL.md
    │   │   ├── format-check/SKILL.md
    │   │   └── security-check/SKILL.md
    │   └── agents/                     SPECIALIST HELPERS
    │       ├── developer.md               writes the code
    │       ├── test-writer.md             writes and runs tests
    │       ├── pr-reviewer.md             finds bugs in a PR
    │       └── security-reviewer.md       finds security problems
    └── config/                      ← settings for the check tools
        ├── ruff.toml                   formatting and lint rules
        └── bandit.yaml                 security scanner settings
```

**Why `claude/` and not `.claude/`?** Claude Code looks for its files in a folder called
`.claude/`. Folders that start with a dot are hidden in many file browsers, so the files
live in the visible `ai-pr-agents/claude/`. Each workflow copies them into `.claude/`
just before Claude starts.

---

## 3. One-time setup (about 10 minutes)

Do these once, in this order.

**Step 1: Get an Anthropic API key**
Go to https://console.anthropic.com → *API Keys* → *Create Key*. Copy it.

**Step 2: Save it as a GitHub secret**
In your repo on GitHub: *Settings* → *Secrets and variables* → *Actions* →
*New repository secret*.
- Name: `ANTHROPIC_API_KEY`
- Secret: paste the key

Or from a terminal: `gh secret set ANTHROPIC_API_KEY` (it asks you to paste the key).

**Step 3: Install the Claude GitHub App**
Open https://github.com/apps/claude → *Install* → choose **Only select repositories**
→ pick `ai-and-data-labs`. This lets Claude push branches and post comments.

**Step 4: Let workflows create PRs**
*Settings* → *Actions* → *General* → *Workflow permissions*:
- choose **Read and write permissions**
- tick **Allow GitHub Actions to create and approve pull requests**
- *Save*

**Step 5: Check the label exists**
*Issues* → *Labels*. You should see `claude:implement` (it's already been created). If it's
missing: `gh label create "claude:implement" --color 7057ff`.

**Step 6 (recommended): Protect `main`**
*Settings* → *Branches* → *Add branch protection rule* for `main`:
- Require a pull request before merging, with 1 approval
- Require status checks to pass, and pick the jobs from **PR quality checks**

---

## 4. Try it: your first run

1. **Open an issue.** *Issues* → *New issue* → **Agent task**. Fill it in, for example:
   - Project folder: `ridepulse-databricks`
   - Goal: *Drop trips with a negative fare in the silver layer.*
   - Acceptance criteria:
     `- [ ] Rows with fare_amount < 0 are removed`
     `- [ ] A test covers negative, zero and positive fares`
2. **Add the label** `claude:implement` to the issue.
3. **Watch it run:** *Actions* tab → *Claude · implement issue*. It takes a few minutes.
4. **A PR appears**, linked to your issue. The reviews and checks start on their own.
5. **Read the review comments** on the PR.
6. **Ask for changes** by commenting on the PR: `@claude /fix-review 7`
   (use your PR number).
7. When everything is ✅ and you're happy, **merge**.

Tip: the clearer your acceptance criteria, the better the result. Each one becomes a test.

---

## 5. Things you can type in a comment

Write these in any issue or PR comment. Only people with write access to the repo can
trigger Claude.

| Comment | What happens |
|---|---|
| `@claude /implement 12` | Implements issue #12 and opens a PR (same as adding the label) |
| `@claude /review 7` | Reviews PR #7 again |
| `@claude /security-review 7` | Runs the security review on PR #7 again |
| `@claude /fix-review 7` | Fixes the review comments on PR #7 and pushes |
| `@claude /test` | Writes missing tests on this PR's branch |
| `@claude /check` | Runs format, lint, tests and security checks, and fixes problems |
| `@claude <anything>` | Plain English works too: `@claude rename clean_trips to filter_trips` |

---

## 6. What happens during a run

Example: you add `claude:implement` to issue #12.

1. GitHub sees the "label added" event and starts `claude-implement-issue.yml`.
2. GitHub gives the job a **fresh Linux machine** and runs its steps in order:
   1. Stop with a clear error if `ANTHROPIC_API_KEY` is missing
   2. Download your repo
   3. Install Python, ruff, pytest, bandit, pip-audit
   4. Copy `ai-pr-agents/claude/` → `.claude/`
   5. Start Claude Code with the prompt *"Run the /implement command for issue 12"*
3. Claude reads `CLAUDE.md` and the rules it includes, then opens
   `commands/implement.md`, which points to the `implement-issue` skill.
4. Following the skill, Claude runs real terminal commands on that machine:
   `gh issue view 12`, `git checkout -b …`, then hands the coding to the `developer`
   agent and the tests to the `test-writer` agent, then runs `ruff`, `pytest`,
   `bandit`, `git push` and `gh pr create`.
5. The new PR triggers the review and check workflows the same way.

Claude can only use the tools listed in each workflow's `--allowedTools`. For example,
the review jobs have no Edit or Write tools, so a reviewer can't change your code.

---

## 7. Customising

| I want to… | Edit this |
|---|---|
| Change coding style rules | `claude/instructions/02-python-coding-rules.md` |
| Change testing rules | `claude/instructions/03-testing-rules.md` |
| Make the reviewer stricter or looser | `claude/agents/pr-reviewer.md` |
| Change the issue → PR steps | `claude/skills/implement-issue/SKILL.md` |
| Change lint rules | `config/ruff.toml` |
| Use a different Claude model | `--model` in the `.yml` files |
| Limit cost per run | `--max-turns` in the `.yml` files |

**Add a new rule file:** create `claude/instructions/07-my-rules.md`, then add the line
`@instructions/07-my-rules.md` to `claude/CLAUDE.md`.

**Add a new command:** create `claude/commands/<name>.md`:

```markdown
---
description: One line saying what it does
argument-hint: <PR number>
---

Do X for PR #$ARGUMENTS. Follow the `<skill-name>` skill.
```

Then use it with `@claude /<name> 7`. `$ARGUMENTS` is replaced by whatever you type
after the command.

**Add a new agent:** create `claude/agents/<name>.md` with `name`, `description` and
`tools` at the top (copy an existing agent file as a starting point).

**Note:** the review jobs load their instructions from `main`. A change to them affects
reviews only after it's merged, so a PR can't rewrite its own reviewer.

---

## 8. Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| ❌ *"ANTHROPIC_API_KEY is not set"* | The secret is missing | Setup step 2 |
| Added the label, nothing happened | Wrong label name, or the workflow isn't on `main` yet | The label must be exactly `claude:implement`; merge this setup first |
| Claude opened a PR but no reviews or checks ran | Claude GitHub App not installed | Setup step 3 |
| *"Resource not accessible by integration"* | Actions can't write | Setup step 4 |
| `format-lint` ❌ | Code isn't formatted | Click *Details*, or comment `@claude /check` |
| Run stopped with *max turns* | The task was too big for the step limit | Split the issue, or raise `--max-turns` |

To see what Claude did, go to the *Actions* tab → click the run → click the job →
expand **Claude implements the issue** (or the review step).

**Cost:** the Claude jobs use API credits on each run. The quality checks are free. To
spend less, use draft PRs while you're working (draft PRs aren't reviewed) and keep
issues small.
