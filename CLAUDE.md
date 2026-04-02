# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sorta.Fit is an AI-powered sprint automation system that connects issue boards (Jira, Linear, GitHub Issues) to Claude Code CLI. It runs a polling loop that reads cards from a board, renders prompt templates, and passes them to Claude Code for hands-off card refinement, implementation, PR review, and bug triage.

**Stack:** Bash orchestration, Node.js (JSON/ADF parsing, template rendering), Git, GitHub CLI, Claude Code CLI.

## Running the System

```bash
# Start the runner directly (no setup wizard)
bash run.sh            # macOS/Linux
run.bat                # Windows (double-click)

# Start the polling loop (core entry point)
bash core/loop.sh

# Run a single runner manually
bash runners/refine.sh
bash runners/code.sh
bash runners/review.sh
bash runners/triage.sh
bash runners/bounce.sh
bash runners/merge.sh

# Generate release notes (manual, not part of the loop)
bash runners/release-notes.sh <since-tag-or-date> [output-file]

# Launch the setup wizard (web UI on port 3456)
bash setup.sh          # macOS/Linux
setup.bat              # Windows (double-click)
```

There is no automated test suite. Testing is manual: create a test project on the board and run runners individually.

## Architecture

### Core Loop

`core/loop.sh` → loads config (`core/config.sh`) → validates dependencies → acquires `.automation.lock` → runs enabled runners in sequence → sleeps `POLL_INTERVAL` → repeats. `core/utils.sh` provides logging, lock management, template rendering (`{{KEY}}` substitution via Node.js), and git helpers.

### Adapter Layer

Adapters in `adapters/` implement a standard `board_*` function interface, making the system board-agnostic. Each adapter has a companion `*.config.sh` that stores an ID-driven mapping of statuses and transitions.

**Adapter config format** (`adapters/jira.config.sh`):
- `STATUS_<id>="Display Name"` — maps Jira status IDs to human-readable names
- `TRANSITION_TO_<statusId>=<transitionId>` — maps target status IDs to the transition ID needed to move a card there

**Interface:** `board_get_cards_in_status` (takes status ID), `board_get_card_key`, `board_get_card_title`, `board_get_card_description`, `board_get_card_comments`, `board_update_description`, `board_add_comment`, `board_transition` (takes transition ID), `board_discover`.

Currently implemented: Jira Cloud (`adapters/jira.sh`). Linear and GitHub Issues are planned.

### Runners

Each runner in `runners/` follows the same pattern: query cards from a source lane → fetch details → render a prompt from `prompts/*.md` → pass to Claude Code CLI (`claude -p`) → update the board → transition the card.

- **refine** — Generates structured specs from raw cards (To Do → Refined)
- **architect** — Analyzes codebase architecture and produces implementation plans (Refined → Architected)
- **code** — Creates branch, worktree, runs Claude for implementation, opens PR (Agent → QA)
- **review** — Fetches PR diff, runs Claude review, posts verdict to GitHub (QA lane)
- **triage** — Analyzes bug reports, appends root-cause analysis (To Do → Refined)
- **bounce** — Detects rejected PRs, routes back for rework or escalates after `MAX_BOUNCES` (QA → Agent)
- **documenter** — Generates/updates project docs from card specs in isolated worktrees, opens PR (configurable lanes)
- **merge** — Merges approved PRs, transitions card to done (QA → Done)

### Prompt Templates

`prompts/*.md` files use `{{KEY}}` placeholders (e.g., `{{CARD_KEY}}`, `{{CARD_TITLE}}`), rendered at runtime by `render_template` in `core/utils.sh`.

## Working on This Codebase

- **Do not guess at bug fixes.** When an error is reported, trace the exact code path, read the relevant code, and identify the root cause with evidence before making changes. For bug fixes, describe the proposed fix and wait for confirmation — sometimes the initial direction is wrong and guessing creates new bugs that waste time undoing. For straightforward feature work, implementation can proceed without asking at each step.

## Shared Runner Library

`core/runner-lib.sh` provides shared functions used across runners. **All runners must source it** after `utils.sh` and the adapter:

```bash
source "$SORTA_ROOT/core/runner-lib.sh"
```

