# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Sorta.Fit is an AI-powered sprint automation system that connects issue boards (Jira, Linear, GitHub Issues) to Codex CLI. It runs a polling loop that reads cards from a board, renders prompt templates, and passes them to Codex for hands-off card refinement, implementation, PR review, and bug triage.

**Stack:** Bash orchestration, Node.js (JSON/ADF parsing, template rendering), Git, GitHub CLI, Codex CLI.

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

Each runner in `runners/` follows the same pattern: query cards from a source lane → fetch details → render a prompt from `prompts/*.md` → pass to Codex CLI (`Codex -p`) → update the board → transition the card.

- **refine** — Generates structured specs from raw cards (To Do → Refined)
- **architect** — Analyzes codebase architecture and produces implementation plans (Refined → Architected)
- **code** — Creates branch, worktree, runs Codex for implementation, opens PR (Agent → QA)
- **review** — Fetches PR diff, runs Codex review, posts verdict to GitHub (QA lane)
- **triage** — Analyzes bug reports, appends root-cause analysis (To Do → Refined)
- **bounce** — Detects rejected PRs, routes back for rework or escalates after `MAX_BOUNCES` (QA → Agent)

### Prompt Templates

`prompts/*.md` files use `{{KEY}}` placeholders (e.g., `{{CARD_KEY}}`, `{{CARD_TITLE}}`), rendered at runtime by `render_template` in `core/utils.sh`.

## Code Conventions

- All scripts use `#!/usr/bin/env bash` and `set -euo pipefail`
- Logging via `log_info`, `log_warn`, `log_error`, `log_step` from `core/utils.sh` — no bare `echo`
- UPPERCASE for env/exported variables, lowercase for locals
- 2-space indentation, LF line endings only
- Allowed dependencies: Bash, Git, Node.js, curl, gh (GitHub CLI), Codex — no Python, jq, or other external tools
- No hardcoded values; use env vars and config

## Safety Invariants

- The `code` runner uses **isolated git worktrees** (`.worktrees/`); the main working tree is never modified
- Branches named `main`, `master`, `dev`, `develop` are **never checked out** by runners
- AI-created branches are always prefixed `Codex/{ISSUE_KEY}-{slug}`
- No `git push --force` or destructive git operations
- `.automation.lock` prevents overlapping polling cycles

## Extension Points

- **New runner:** Create `runners/{name}.sh` + `prompts/{name}.md`, add to `RUNNERS_ENABLED` in `.env`
- **New adapter:** Create `adapters/{name}.sh` implementing all `board_*` functions + `adapters/{name}.config.sh.example`

## Configuration

All config lives in `.env` (see `.env.example`). Key variables: `BOARD_ADAPTER`, `BOARD_DOMAIN`, `BOARD_API_TOKEN`, `BOARD_PROJECT_KEY`, `GIT_BASE_BRANCH`, `POLL_INTERVAL`, `RUNNERS_ENABLED`, and per-runner `MAX_CARDS_*` / `RUNNER_*_FROM` / `RUNNER_*_TO` lane routing.

Runner lane routing uses **Jira status IDs** (not names). `RUNNER_*_FROM` is the status ID to query cards from; `RUNNER_*_TO` is the status ID to transition cards to (resolved via `TRANSITION_TO_<id>` in the adapter config). Run the setup wizard to discover your board's IDs.
