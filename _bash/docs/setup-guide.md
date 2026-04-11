# Sorta.Fit -- Setup Guide

This guide covers manual setup for technical users who prefer working from the terminal rather than the setup wizard.

## Prerequisites

You will need the following installed before running Sorta:

| Tool | Version | Purpose | Install |
|------|---------|---------|---------|
| Git Bash | (bundled with Git) | Shell environment (required on Windows) | https://git-scm.com/downloads |
| Node.js | 18+ | Template rendering, JSON parsing | https://nodejs.org |
| Claude Code CLI | latest | AI-powered code generation | https://claude.ai/code |
| GitHub CLI (`gh`) | latest | PR creation, reviews | https://cli.github.com |
| curl | any | API requests to issue board | Included with Git Bash on Windows |

Verify everything is available:

```bash
git --version
node --version
claude --version
gh --version
curl --version
```

## Clone and Directory Structure

```bash
git clone https://github.com/matthewmoran/sorta.fit.git
cd Sorta.Fit
```

The project is organized as follows:

```
Sorta.Fit/
  core/
    config.sh         # Loads .env, validates required vars, sets defaults
    utils.sh          # Logging, slugify, render_template, find_gh, lock files
    loop.sh           # Main loop -- polls board, runs enabled runners
    runner-lib.sh     # Shared functions used across runners
  adapters/
    jira.sh           # Jira Cloud adapter (implements board_* interface)
    jira.config.sh.example  # Status/transition IDs template for Jira
  prompts/
    refine.md         # Prompt template for card refinement
    architect.md      # Prompt template for architecture planning
    code.md           # Prompt template for implementation
    review.md         # Prompt template for PR review
    triage.md         # Prompt template for bug triage
    documenter.md     # Prompt template for documentation generation
  runners/
    refine.sh         # To Do -> Refined
    architect.sh      # Refined -> Architected
    code.sh           # Agent -> branch -> PR -> QA
    review.sh         # QA -> PR review (card stays in QA)
    triage.sh         # Bug triage -> Refined
    bounce.sh         # QA -> Agent (rejected PRs)
    merge.sh          # QA -> Done (approved PRs)
    documenter.sh     # Generates/updates docs, opens PR
    release-notes.sh  # Manual: generate changelog from merged commits
  setup/
    server.js         # Setup wizard HTTP server (port 3456)
    index.html        # Setup wizard GUI
  docs/               # Documentation
    features/         # Auto-generated feature docs
  .env                # Your configuration (not committed)
  .env.example        # Template with all variables documented
```

## Creating .env

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` in your editor and configure the following variables:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `BOARD_ADAPTER` | Which issue board adapter to use | `jira` |
| `BOARD_DOMAIN` | Your board's domain (no protocol) | `mycompany.atlassian.net` |
| `BOARD_API_TOKEN` | API token for authentication | `ATATTx...` (Jira API token) |
| `BOARD_PROJECT_KEY` | The project key on your board | `PROJ` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_BASE_BRANCH` | `main` | The base branch for new feature branches |
| `POLL_INTERVAL` | `3600` | Seconds between polling cycles (3600 = 1 hour) |
| `MAX_CARDS_REFINE` | `5` | Maximum cards to refine per cycle |
| `MAX_CARDS_CODE` | `2` | Maximum cards to implement per cycle |
| `RUNNERS_ENABLED` | `refine,code` | Comma-separated list of runners to run |
| `TARGET_REPO` | (current git root) | Absolute path to the repository sorta.fit operates on |
| `MERGE_STRATEGY` | `merge` | How to merge PRs: `merge`, `squash`, or `rebase` |
| `GIT_RELEASE_BRANCH` | (empty) | Release branch for promotion PRs after merge |
| `MAX_SKIP_RETRIES` | `3` | Extra batches to fetch if all cards in a batch are skipped |
| `MAX_CARDS_ARCHITECT` | `5` | Maximum cards to architect per cycle |
| `MAX_CARDS_BOUNCE` | `10` | Maximum cards to check for bounces per cycle |
| `MAX_CARDS_MERGE` | `10` | Maximum cards to check for merge per cycle |
| `MAX_CARDS_DOCUMENTER` | `5` | Maximum cards to document per cycle |
| `DOCS_DIR` | `docs` | Target directory for generated documentation |
| `DOCS_ORGANIZE_BY` | `feature` | How to organize generated doc files |
| `BOARD_EMAIL` | (empty) | Your board account email (required for Jira) |

### Jira-Specific Notes

For Jira Cloud, `BOARD_API_TOKEN` is an API token generated at https://id.atlassian.com/manage-profile/security/api-tokens. The `BOARD_EMAIL` variable is required for Jira because authentication uses `email:token` as basic auth credentials.

## Setting Up Adapter Config

Each adapter needs a config file containing your board's status IDs and transition IDs. These are unique to your project's workflow.

