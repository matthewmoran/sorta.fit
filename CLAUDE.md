# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sorta.Fit is an AI-powered sprint automation system that connects issue boards (Jira, Linear, GitHub Issues) to Claude Code CLI. It runs a polling loop that reads cards from a board, renders prompt templates, and passes them to Claude Code for hands-off card refinement, implementation, PR review, and bug triage.

**Stack:** Python orchestration, Git, GitHub CLI, Claude Code CLI.

**Dependencies:** Python 3.10+, requests, cryptography, PyJWT. Dev dependencies: pytest, pytest-mock, responses.

## Running the System

```bash
# Start the runner directly (no setup wizard)
python run.py

# Start via module
python -m sortafit

# Validate configuration without running
python -m sortafit --validate

# Launch the setup wizard (web UI on port 3456)
python setup_wizard.py

# Install as editable package (for development)
pip install -e ".[dev]"

# After installation, use entry points
sortafit               # run the polling loop
sortafit-setup         # launch the setup wizard
```

Runners are executed through the main polling loop and are not designed to be run individually. The loop loads configuration, creates the appropriate board adapter, and runs each enabled runner in sequence.

### Testing

```bash
pytest                           # Run all tests
pytest tests/unit/               # Run unit tests only
pytest tests/integration/        # Run integration tests only
pytest tests/ -v                 # Verbose output
pytest tests/unit/test_utils.py  # Run a specific test file
```

