# AGENTS.md

This file provides guidance to AI agents (Claude Code, etc.) when working with code in this repository.

## Project Overview

Sorta.Fit is an AI-powered sprint automation system that connects issue boards (Jira, Linear, GitHub Issues) to Claude Code CLI. It runs a polling loop that reads cards from a board, renders prompt templates, and passes them to Claude Code for hands-off card refinement, implementation, PR review, and bug triage.

**Stack:** Python orchestration, Git, GitHub CLI, Claude Code CLI.

**Dependencies:** Python 3.10+, requests, cryptography, PyJWT.

## Running the System

```bash
# Start the polling loop
python run.py
python -m sortafit

# Validate configuration without running
python -m sortafit --validate

# Launch the setup wizard (web UI on port 3456)
python setup_wizard.py

# Install as editable package (for development)
pip install -e ".[dev]"
```

Runners are executed through the main polling loop and are not designed to be run individually. The loop loads configuration, creates the appropriate board adapter, and runs each enabled runner in sequence.

### Testing

```bash
pytest                           # Run all tests
pytest tests/unit/               # Run unit tests only
pytest tests/integration/        # Run integration tests only
pytest tests/ -v                 # Verbose output
```

Tests use [pytest](https://docs.pytest.org/) with pytest-mock and responses.

- **Unit tests** in `tests/unit/` -- test individual functions and classes in isolation
- **Integration tests** in `tests/integration/` -- test multi-module interactions (config loading pipeline, adapter validation, event logging)
- **Shared fixtures** in `tests/conftest.py` -- temp dir management, mock `.env` generation, test git repos

## Architecture

### Core Loop

`sortafit/loop.py` (`run_loop()`) -> loads config (`sortafit/config.py`) -> validates dependencies -> acquires `.automation.lock` -> runs enabled runners in sequence -> sleeps `POLL_INTERVAL` -> repeats. `sortafit/utils.py` provides logging, lock management, template rendering (`{{KEY}}` substitution), and git helpers.

### Adapter Layer

Adapters in `sortafit/adapters/` implement the `BoardAdapter` abstract base class (`sortafit/adapters/base.py`), making the system board-agnostic. Each adapter has a companion `*.config.sh` file (in `adapters/`) that stores an ID-driven mapping of statuses and transitions.

**Adapter config format** (`adapters/jira.config.sh`):
- `STATUS_<id>="Display Name"` -- maps Jira status IDs to human-readable names
- `TRANSITION_TO_<statusId>=<transitionId>` -- maps target status IDs to the transition ID needed to move a card there

**Interface** (`BoardAdapter` ABC):
- `get_cards_in_status(status, max_count, start_at)` -- returns issue IDs in the given status
- `get_card_key(issue_id)` -- returns the human-readable key (e.g., PROJ-123)
- `get_card_title(issue_key)` -- returns the title/summary
- `get_card_type(issue_key)` -- returns the issue type
- `get_card_description(issue_key)` -- returns description as markdown
- `get_card_comments(issue_key)` -- returns all comments as formatted text
- `update_description(issue_key, markdown)` -- replaces the card description
- `add_comment(issue_key, comment)` -- adds a comment
- `transition(issue_key, transition_id)` -- moves the card to a new status
- `discover()` -- discovers board statuses and transitions

Currently implemented: Jira Cloud (`sortafit/adapters/jira.py`), Linear (`sortafit/adapters/linear.py`), GitHub Issues (`sortafit/adapters/github_issues.py`).

### Runners

Each runner in `sortafit/runners/` extends `BaseRunner` (`sortafit/runners/base.py`) and follows the same pattern: query cards from a source lane -> fetch details -> render a prompt from `prompts/*.md` -> pass to Claude Code CLI via `run_claude()` -> update the board -> transition the card.

- **refine** -- Generates structured specs from raw cards (To Do -> Refined)
- **architect** -- Analyzes codebase architecture and produces implementation plans (Refined -> Architected)
- **code** -- Creates branch, worktree, runs Claude for implementation, opens PR (Agent -> QA)
- **review** -- Fetches PR diff, runs Claude review, posts verdict to GitHub (QA lane)
- **triage** -- Analyzes bug reports, appends root-cause analysis (To Do -> Refined)
- **bounce** -- Detects rejected PRs, routes back for rework or escalates after `MAX_BOUNCES` (QA -> Agent)
- **documenter** -- Generates/updates project docs from card specs in isolated worktrees, opens PR (configurable lanes)
- **merge** -- Merges approved PRs, transitions card to done (QA -> Done)

### Prompt Templates

`prompts/*.md` files use `{{KEY}}` placeholders (e.g., `{{CARD_KEY}}`, `{{CARD_TITLE}}`), rendered at runtime by `render_template()` in `sortafit/utils.py`.

## Code Conventions

- Python 3.10+ with type hints throughout
- PEP 8 style
- Use `dataclasses` for structured data (see `Config` in `sortafit/config.py`)
- Use ABC/abstractmethod for interfaces (see `BoardAdapter`)
- Logging via `log_info`, `log_warn`, `log_error`, `log_step` from `sortafit/utils.py` -- no bare `print()`
- UPPERCASE for env/exported variables, lowercase/snake_case for Python locals and functions
- No hardcoded values; use env vars and `Config` dataclass
- Git operations in runners use `subprocess.run(["git", "-C", repo_root, ...])` -- never bare `git`
- Claude execution in runners uses `run_claude_safe()` (or `run_claude()`) -- never call `claude -p` directly

## Safety Invariants

- The `code` and `documenter` runners use **isolated git worktrees** (`.worktrees/`); the main working tree is never modified
- Branches named `main`, `master`, `dev`, `develop` are **never checked out** by runners
- AI-created branches are always prefixed `claude/{ISSUE_KEY}-{slug}`
- No `git push --force` or destructive git operations
- `.automation.lock` prevents overlapping polling cycles

## Extension Points

- **New runner:** Create a new class in `sortafit/runners/{name}.py` extending `BaseRunner`, implement `process_card()`, add the prompt in `prompts/{name}.md`, register in `sortafit/loop.py`, add to `RUNNERS_ENABLED` in `.env`
- **New adapter:** Create `sortafit/adapters/{name}.py` implementing the `BoardAdapter` ABC + `adapters/{name}.config.sh.example`

## Configuration

All config lives in `.env` (see `.env.example`). Key variables: `BOARD_ADAPTER`, `BOARD_DOMAIN`, `BOARD_API_TOKEN`, `BOARD_PROJECT_KEY`, `TARGET_REPO`, `GIT_BASE_BRANCH`, `POLL_INTERVAL`, `RUNNERS_ENABLED`, and per-runner `MAX_CARDS_*` / `RUNNER_*_FROM` / `RUNNER_*_TO` lane routing.

Runner lane routing uses **Jira status IDs** (not names). `RUNNER_*_FROM` is the status ID to query cards from; `RUNNER_*_TO` is the status ID to transition cards to (resolved via `TRANSITION_TO_<id>` in the adapter config). Run the setup wizard to discover your board's IDs.
