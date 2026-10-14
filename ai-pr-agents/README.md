# ai-pr-agents

This project uses Claude Code inside GitHub Actions to help with the everyday parts of working on this repo. I write an issue, and Claude writes the code and tests and opens a pull request. Every pull request also gets reviewed and checked automatically before I merge it.

I put this together after going through the Claude Code docs on [GitHub Actions](https://code.claude.com/docs/en/github-actions), [subagents](https://code.claude.com/docs/en/sub-agents), [slash commands](https://code.claude.com/docs/en/slash-commands) and [skills](https://code.claude.com/docs/en/skills). I wanted the instructions to live in normal Markdown files in the repo, where I can read and change them, instead of one huge prompt hidden inside a YAML file.

## A few terms first

If you're new to GitHub Actions or Claude Code, these are the words used throughout this page.

- An **issue** is a task written on GitHub, like "drop trips with a negative fare".
- A **pull request (PR)** is a set of code changes waiting to be reviewed and merged into `main`.
- **GitHub Actions** runs scripts on GitHub's own machines whenever something happens in the repo, like a new PR or a new comment. Each script is a **workflow**, saved as a `.yml` file.
- A **secret** is a value, like an API key, stored in the repo settings so it never appears in the code.
- **Claude Code** is Anthropic's coding agent. [claude-code-action](https://github.com/anthropics/claude-code-action) is the official action that runs it inside a workflow.

## What happens, step by step

1. I open an issue using the "Agent task" form and write down what I want and how I'll know it's done (the acceptance criteria).
2. I add the label `claude:implement` to the issue.
3. A workflow starts. Claude reads the issue, creates a branch, writes the code and tests, runs the checks and opens a PR linked to the issue.
4. Opening the PR starts two more workflows. One has Claude review the code and look for security problems, and it leaves its findings as comments. The other runs the normal tools: ruff for formatting and linting, pytest for tests, bandit and pip-audit for security, and gitleaks to catch passwords or keys committed by mistake.
5. If something needs fixing, I comment on the PR, for example `@claude /fix-review 7`, and Claude pushes a fix.
6. I read everything and merge it myself. Claude only leaves comments. It never approves a PR.

## Where the files are

The workflows are in `.github/workflows/` at the root of the repo, because that's the only place GitHub looks for them:

- `claude-implement-issue.yml` handles the label and any `@claude` comments
- `claude-pr-review.yml` runs the code review and the security review
- `pr-quality-checks.yml` runs ruff, pytest, bandit, pip-audit and gitleaks

Also in `.github/` are the issue form (`ISSUE_TEMPLATE/agent-task.yml`) and the PR description template (`pull_request_template.md`).

Everything Claude reads is in `ai-pr-agents/claude/`:

- `CLAUDE.md`
- `instructions/`
- `commands/`
- `skills/`
- `agents/`

The settings for ruff and bandit are in `ai-pr-agents/config/`.

Claude Code normally expects these files in a folder called `.claude/`. Folders starting with a dot are hidden in most file browsers, so I keep them in `ai-pr-agents/claude/`, where they're easy to find. Each workflow copies them into `.claude/` just before Claude starts.

## What the four folders mean

This was the part that took me longest to understand, so here it is in plain terms.

### instructions

These are the house rules. Claude follows them on every run, whatever the task. There's one small file for each topic: how I write Python, how tests should look, security rules, git and PR conventions, and how to edit Databricks notebooks without breaking them.

Claude Code automatically reads `CLAUDE.md` when it starts. That file just lists the rule files with lines like `@instructions/03-testing-rules.md`, which pulls each one in ([how imports work](https://code.claude.com/docs/en/memory)). If I want to change a testing rule, I open one short file and edit it.

### commands

A command is a saved prompt with a name. The file `commands/review.md` becomes `/review`. Anything typed after the name is put where the file says `$ARGUMENTS`, so `/review 7` means "review PR 7".

The workflows start Claude by running a command, and I can type the same commands in a GitHub comment. Each command file is only a few lines. It says what to do and which skill to follow. ([Slash commands docs](https://code.claude.com/docs/en/slash-commands))

### skills

A skill is a step-by-step recipe for one kind of job. For example, `implement-issue` says: read the issue, make a branch, write the code, write the tests, run the checks, commit, open the PR. Each skill is a `SKILL.md` file in its own folder.

The recipe lives in a skill rather than in a command so that more than one command can use it. `/check` and `/implement` both use the same `format-check` and `security-check` skills. ([Skills docs](https://code.claude.com/docs/en/skills))

### agents

An agent (also called a subagent) is a helper with one job. There are four: `developer` writes the code, `test-writer` writes and runs tests, `pr-reviewer` looks for bugs, and `security-reviewer` looks for security problems.

When a skill hands work to `test-writer`, that agent starts fresh and only thinks about tests. When it's done, it sends back a short summary. Each agent also has its own list of tools it's allowed to use. The two reviewers can read code but have no tool to edit it. ([Subagents docs](https://code.claude.com/docs/en/sub-agents))

### How they fit together

A workflow runs a command. The command points to a skill. The skill passes parts of the work to agents. All of them follow the instructions.

## Setting it up

You only need to do this once.

1. Get an API key from the [Anthropic Console](https://console.anthropic.com).
2. In the GitHub repo, go to Settings, then Secrets and variables, then Actions. Add a new repository secret called `ANTHROPIC_API_KEY` and paste the key. (From a terminal, `gh secret set ANTHROPIC_API_KEY` does the same thing.)
3. Install the [Claude GitHub App](https://github.com/apps/claude) and give it access to this repository only.
4. Go to Settings, then Actions, then General. Under "Workflow permissions", pick "Read and write permissions" and tick "Allow GitHub Actions to create and approve pull requests".
5. Create the label `claude:implement` (Issues, then Labels, then New label), or run `gh label create "claude:implement" --color 7057ff`.
6. Optional, but I'd recommend it: protect the `main` branch so a PR needs one approval and the quality checks have to pass before it can be merged.

The label and the `@claude` comments only start working once these workflow files are on `main`. GitHub always uses the version on the default branch for issue and comment events.

## Trying it out

1. Go to Issues, click New issue and pick "Agent task".
2. Fill it in. For example, set the project folder to `ridepulse-databricks` and the goal to "Drop trips with a negative fare in the silver layer". For acceptance criteria, write "Rows with fare_amount below 0 are removed" and "A test covers negative, zero and positive fares".
3. Add the `claude:implement` label.
4. Open the Actions tab to watch it run. It usually takes a few minutes.
5. When the PR shows up, read the review comments and check whether the quality checks passed.
6. If something needs changing, comment `@claude /fix-review <PR number>`, or just describe what you want in your own words.

The clearer the acceptance criteria, the better the result, because each one is meant to become a test.

## Things you can type in a comment

Only people with write access to the repo can trigger Claude.

- `@claude /implement 12` implements issue 12. It does the same as adding the label.
- `@claude /review 7` reviews PR 7 again.
- `@claude /security-review 7` runs the security review on PR 7 again.
- `@claude /fix-review 7` fixes the review comments on PR 7 and pushes the changes.
- `@claude /test` adds missing tests on the PR's branch.
- `@claude /check` runs the format, lint, test and security checks and fixes what fails.

Normal sentences work too, like `@claude rename clean_trips to filter_trips`.

## Changing how it behaves

- To change a coding, testing or security rule, edit the matching file in `claude/instructions/`. If you add a new rule file, add an `@instructions/<name>.md` line for it in `CLAUDE.md`.
- To make the reviews stricter or more relaxed, edit `claude/agents/pr-reviewer.md` or `claude/agents/security-reviewer.md`.
- To add your own command, create `claude/commands/<name>.md` with a short `description` at the top. You can then use it as `@claude /<name>`.
- To change the Claude model or limit how long a run can go on, change `--model` and `--max-turns` in the workflow files.
- To change the lint rules, edit `config/ruff.toml`.

Changes to the review instructions only take effect after they're merged into `main` (see the first point in the next section).

## Why I set it up this way

- The review jobs take their instructions from `main`, not from the PR being reviewed. Otherwise a PR could edit the reviewer's instructions and make itself look fine.
- The review jobs can't change code. They're only allowed to read files, look at the PR and post comments.
- The quality checks only look at files the PR changed. Some older notebooks in this repo don't match the current ruff settings, and I didn't want every new PR to fail because of code it didn't touch.
- Claude treats issue text as a description of the work, not as orders. If an issue asks it to change the workflows, secrets or this folder, it won't. The issue text is also never pasted into a shell command in the workflows.
- The Claude GitHub App is required, not just optional. A PR created with GitHub's built-in token [doesn't trigger other workflows](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication), so Claude's own PRs would never get reviewed or checked. The app's token doesn't have that problem.
- The notebooks are saved in Databricks source format. To a linter, `spark`, `dbutils` and `display` look like undefined names, so `ruff.toml` ignores that error in `notebooks/`. One of the instruction files also tells Claude to keep the `# MAGIC` and `# COMMAND ----------` lines.

## Problems I ran into

- The security review failed the first time it ran. That PR was the one adding `ai-pr-agents/`, so `main` didn't have the folder yet, and my fallback ended up copying the config folder onto itself. Now the job checks whether `main` has the folder before copying.
- Before the API key was added, the Claude jobs showed a green tick even though they hadn't done anything, because the action quietly skipped. Now every Claude job checks for the key first and fails with a clear message if it's missing.
- A plain `run:` step in GitHub Actions uses `bash -e`, while a step with `shell: bash` also turns on `pipefail`. The two behave differently when a command in a pipe fails, so I made sure my file-filtering commands work either way.

## Docs I used

- [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions) and the [claude-code-action repo](https://github.com/anthropics/claude-code-action)
- Claude Code [subagents](https://code.claude.com/docs/en/sub-agents), [slash commands](https://code.claude.com/docs/en/slash-commands), [skills](https://code.claude.com/docs/en/skills) and [memory / CLAUDE.md](https://code.claude.com/docs/en/memory)
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions)
- [Ruff](https://docs.astral.sh/ruff/), [Bandit](https://bandit.readthedocs.io/), [pip-audit](https://pypi.org/project/pip-audit/) and [gitleaks-action](https://github.com/gitleaks/gitleaks-action)
