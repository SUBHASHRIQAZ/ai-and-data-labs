# ai-pr-agents

A small setup that runs Claude Code inside GitHub Actions to handle the routine parts
of my workflow on this repo: turning an issue into a first-draft PR, reviewing PRs, and
running format, test and security checks.

I built it after reading through the Claude Code docs on
[GitHub Actions](https://code.claude.com/docs/en/github-actions),
[subagents](https://code.claude.com/docs/en/sub-agents),
[slash commands](https://code.claude.com/docs/en/slash-commands) and
[skills](https://code.claude.com/docs/en/skills). I wanted to see how far I could get
with plain Markdown instructions kept in the repo instead of long prompts buried in YAML.

## What it does

- **Issue to PR.** Label an issue `claude:implement` and a workflow runs Claude Code
  with the `/implement` command. It reads the issue, makes a branch, writes the change
  and tests, runs the checks and opens a PR that links back to the issue.
- **PR review.** Every non-draft PR gets two Claude jobs. One looks for bugs and
  missing tests, the other looks for security problems. Both post comments on the PR.
  Neither can edit code.
- **Quality checks.** A separate workflow with no AI in it runs ruff, pytest, bandit,
  pip-audit and gitleaks on the files the PR changed. These are the checks I'd make
  required before merging.
- **Follow-ups.** Commenting `@claude ...` on an issue or PR starts another run, for
  example `@claude /fix-review 7`.

I still review and merge everything myself. The AI review only comments; it never
approves.

## Layout

```
.github/
  workflows/
    claude-implement-issue.yml   issue label and @claude comments
    claude-pr-review.yml         code review + security review
    pr-quality-checks.yml        ruff, pytest, bandit, pip-audit, gitleaks
  ISSUE_TEMPLATE/agent-task.yml
  pull_request_template.md

ai-pr-agents/
  claude/
    CLAUDE.md          entry point, pulls in the files under instructions/
    instructions/      coding, testing, security, git and notebook rules
    commands/          /implement, /review, /security-review, /test, /check, /fix-review
    skills/            the step-by-step procedures the commands follow
    agents/            developer, test-writer, pr-reviewer, security-reviewer
  config/
    ruff.toml
    bandit.yaml
```

Claude Code looks for this material in a `.claude/` directory. I keep it in
`ai-pr-agents/claude/` so it's visible and grouped with the rest of the project, and
each workflow copies it into `.claude/` before starting Claude. The workflows have to
live in the root `.github/workflows/`, because that's the only place GitHub reads them
from.

### What each folder is for

**`instructions/`: the rules.** These are standing rules Claude follows on every run,
whatever it's working on: how I write Python, what a good test looks like, what counts
as a security problem, branch and commit conventions, and how to edit Databricks
notebooks without breaking them. `CLAUDE.md` is the file Claude Code loads
automatically at startup, and it pulls each rule file in with an
[`@` import](https://code.claude.com/docs/en/memory). Splitting them up means a change
to the testing rules touches one short file instead of one long prompt.

**`commands/`: the entry points.** A command is a reusable prompt that gets a name.
`commands/review.md` becomes `/review`, and whatever follows the name (a PR number,
say) is substituted wherever the file says `$ARGUMENTS`. The workflows start Claude by
running a command, and I can run the same commands myself in a `@claude` comment. They
stay short on purpose: they say what to do and which skill to follow, and nothing more.
See [slash commands](https://code.claude.com/docs/en/slash-commands).

**`skills/`: the procedures.** A skill is a step-by-step recipe for one kind of task,
like "implement an issue": read it, branch, write the code, test, check, commit, open a
PR. Each lives in its own folder as `SKILL.md`, with a `description` at the top that
tells Claude when it applies. Keeping the procedure here, rather than in the command,
lets several commands reuse it. `/check`, for example, uses the same `format-check`
and `security-check` skills as `/implement`.
See [skills](https://code.claude.com/docs/en/skills).

**`agents/`: the specialists.** An agent (subagent) is a helper with a single job, its
own instructions and its own list of allowed tools. When a skill hands work to
`test-writer`, that agent starts with a clean context focused only on testing, and
sends back a summary instead of filling the main conversation with every file it read.
The tool lists also act as guardrails: `pr-reviewer` and `security-reviewer` can read
code but have no tool to edit it.
See [subagents](https://code.claude.com/docs/en/sub-agents).

Put together, a run goes: the workflow starts a **command**, the command follows a
**skill**, the skill hands focused pieces to **agents**, and all of them follow the
**instructions**. Each layer is thin, so changing one behaviour means editing one
small file.

## Design decisions

**Reviewers load their instructions from `main`, not from the PR.** If the review job
used the PR's own copy of `ai-pr-agents/`, a PR could quietly weaken its own reviewer.
The review workflow checks out the base commit into a separate directory and copies the
instructions and scanner config from there.

**Review jobs are read-only.** Their `--allowedTools` list has no `Edit` or `Write`
tool, and their shell access is limited to `gh pr view/diff/comment`, `git diff/log`
and the scanners.

**Checks only look at changed files.** The repo has older notebooks that don't follow
the current ruff config. Running the formatter on everything would fail every PR on
code it didn't touch, so the `changes` job works out the changed `.py` files and the
project folders with a `tests/` directory, and the later jobs run on just those.

**Issue text is treated as untrusted.** Only people with write access can add labels
or trigger `@claude`, but the `/implement` command still tells Claude to ignore anything
in an issue that asks it to touch CI, secrets or this folder. Issue titles and bodies
are never put into a `run:` step.

**The Claude GitHub App token, not `GITHUB_TOKEN`.** A PR opened with the default
`GITHUB_TOKEN` [doesn't trigger other workflows](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication),
so a PR from the implement job would never get reviewed or checked. With the Claude
GitHub App installed, the action uses the app's token and the downstream workflows run
normally.

**Databricks notebooks need special handling.** The notebooks here are stored in
Databricks source format, so `spark`, `dbutils` and `display` look like undefined names
to a linter. `ruff.toml` ignores `F821` under `notebooks/`, and there's an instruction
file telling Claude to keep the `# MAGIC` and `# COMMAND ----------` lines intact.

## Setup

1. Create an API key in the [Anthropic Console](https://console.anthropic.com) and add
   it as the repository secret `ANTHROPIC_API_KEY`
   (`gh secret set ANTHROPIC_API_KEY`, or Settings > Secrets and variables > Actions).
2. Install the [Claude GitHub App](https://github.com/apps/claude) on this repository
   only.
3. Under Settings > Actions > General > Workflow permissions, select "Read and write
   permissions" and allow GitHub Actions to create pull requests.
4. Create the trigger label:
   `gh label create "claude:implement" --color 7057ff`
5. Optional: protect `main`, requiring one approval and the jobs from
   `PR quality checks`.

The label and comment triggers only work once the workflows are on the default branch.
GitHub runs `issues` and `issue_comment` workflows from there, not from feature
branches.

## Using it

Open an issue with the *Agent task* template. The acceptance criteria field matters
most, because each criterion is supposed to end up as at least one test. Then add the
`claude:implement` label and follow the run under the Actions tab.

Commands you can use in a comment:

```
@claude /implement 12          implement issue #12 (same as adding the label)
@claude /review 7              review PR #7 again
@claude /security-review 7     security review of PR #7 again
@claude /fix-review 7          address review comments on PR #7 and push
@claude /test                  add missing tests on the PR branch
@claude /check                 run format, lint, tests and security checks, then fix
```

Plain requests work too, for example `@claude rename clean_trips to filter_trips`.

## Customising

- **Coding, testing or security rules:** edit the relevant file in
  `claude/instructions/`. To add a new rule file, also add an `@instructions/<file>.md`
  line to `CLAUDE.md`.
- **Review focus:** edit `claude/agents/pr-reviewer.md` or `security-reviewer.md`.
- **New command:** add `claude/commands/<name>.md` with a `description` in the front
  matter. `$ARGUMENTS` is replaced with whatever follows the command.
- **Model and cost:** set `--model` and `--max-turns` in each workflow's `claude_args`.
  Draft PRs skip the Claude review, which helps when pushing lots of small commits.
- **Lint rules:** edit `config/ruff.toml`.

Changes to reviewer instructions only take effect after they're merged into `main`, for
the reason above.

## Things I ran into

- The first version of the security-review job failed on the PR that introduced it.
  `main` didn't have `ai-pr-agents/` yet, so the fallback path copied the config
  directory onto itself and `cp` exited with an error. The job now branches explicitly
  on whether the base copy exists.
- Without the API key secret, `claude-code-action` skipped its work and the job showed
  as passing, which was misleading. Each Claude job now starts by checking for the
  secret and fails with a clear message if it's missing.
- In GitHub Actions, a plain `run:` step uses `bash -e` without `pipefail`, but a step
  that declares `shell: bash` gets `pipefail` too. I wrote the file-filtering pipelines
  so they behave the same either way.

## References

- [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions) and the
  [claude-code-action repo](https://github.com/anthropics/claude-code-action)
- Claude Code [subagents](https://code.claude.com/docs/en/sub-agents),
  [slash commands](https://code.claude.com/docs/en/slash-commands),
  [skills](https://code.claude.com/docs/en/skills),
  [memory and CLAUDE.md](https://code.claude.com/docs/en/memory)
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions)
- [Ruff](https://docs.astral.sh/ruff/), [Bandit](https://bandit.readthedocs.io/),
  [pip-audit](https://pypi.org/project/pip-audit/),
  [gitleaks-action](https://github.com/gitleaks/gitleaks-action)
