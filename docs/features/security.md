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

> **Note:** The wizard does not currently implement authentication on its own API endpoints. On shared machines, any local user could call `http://localhost:3456/api/load-config` to read the saved configuration. If the wizard will run on multi-user hosts, a session token or single-use auth mechanism should be added.

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

For defense-in-depth, callers should set restrictive permissions explicitly or ensure `umask 077` is active during runner execution.

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

The setup wizard writes runner output to `runner.log` in the project root via `fs.openSync(logPath, 'a')`. This log may contain board data echoed by runner scripts. The log file inherits default permissions from the OS; on shared systems, restrict it:

```bash
chmod 600 runner.log
```

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

The setup wizard spawns runner processes with `{ ...process.env }`, passing the full parent environment. This means any environment variables set in the wizard's process (including credentials loaded into memory) are inherited by child processes. This is functional but broad --- in hardened deployments, the spawn call should pass only the variables runners actually need (`BOARD_*`, `GIT_*`, `POLL_INTERVAL`, etc.).

## Checklist for Operators

- [ ] Set `chmod 600 .env` after creating or editing the file (macOS/Linux)
- [ ] Verify `.env` is listed in `.gitignore` (it is by default)
- [ ] Audit git history for accidentally committed secrets before making the repo public (`git log --all -p -- .env`)
- [ ] If running the setup wizard on a shared machine, restrict access to port 3456 or add authentication
- [ ] Review `runner.log` permissions if the setup wizard is used to start runners
- [ ] Rotate board API tokens periodically; revoke any tokens found in git history
