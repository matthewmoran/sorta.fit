# Security Model

Sorta.Fit handles API credentials, spawns subprocesses, and writes temporary files throughout its polling lifecycle. This document describes the security boundaries, credential handling, file permission expectations, and hardening measures in the codebase.

## Credential Management

### API Tokens

Board API tokens (e.g., Jira personal access tokens) are stored in the `.env` file, which is gitignored. Tokens are never hardcoded in scripts.

- **`.env` permissions** --- On macOS/Linux, restrict the file to owner-only access after creation:
  ```bash
  chmod 600 .env
  ```
  On Windows, NTFS ACLs provide per-user isolation by default; no extra step is needed.

- **Adapter authentication** --- The Jira adapter (`adapters/jira.sh`) passes credentials via the `Authorization` HTTP header, not as command-line arguments. This prevents tokens from appearing in `ps` output or shell history:
  ```bash
  # Header-based auth (current)
  JIRA_AUTH_HEADER="Authorization: Basic $(echo -n "$BOARD_EMAIL:$BOARD_API_TOKEN" | base64 -w 0)"
  curl -H "$JIRA_AUTH_HEADER" ...
  ```

### Setup Wizard Credentials

The setup wizard (`setup/server.js`) handles credentials in its `/api/test-connection` and `/api/save-config` endpoints. Credentials are received over HTTP from the browser, used for a single API call, and written to `.env`. The wizard binds to `127.0.0.1` only --- it is not reachable from other machines.

All API endpoints require a session token (`X-Session-Token` header). A cryptographically random 256-bit token is generated on each wizard startup using `crypto.randomBytes(32)` and compared using `crypto.timingSafeEqual()` to prevent timing attacks. The token is printed to the terminal on startup and injected into the served HTML page automatically, so no manual copy-paste is needed. Unauthenticated requests to any `/api/*` endpoint receive a `401 Unauthorized` response.

## Input Validation

### Board Domain

`core/config.sh` validates `BOARD_DOMAIN` against a strict regex before it is used to construct API URLs:

```bash
if [[ ! "$BOARD_DOMAIN" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$ ]]; then
  echo "ERROR: Invalid BOARD_DOMAIN: $BOARD_DOMAIN"
  exit 1
fi
```

This rejects shell metacharacters (`;`, `$`, backticks, `#`, spaces) and prevents command injection through crafted domain values.

### Adapter Name

`core/config.sh` also validates `BOARD_ADAPTER` against an allowlist (`jira`, `linear`, `github-issues`) to prevent path traversal when sourcing adapter scripts.

### Setup Wizard Input

The `/api/save-config` endpoint validates the adapter name with `/^[a-z][a-z0-9-]*$/` before using it to construct file paths, preventing directory traversal. Static file serving in the wizard resolves paths and verifies they remain within the `setup/` directory.

## File Permissions and Temporary Files

### Temp Files

Runners and utilities create temporary files via `mktemp` for prompt content, Claude output, and API payloads. These files may contain card descriptions, implementation plans, or API response data. On most systems, `mktemp` creates files with mode `0600` by default (owner-read/write only), but this depends on the system's `umask`.

`core/loop.sh` sets `umask 077` at startup, immediately after `set -euo pipefail`. All temp files, logs, and lock directories created by runners during the polling cycle inherit restrictive permissions (`0700` for directories, `0600` for files) regardless of the system default.

Files created by runners:
| Runner | Temp files | Contents |
|--------|-----------|----------|
| `refine.sh` | `PROMPT_FILE`, `RESULT_FILE` | Rendered prompt, Claude output |
| `code.sh` | `PROMPT_FILE`, `RESULT_FILE`, `PR_BODY_FILE` | Rendered prompt, Claude output, PR markdown |
| `review.sh` | `PROMPT_FILE`, `RESULT_FILE` | Rendered prompt, review verdict |
| `triage.sh` | `PROMPT_FILE`, `RESULT_FILE` | Rendered prompt, triage analysis |
| `adapters/jira.sh` | `tmpfile`, `payload_file` | API response bodies, JSON payloads |
| `core/utils.sh` | `stderr_file` | Claude stderr output |

All temp files are cleaned up with `rm -f` after use, including in error paths.

### Log Files

The setup wizard writes runner output to `runner.log` in the project root via `fs.openSync(logPath, 'a')`. This log may contain board data echoed by runner scripts. On Unix-like systems, the wizard automatically sets the log file to mode `0600` (owner-read/write only) via `fs.chmodSync()` after opening. On Windows, NTFS ACLs provide per-user isolation by default.

### Lock Files

The polling loop uses a lock directory (`.automation.lock`) to prevent concurrent cycles. `core/utils.sh:lock_acquire()` uses `mkdir` for atomic acquisition --- `mkdir` is an atomic filesystem operation that fails if the directory already exists, avoiding the TOCTOU (time-of-check-time-of-use) race condition present in check-then-write patterns:

```bash
lock_acquire() {
  local lock_dir="$1"
  if mkdir "$lock_dir" 2>/dev/null; then
    echo $$ > "$lock_dir/pid"
    return 0
  fi
  # ... stale lock recovery
}
```

## Process Isolation

### Worktrees

The `code` runner executes Claude Code in isolated git worktrees (`.worktrees/<ISSUE_KEY>`), never in the main working tree. This prevents AI-generated changes from affecting the primary checkout or other in-flight work.

### Protected Branches

Runners never check out `main`, `master`, `dev`, or `develop`. All AI-created branches are prefixed `claude/{ISSUE_KEY}-{slug}`. The code runner explicitly checks branch names against a `PROTECTED_BRANCHES` list before proceeding. No runner performs `git push --force` or other destructive git operations.

### Environment Passthrough

The setup wizard spawns runner processes with a restricted environment built by `buildRunnerEnv()`. Only allowlisted variables are passed to child processes: keys matching specific prefixes (`BOARD_*`, `GIT_*`, `CLAUDE_*`, `RUNNER_*`, `MAX_CARDS_*`, `MAX_BOUNCES`) and exact names (`PATH`, `HOME`, `USER`, `LANG`, `TERM`, `POLL_INTERVAL`, `RUNNERS_ENABLED`, `MERGE_STRATEGY`, `TARGET_REPO`, `DOCS_DIR`, `DOCS_ORGANIZE_BY`). This prevents unintended credential leakage from the parent process environment.

## Checklist for Operators

- [ ] Set `chmod 600 .env` after creating or editing the file (macOS/Linux)
- [ ] Verify `.env` is listed in `.gitignore` (it is by default)
- [ ] Audit git history for accidentally committed secrets before making the repo public (`git log --all -p -- .env`)
- [x] Setup wizard API endpoints require a session token (enforced in code)
- [x] `runner.log` is created with `0600` permissions on Unix (enforced in code)
- [x] Runner child processes receive only allowlisted environment variables (enforced in code)
- [x] `umask 077` is set in `core/loop.sh` for all runner temp files (enforced in code)
- [ ] Rotate board API tokens periodically; revoke any tokens found in git history
