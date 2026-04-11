# Writing New Runners

This guide walks through creating a new runner (board agent type) for Sorta.Fit. A runner is a bash script that reads cards from a board lane, processes them with Claude, and updates the board. By the end of this guide you will have a working runner integrated into the polling loop.

For reference while reading: `runners/refine.sh` is the simplest runner and `runners/code.sh` is the most complex. Both follow the same pattern described here.

---

## Runner Anatomy

Every runner follows a 6-step pattern:

1. **Source dependencies** — load config, utilities, and the board adapter
2. **Query the board** — fetch card IDs from the source lane
3. **Fetch card details** — get title, description, comments for each card
4. **Render the prompt** — fill a Markdown template with card data
5. **Call Claude CLI** — pass the rendered prompt to `claude -p`
6. **Update the board and transition** — write results back and move the card

### Skeleton Runner

Below is a fully annotated skeleton. Replace `example` with your runner's name throughout.

```bash
#!/usr/bin/env bash
# Runner: Example — one-line description of what this runner does
set -euo pipefail

# ── Step 1: Source dependencies ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"    # loads .env, sets defaults, validates
source "$SORTA_ROOT/core/utils.sh"     # logging, render_template, run_claude
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"  # board_* functions

# ── Step 2: Query the board ──────────────────────────────────────────────────────────
# RUNNER_EXAMPLE_FROM is the status ID to read from (set in .env)
# MAX_CARDS_EXAMPLE caps how many cards to process per cycle
log_info "Example: checking $RUNNER_EXAMPLE_FROM lane..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_EXAMPLE_FROM" "$MAX_CARDS_EXAMPLE")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_EXAMPLE_FROM. Nothing to do."
  exit 0
fi

# ── Step 3–6: Process each card ──────────────────────────────────────────────────────
for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID")

  # Optional: skip cards that don't match a type filter
  if [[ -n "${RUNNER_EXAMPLE_FILTER_TYPE:-}" ]]; then
    CARD_TYPE=$(board_get_card_type "$ISSUE_KEY")
    if ! matches_type_filter "$CARD_TYPE" "$RUNNER_EXAMPLE_FILTER_TYPE"; then
      log_info "Skipping $ISSUE_KEY (type: $CARD_TYPE, filter: $RUNNER_EXAMPLE_FILTER_TYPE)"
      continue
    fi
  fi

  # ── Step 3: Fetch card details ─────────────────────────────────────────────────────
  TITLE=$(board_get_card_title "$ISSUE_KEY")
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY")
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY")

  log_step "Processing: $ISSUE_KEY — $TITLE"

  # ── Step 4: Render the prompt ──────────────────────────────────────────────────────
  # render_template replaces {{KEY}} placeholders in prompts/example.md
  PROMPT=$(render_template "$SORTA_ROOT/prompts/example.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION" \
    CARD_COMMENTS "$COMMENTS")

  # ── Step 5: Call Claude CLI ────────────────────────────────────────────────────────
  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  (cd "$SORTA_ROOT" && claude -p "$(cat "$PROMPT_FILE")" > "$RESULT_FILE" 2>/dev/null) || {
    log_error "Claude failed for $ISSUE_KEY, skipping"
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  }

  if [[ ! -s "$RESULT_FILE" ]]; then
    log_error "Empty response for $ISSUE_KEY, skipping"
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  fi

  # ── Step 6: Update the board and transition ────────────────────────────────────────
  # Choose how to write results back:
  #   board_update_description — replaces the card's description
  #   board_add_comment        — appends a comment to the card
  board_update_description "$ISSUE_KEY" "$(cat "$RESULT_FILE")"
  board_add_comment "$ISSUE_KEY" "Processed by Sorta.Fit example runner on $(date '+%Y-%m-%d %H:%M')."

  # Transition the card if RUNNER_EXAMPLE_TO is configured
  if [[ -n "$RUNNER_EXAMPLE_TO" ]]; then
    # Indirect variable lookup: TRANSITION_TO_<statusId> holds the transition ID
    local_transition="TRANSITION_TO_${RUNNER_EXAMPLE_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY processed and moved to $RUNNER_EXAMPLE_TO"
  else
    log_info "Done: $ISSUE_KEY processed (no transition configured)"
  fi

  rm -f "$PROMPT_FILE" "$RESULT_FILE"
done
```

---

## Prompt Templates

Each runner has a companion prompt file in `prompts/`. The template is a Markdown file with `{{KEY}}` placeholders that get replaced at runtime by `render_template`.

### Skeleton Prompt Template

Create `prompts/example.md`:

```markdown
You are analyzing issue {{CARD_KEY}}.

## Card Details

**Title:** {{CARD_TITLE}}

**Description:**
{{CARD_DESCRIPTION}}

**Comments:**
{{CARD_COMMENTS}}

## Instructions

Analyze this card and produce a structured output.

## Output Format

Return ONLY the following sections. No preamble.

## Analysis
[Your analysis here]

## Recommendation
[Your recommendation here]
```