### Step 1: Discover Your IDs

Run the board discovery command to list available statuses and transitions:

```bash
source core/config.sh
source core/utils.sh
source adapters/${BOARD_ADAPTER}.sh
board_discover
```

This will output something like:

```
=== Statuses ===
10000 - To Do
10070 - Refined
10069 - Agent
10001 - In Progress
10036 - QA
10002 - Done

=== Transitions (from first issue) ===
11 - To Do -> To Do
5 - Refine -> Refined
4 - Agent -> Agent
21 - In Progress -> In Progress
3 - QA -> QA
31 - Done -> Done
```

### Step 2: Create the Adapter Config

Copy the example and fill in the IDs from the discovery output:

```bash
cp adapters/jira.config.sh.example adapters/jira.config.sh
```

Edit `adapters/jira.config.sh` with the status and transition IDs matching your project. The file contains `STATUS_*` variables (used to query cards in each lane) and `TRANSITION_*` variables (used to move cards between lanes).

## Platform-Specific Notes

### Windows

Sorta must be run in Git Bash, not PowerShell or CMD. All scripts use bash syntax and Unix tools.

Configure Git to handle line endings correctly:

```bash
git config core.autocrlf input
```

This ensures files are stored with LF endings in the repository. If you encounter `\r` errors when running scripts, the line endings are wrong. Fix them:

```bash
git config core.autocrlf input
git rm --cached -r .
git reset --hard
```

The GitHub CLI (`gh`) may not be on the Git Bash PATH. Sorta handles this automatically by checking the default Windows install location (`/c/Program Files/GitHub CLI/gh.exe`).

### macOS / Linux

Make the scripts executable:

```bash
chmod +x core/*.sh adapters/*.sh runners/*.sh setup.sh
```

No other platform-specific configuration is needed.

## Running Manually

### Full Runner (Polling Loop)

Start the main loop, which polls the board and runs enabled runners in a loop:

```bash
bash core/loop.sh
```

The loop will:
1. Validate all dependencies (preflight check)
2. Run each enabled runner once immediately
3. Sleep for `POLL_INTERVAL` seconds
4. Repeat

Press Ctrl+C to stop. The loop uses a lock file (`.automation.lock`) to prevent overlapping cycles.

### Single Runner

Run any runner in isolation:

```bash
bash runners/refine.sh
bash runners/architect.sh
bash runners/code.sh
bash runners/review.sh
bash runners/triage.sh
bash runners/bounce.sh
bash runners/merge.sh
bash runners/documenter.sh
bash runners/release-notes.sh v1.0.0
```

Each runner sources the config, utils, and adapter on its own, so no prior setup is needed beyond a valid `.env` and adapter config.

## Troubleshooting

### Permission Denied

```
bash: ./core/runner.sh: Permission denied
```

On macOS/Linux, make scripts executable: `chmod +x core/*.sh runners/*.sh adapters/*.sh`. On Windows with Git Bash, use `bash core/loop.sh` (prefix with `bash`) instead of `./core/loop.sh`.

### Line Ending Errors

```
syntax error near unexpected token `$'\r''
```

Your files have Windows-style (CRLF) line endings. Fix with:

```bash
git config core.autocrlf input
git rm --cached -r .
git reset --hard
```

Or convert a single file: `sed -i 's/\r$//' core/loop.sh`

### Missing Dependencies

```
[ERROR] 'claude' is not installed.
```

The preflight check (`preflight_check` in `core/utils.sh`) validates that all required tools are on the PATH. Install whichever tool is reported missing using the URL shown in the error message.

### API Token Issues (Jira)

```
{"errorMessages":["Issue does not exist or you do not have permission"]}
```

Common causes:
- `BOARD_API_TOKEN` has expired or been revoked. Generate a new one.
- `BOARD_EMAIL` does not match the email associated with the API token.
- The token does not have permission to access the project specified in `BOARD_PROJECT_KEY`.
- `BOARD_DOMAIN` is wrong (it should be just the domain, e.g., `mycompany.atlassian.net`, not a full URL).

### Stale Lock File

```
[WARN] Previous cycle (PID 12345) still running. Skipping.
```

If the previous run crashed without cleaning up, a stale lock file remains. Remove it:

```bash
rm .automation.lock
```

### No Cards Found

If runners report "No cards in [lane]" but you see cards on your board:
- Verify the status names in your adapter config match exactly (case-sensitive).
- Run `board_discover` to confirm the correct status IDs.
- Ensure the cards are in the correct project (`BOARD_PROJECT_KEY`).

### Claude Failures

If Claude returns empty results or errors:
- Check that `claude --version` works from the terminal.
- Ensure you are authenticated with Claude Code (`claude` should open an interactive session).
- Large card descriptions may exceed context limits. Check the prompt template output for truncation.