Tests use [pytest](https://docs.pytest.org/) with pytest-mock and responses.

- **Unit tests** in `tests/unit/` -- test individual functions and classes in isolation
- **Integration tests** in `tests/integration/` -- test multi-module interactions (config loading pipeline, adapter validation, event logging)
- **Shared fixtures** in `tests/conftest.py` -- temp dir management, mock `.env` generation, test git repos

## Architecture

### Core Loop

`sortafit/loop.py` (`run_loop()`) -> loads config (`sortafit/config.py`) -> acquires `.automation.lock` -> runs enabled runners in sequence -> sleeps `POLL_INTERVAL` -> repeats. `sortafit/utils.py` provides logging, lock management, template rendering (`{{KEY}}` substitution), and git helpers.

### Adapter Layer

Adapters in `sortafit/adapters/` implement the `BoardAdapter` abstract base class (`sortafit/adapters/base.py`), making the system board-agnostic. Each adapter has a companion `*.config.sh` file (in `adapters/`) that stores an ID-driven mapping of statuses and transitions, loaded by `sortafit/adapters/config_loader.py`.

**Adapter config format** (`adapters/jira.config.sh`):
- `STATUS_<id>="Display Name"` -- maps Jira status IDs to human-readable names
- `TRANSITION_TO_<statusId>=<transitionId>` -- maps target status IDs to the transition ID needed to move a card there

**Interface** (`BoardAdapter` ABC):
- `get_cards_in_status(status, max_count, start_at)` -- returns issue IDs in the given status
- `get_card_key(issue_id)` -- returns the human-readable key (e.g., PROJ-123)
- `get_card_title(issue_key)` -- returns the title/summary
- `get_card_type(issue_key)` -- returns the issue type (Bug, Story, Task, etc.)
- `get_card_description(issue_key)` -- returns description as markdown
- `get_card_comments(issue_key)` -- returns all comments as formatted text
- `update_description(issue_key, markdown)` -- replaces the card description
- `add_comment(issue_key, comment)` -- adds a comment to the card
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
- **release_notes** -- Generates release notes from merged cards

### Prompt Templates

`prompts/*.md` files use `{{KEY}}` placeholders (e.g., `{{CARD_KEY}}`, `{{CARD_TITLE}}`), rendered at runtime by `render_template()` in `sortafit/utils.py`.

### Key Modules

| Module | Purpose |
|---|---|
| `sortafit/config.py` | Configuration loading, `Config` dataclass, `.env` parsing |
| `sortafit/utils.py` | Logging (`log_info`, `log_warn`, `log_error`, `log_step`), lock management, template rendering, git helpers |
| `sortafit/runner_lib.py` | Shared runner functions: `runner_transition()`, `setup_worktree()`, `run_claude_safe()`, `check_pr_review_state()`, `extract_pr_url()` |
| `sortafit/runners/base.py` | `BaseRunner` ABC with the shared batch loop pattern |
| `sortafit/claude.py` | Claude Code CLI wrapper (`run_claude()`) |
| `sortafit/events.py` | Structured event logging (`log_event()`) |
| `sortafit/gh_auth.py` | GitHub App authentication and token refresh |
| `sortafit/adapters/config_loader.py` | Adapter config file parser |
| `sortafit/adapters/jira_adf.py` | Jira Atlassian Document Format (ADF) conversion |
| `sortafit/loop.py` | Main polling loop |
| `sortafit/__main__.py` | Entry point for `python -m sortafit` |

## Working on This Codebase

- **Do not guess at bug fixes.** When an error is reported, trace the exact code path, read the relevant code, and identify the root cause with evidence before making changes. For bug fixes, describe the proposed fix and wait for confirmation -- sometimes the initial direction is wrong and guessing creates new bugs that waste time undoing. For straightforward feature work, implementation can proceed without asking at each step.

### Test-Driven Development

All changes to core modules must follow TDD:

1. **Write or update tests first** -- before changing a function in `sortafit/`, update the corresponding test file in `tests/`
2. **Run tests** -- `pytest` must pass before opening a PR
3. **Keep tests current** -- when changing functionality, update tests to match. If a test needs to change, that change should be part of the same commit as the code change
4. **Test file mapping:**
   - `sortafit/utils.py` -> `tests/unit/test_utils.py` + `tests/unit/test_render_template.py`
   - `sortafit/config.py` -> `tests/unit/test_config.py`
   - `sortafit/runner_lib.py` -> `tests/unit/test_runner_lib.py`
   - `sortafit/events.py` -> `tests/unit/test_events.py`
   - `sortafit/adapters/jira_adf.py` -> `tests/unit/test_jira_adf.py`
   - `sortafit/gh_auth.py` -> `tests/unit/test_gh_auth.py`
   - `sortafit/adapters/jira.py` -> `tests/integration/test_adapter_validation.py`
   - `sortafit/adapters/linear.py` -> `tests/integration/test_linear_adapter.py`
   - `sortafit/adapters/github_issues.py` -> `tests/integration/test_github_issues_adapter.py`
   - `sortafit/config.py` (loading pipeline) -> `tests/integration/test_config_loading.py`
   - `sortafit/events.py` (integration) -> `tests/integration/test_event_logging.py`

## Shared Runner Library

`sortafit/runner_lib.py` provides shared functions used across runners. The `BaseRunner` class in `sortafit/runners/base.py` implements the common batch loop pattern -- all runners extend it.

Key functions in `runner_lib.py`:
- `runner_transition(issue_key, target_status, verb, config, adapter)` -- handles transition with guard check and logging
- `setup_worktree(issue_key, branch_name, config, worktree_base)` -- full worktree lifecycle (branch, create, settings, install)
- `run_claude_safe(prompt, result_file, work_dir)` -- wraps `run_claude` with temp file cleanup on failure
- `check_pr_review_state(pr_url, expected_state)` -- checks GitHub PR review decision
- `extract_pr_url(comments_text)` -- extracts GitHub PR URL from text

Key base class in `runners/base.py`:
- `BaseRunner` ABC -- implements the shared batch loop (fetch cards, process each, handle skip-retry logic)
- Subclasses override `process_card()` (and optionally `fetch_card_data()`) for runner-specific logic
- Raises `ClaudeRateLimited` when Claude returns exit code 2

## Code Conventions

- Python 3.10+ with type hints throughout
- PEP 8 style, enforced by standard tooling
- Use `dataclasses` for structured data (see `Config` in `sortafit/config.py`)
- Use ABC/abstractmethod for interfaces (see `BoardAdapter` in `sortafit/adapters/base.py`)
- Logging via `log_info`, `log_warn`, `log_error`, `log_step` from `sortafit/utils.py` -- no bare `print()`
- `log_warn` and `log_error` write to stderr; `log_info` and `log_step` write to stdout
- UPPERCASE for env/exported variables, lowercase/snake_case for Python locals and functions
- No hardcoded values; use env vars and `Config` dataclass
- Git operations in runners use `subprocess.run(["git", "-C", repo_root, ...])` -- never bare `git` -- so sorta.fit can operate on a separate repository
- Claude execution in runners uses `run_claude_safe()` (or `run_claude()`) -- never call `claude -p` directly via subprocess
- Imports: stdlib first, then third-party, then `sortafit.*` (standard Python convention)
- Use `from __future__ import annotations` when needed for forward references
- All modules include docstrings describing their purpose

## Safety Invariants

- The `code` and `documenter` runners use **isolated git worktrees** (`.worktrees/`); the main working tree is never modified
- Branches named `main`, `master`, `dev`, `develop` are **never checked out** by runners
- AI-created branches are always prefixed `claude/{ISSUE_KEY}-{slug}`
- No `git push --force` or destructive git operations
- `.automation.lock` prevents overlapping polling cycles
- Claude Code permissions are restricted via `.claude/settings.local.json` -- specific bash commands are allowlisted, destructive commands (`rm -rf`, `sudo`, `curl`, `git push --force`) are denylisted
- Prompts include **sensitive data rules** -- Claude must never hardcode secrets, log .env contents, or document internal URLs/credentials
- The Jira adapter validates API responses -- checks HTTP status and rejects HTML responses with a clear error instead of passing them to JSON parsing
- Write operations (`update_description`, `add_comment`, `transition`) suppress response output

## Extension Points

- **New runner:** Create a new class in `sortafit/runners/{name}.py` extending `BaseRunner`, implement `process_card()`, add the corresponding prompt template in `prompts/{name}.md`, register the runner in `sortafit/loop.py`, and add to `RUNNERS_ENABLED` in `.env`. See [`docs/writing-runners.md`](docs/writing-runners.md) for a complete step-by-step guide.
- **New adapter:** Create `sortafit/adapters/{name}.py` implementing the `BoardAdapter` ABC, add `adapters/{name}.config.sh.example`, and register it in `sortafit/loop.py` `create_adapter()`.
- **Setup wizard:** When adding a new runner, update the routing defaults and the `.env` template in the setup wizard.

## Configuration

All config lives in `.env` (see `.env.example`). Key variables: `BOARD_ADAPTER`, `BOARD_DOMAIN`, `BOARD_API_TOKEN`, `BOARD_PROJECT_KEY`, `TARGET_REPO`, `GIT_BASE_BRANCH`, `GIT_RELEASE_BRANCH`, `POLL_INTERVAL`, `RUNNERS_ENABLED`, `MERGE_STRATEGY`, `MAX_SKIP_RETRIES`, and per-runner `MAX_CARDS_*` / `RUNNER_*_FROM` / `RUNNER_*_TO` lane routing. The documenter runner also uses `DOCS_DIR` (target directory for generated docs, default `docs`) and `DOCS_ORGANIZE_BY` (organization strategy, default `feature`).

`TARGET_REPO` is the absolute path to the repository sorta.fit operates on. If not set, falls back to the current git root. This allows sorta.fit to live in a different directory from the project it automates.

Runner lane routing uses **Jira status IDs** (not names). `RUNNER_*_FROM` is the status ID to query cards from; `RUNNER_*_TO` is the status ID to transition cards to (resolved via `TRANSITION_TO_<id>` in the adapter config). Run the setup wizard to discover your board's IDs.

## Bash Backup

The original Bash/Node.js implementation is preserved in the `bash/` directory for reference. It contains the complete pre-conversion codebase including shell scripts, Node.js helpers, bats tests, and the original `CLAUDE.md` and `AGENTS.md`.