### Available Placeholders

The placeholders you can use depend on what your runner passes to `render_template`. Common placeholders used across existing runners:

| Placeholder | Source | Used by |
|---|---|---|
| `{{CARD_KEY}}` | `board_get_card_key` | all runners |
| `{{CARD_TITLE}}` | `board_get_card_title` | refine, code, triage |
| `{{CARD_DESCRIPTION}}` | `board_get_card_description` | refine, code, triage |
| `{{CARD_COMMENTS}}` | `board_get_card_comments` | refine, code |
| `{{BRANCH_NAME}}` | generated in runner | code |
| `{{BASE_BRANCH}}` | `GIT_BASE_BRANCH` env var | code |
| `{{PR_URL}}` | extracted from comments | review |
| `{{PR_DIFF}}` | `gh pr diff` | review |

You can define any custom placeholders — just pass matching key/value pairs to `render_template`:

```bash
PROMPT=$(render_template "$SORTA_ROOT/prompts/example.md" \
  CARD_KEY "$ISSUE_KEY" \
  CARD_TITLE "$TITLE" \
  MY_CUSTOM_FIELD "$some_value")
```

### Tips for Prompt Templates

- Be explicit about the output format. Include exact section headings so the output can be parsed or consumed reliably.
- End with a directive like "Output ONLY the report. No preamble." to keep Claude's response clean.
- The prompt is rendered by `render_template` in `core/utils.sh`, which uses Node.js for safe string replacement (handles special characters in card content).

---

## .env Configuration

Each runner needs configuration variables in `.env` (with defaults set in `core/config.sh`).

### Required Variables

| Variable | Purpose | Example |
|---|---|---|
| `RUNNER_{NAME}_FROM` | Status ID of the lane to read cards from | `10000` |
| `RUNNER_{NAME}_TO` | Status ID to transition cards to (empty = no transition) | `10070` |
| `MAX_CARDS_{NAME}` | Maximum cards to process per polling cycle | `5` |

### Optional Variables

| Variable | Purpose | Example |
|---|---|---|
| `RUNNER_{NAME}_FILTER_TYPE` | Comma-separated card types to include (empty = all) | `Bug,Defect` |

### Registering in RUNNERS_ENABLED

Add the runner name to the comma-separated `RUNNERS_ENABLED` list in `.env`:

```bash
RUNNERS_ENABLED=refine,code,example
```

The polling loop (`core/loop.sh`) parses this list and runs `runners/{name}.sh` for each entry.

### Adding Defaults to core/config.sh

Register your runner's variables with defaults in `core/config.sh` so the system works even when they are not explicitly set in `.env`:

```bash
export RUNNER_EXAMPLE_FROM="${RUNNER_EXAMPLE_FROM:-}"
export RUNNER_EXAMPLE_TO="${RUNNER_EXAMPLE_TO:-}"
export RUNNER_EXAMPLE_FILTER_TYPE="${RUNNER_EXAMPLE_FILTER_TYPE:-}"
export MAX_CARDS_EXAMPLE="${MAX_CARDS_EXAMPLE:-5}"
```

### Finding Status IDs

Status IDs are board-specific. To discover them:

- Run the setup wizard (`bash setup.sh`) and use the board discovery UI, or
- Call `board_discover` directly:
  ```bash
  bash -c "source core/config.sh && source adapters/jira.sh && board_discover"
  ```

This prints all available statuses and transitions with their numeric IDs.

---

## Board Adapter Interface

Runners interact with the board exclusively through `board_*` functions defined in `adapters/{adapter}.sh`. This abstraction means your runner works with any supported board (Jira, Linear, GitHub Issues) without code changes.

### Functions

| Function | Parameters | Returns | Purpose |
|---|---|---|---|
| `board_get_cards_in_status` | status_id, max_count | Issue IDs (one per line) | Query cards in a lane |
| `board_get_card_key` | issue_id | Key (e.g., `PROJ-42`) | Convert internal ID to display key |
| `board_get_card_type` | issue_key | Type name (e.g., `Story`) | Get the card's issue type |
| `board_get_card_title` | issue_key | Title text | Get the card's title/summary |
| `board_get_card_description` | issue_key | Plain text | Get the card's description body |
| `board_get_card_comments` | issue_key | Formatted comments | Get all comments with author and date |
| `board_update_description` | issue_key, markdown | — | Replace the card's description |
| `board_add_comment` | issue_key, comment_text | — | Append a comment to the card |
| `board_transition` | issue_key, transition_id | — | Move the card to a new status |
| `board_discover` | — | Printed output | List all statuses and transitions |

### Transition Lookup Pattern

`board_transition` takes a **transition ID**, not a status ID. The mapping from target status ID to transition ID is stored in `adapters/{adapter}.config.sh` as `TRANSITION_TO_<statusId>=<transitionId>`.

Runners resolve this with bash indirect variable expansion:

```bash
# RUNNER_EXAMPLE_TO contains a status ID, e.g., "10070"
# TRANSITION_TO_10070 contains the transition ID, e.g., "5"
local_transition="TRANSITION_TO_${RUNNER_EXAMPLE_TO}"
board_transition "$ISSUE_KEY" "${!local_transition}"
```

The `${!var}` syntax evaluates the variable whose name is stored in `$var`. This is the standard pattern used by all existing runners.

---

## Utility Functions

`core/utils.sh` provides shared helpers that every runner should use.

### Logging

| Function | Color | Use for |
|---|---|---|
| `log_info` | Green | Normal progress messages |
| `log_warn` | Yellow | Non-fatal issues (skipped cards, missing optional config) |
| `log_error` | Red | Failures (Claude errors, API errors) |
| `log_step` | Blue | Per-card progress (starting to process a card) |

Never use bare `echo` for status output. All output should go through these functions.

### Template Rendering

```bash
render_template "path/to/template.md" KEY1 "value1" KEY2 "value2"
```

Replaces every `{{KEY1}}` in the template file with `value1`, and so on. Uses Node.js internally for safe string replacement.

### Claude Execution

For simpler runners, call Claude directly as shown in the skeleton. For runners that need rate-limit awareness, use `run_claude`:

```bash
run_claude "$PROMPT_FILE" "$RESULT_FILE" "$WORKING_DIR" "$AGENT"
# Returns: 0 = success, 1 = failure, 2 = rate limited
```

The 4th argument is an optional agent name. When set, `--agent <name>` is appended to the `claude -p` invocation. Runners resolve the agent using `"${RUNNER_<NAME>_AGENT:-$CLAUDE_AGENT}"` — this uses the per-runner agent if configured, falling back to the global default. Pass `""` for the 3rd argument (working directory) if you don't need a custom working directory but do need to pass an agent.

For runners that need temp file cleanup on failure, use `run_claude_safe` instead — it accepts the same arguments but removes prompt and result files when Claude returns non-zero.

Check rate-limit status before starting a cycle with `is_rate_limited`.

See [Custom Claude Agents](features/custom-agents.md) for full configuration details.

### Other Helpers

- `slugify "some text"` — converts text to a branch-safe slug (lowercase, hyphens, max 40 chars)
- `matches_type_filter "Bug" "Bug,Defect"` — returns 0 if the type is in the filter list
- `lock_acquire` / `lock_release` — managed by `core/loop.sh`, not typically used in runners directly

---

## Code Conventions

All runner scripts must follow these rules:

| Rule | Convention |
|---|---|
| Shebang | `#!/usr/bin/env bash` |
| Strict mode | `set -euo pipefail` immediately after the shebang/comment |
| Logging | Use `log_info`, `log_warn`, `log_error`, `log_step` — no bare `echo` |
| Variables | UPPERCASE for env/exported variables, lowercase for locals |
| Indentation | 2 spaces, no tabs |
| Line endings | LF only (Unix). Set `git config core.autocrlf input` on Windows |
| Dependencies | Only bash, git, node, curl, gh, claude — no Python, jq, or other tools |
| Hardcoded values | None. Use env vars and adapter config for all board-specific values |
| Quoting | Always quote variable expansions: `"$var"`, not `$var` |
| File-level comment | Include a comment after the shebang explaining the script's purpose |

---

## Checklist: Adding a New Runner

Use this checklist when creating a runner named `{name}`:

| # | Action | File |
|---|---|---|
| 1 | Create the runner script following the 6-step pattern | `runners/{name}.sh` |
| 2 | Create the prompt template with `{{KEY}}` placeholders | `prompts/{name}.md` |
| 3 | Add default variables (`RUNNER_{NAME}_FROM`, `RUNNER_{NAME}_TO`, `MAX_CARDS_{NAME}`) | `core/config.sh` |
| 4 | Add runner configuration values (status IDs, card limits) | `.env` |
| 5 | Add the runner name to `RUNNERS_ENABLED` | `.env` |
| 6 | Document the runner (lane flow, config, placeholders) | `docs/runners.md` |

### Verification

After creating a runner:

1. Syntax-check the script: `bash -n runners/{name}.sh`
2. Create a test card on your board in the source lane.
3. Run the runner standalone: `bash runners/{name}.sh`
4. Verify the card was processed and (if configured) transitioned.
5. Add the runner to `RUNNERS_ENABLED` and run `bash core/loop.sh` to confirm it loads in the polling loop without errors.

---

## Examples to Study

- **`runners/refine.sh`** — The simplest runner. Reads cards, renders a prompt, writes results back to the description, transitions the card. Start here to understand the basic pattern.
- **`runners/code.sh`** — The most complex runner. Adds git worktree management, branch creation, dependency installation, PR creation via `gh`, and multi-step error handling. Study this when your runner needs to interact with git or external tools beyond the board.
- **`runners/triage.sh`** — Demonstrates type filtering (`RUNNER_TRIAGE_FILTER_TYPE`) and appending to (rather than replacing) the card description.
- **`runners/review.sh`** — Shows how to extract data from card comments (PR URLs), interact with GitHub CLI, and skip already-processed cards.