Key functions:
- `runner_transition <issue_key> <target_status> <verb>` — handles transition with guard check and logging
- `setup_worktree <issue_key> <branch_name> <repo_root> <worktree_dir>` — full worktree lifecycle (branch, create, settings, npm install). **Returns the worktree path via stdout** — all log output inside this function MUST go to stderr (`>&2`) so it doesn't get captured by `$()`.
- `run_claude_safe <prompt_file> <result_file> [work_dir]` — wraps `run_claude` with temp file cleanup on failure
- `check_pr_review_state <pr_url> <expected_state>` — checks GitHub PR review decision
- `extract_pr_url <comments_text>` — extracts GitHub PR URL from text

When adding shared functions that return values via stdout, **always redirect log output to stderr** to avoid polluting the captured output.

## Code Conventions

- All scripts use `#!/usr/bin/env bash` and `set -euo pipefail`
- Logging via `log_info`, `log_warn`, `log_error`, `log_step` from `core/utils.sh` — no bare `echo`
- `log_warn` and `log_error` write to stderr; `log_info` and `log_step` write to stdout — be aware of this when capturing output with `$()`
- UPPERCASE for env/exported variables, lowercase for locals
- Do not use `local` outside of functions — runner scripts run as top-level processes, not functions, and `local` will error
- 2-space indentation, LF line endings only
- Allowed dependencies: Bash, Git, Node.js, curl, gh (GitHub CLI), claude — no Python, jq, or other external tools
- No hardcoded values; use env vars and config
- Git operations in runners use `git -C "$REPO_ROOT"` or `git -C "$TARGET_REPO"` — never bare `git` — so sorta.fit can operate on a separate repository
- Claude execution in runners uses `run_claude_safe` (or `run_claude`) — never call `claude -p` directly

## Safety Invariants

- The `code` and `documenter` runners use **isolated git worktrees** (`.worktrees/`); the main working tree is never modified
- Branches named `main`, `master`, `dev`, `develop` are **never checked out** by runners
- AI-created branches are always prefixed `claude/{ISSUE_KEY}-{slug}`
- No `git push --force` or destructive git operations
- `.automation.lock` prevents overlapping polling cycles
- Claude Code permissions are restricted via `.claude/settings.local.json` — specific bash commands are allowlisted, destructive commands (`rm -rf`, `sudo`, `curl`, `git push --force`) are denylisted
- Prompts include **sensitive data rules** — Claude must never hardcode secrets, log .env contents, or document internal URLs/credentials
- The Jira adapter (`jira_curl`) validates API responses — checks HTTP status and rejects HTML responses with a clear error instead of passing them to JSON.parse
- Write operations (`board_update_description`, `board_add_comment`, `board_transition`) suppress response output to `/dev/null`

## Extension Points

- **New runner:** Create `runners/{name}.sh` + `prompts/{name}.md`, source `runner-lib.sh`, use shared functions (`runner_transition`, `run_claude_safe`, etc.), add to `RUNNERS_ENABLED` in `.env`. See [`docs/writing-runners.md`](docs/writing-runners.md) for a complete step-by-step guide.
- **New adapter:** Create `adapters/{name}.sh` implementing all `board_*` functions + `adapters/{name}.config.sh.example`
- **Setup wizard:** When adding a new runner, update three places: `RUNNER_DEFS` array in `setup/index.html`, the routing defaults, and the `.env` template in `setup/server.js` `handleSaveConfig`

## Configuration

All config lives in `.env` (see `.env.example`). Key variables: `BOARD_ADAPTER`, `BOARD_DOMAIN`, `BOARD_API_TOKEN`, `BOARD_PROJECT_KEY`, `TARGET_REPO`, `GIT_BASE_BRANCH`, `GIT_RELEASE_BRANCH`, `POLL_INTERVAL`, `RUNNERS_ENABLED`, `MERGE_STRATEGY`, `MAX_SKIP_RETRIES`, and per-runner `MAX_CARDS_*` / `RUNNER_*_FROM` / `RUNNER_*_TO` lane routing. The documenter runner also uses `DOCS_DIR` (target directory for generated docs, default `docs`) and `DOCS_ORGANIZE_BY` (organization strategy, default `feature`).

`TARGET_REPO` is the absolute path to the repository sorta.fit operates on. If not set, falls back to the current git root. This allows sorta.fit to live in a different directory from the project it automates.

Runner lane routing uses **Jira status IDs** (not names). `RUNNER_*_FROM` is the status ID to query cards from; `RUNNER_*_TO` is the status ID to transition cards to (resolved via `TRANSITION_TO_<id>` in the adapter config). Run the setup wizard to discover your board's IDs.
