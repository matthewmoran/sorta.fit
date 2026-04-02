#!/usr/bin/env bash
# Runner: Architect — analyzes codebase and enriches refined specs with implementation plans
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
source "$SORTA_ROOT/core/runner-lib.sh"

log_info "Architect: checking $RUNNER_ARCHITECT_FROM lane..."

START_AT=0
SKIP_RETRIES=0

while true; do
ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_ARCHITECT_FROM" "$MAX_CARDS_ARCHITECT" "$START_AT")

if [[ -z "$ISSUE_IDS" ]]; then
  [[ "$START_AT" -eq 0 ]] && log_info "No cards in $RUNNER_ARCHITECT_FROM. Nothing to architect."
  break
fi

BATCH_PROCESSED=0

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }

  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY") || { log_warn "Failed to fetch description for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  log_step "Architecting: $ISSUE_KEY — $TITLE"

  PROMPT=$(render_template "$SORTA_ROOT/prompts/architect.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION" \
    CARD_COMMENTS "$COMMENTS")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  claude_rc=0
  run_claude_safe "$PROMPT_FILE" "$RESULT_FILE" "" "${RUNNER_ARCHITECT_AGENT:-$CLAUDE_AGENT}" || claude_rc=$?
  if [[ "$claude_rc" -eq 2 ]]; then break; fi
  if [[ "$claude_rc" -ne 0 ]]; then
    log_error "Claude failed for $ISSUE_KEY, skipping"
    continue
  fi

  ARCH_PLAN=$(cat "$RESULT_FILE")
  rm -f "$PROMPT_FILE" "$RESULT_FILE"

  if [[ -z "$ARCH_PLAN" ]]; then
    log_warn "Empty architecture plan for $ISSUE_KEY. Skipping."
    continue
  fi

  UPDATED_DESC="$DESCRIPTION

---
## Architecture Plan (Sorta)
$ARCH_PLAN"

  board_update_description "$ISSUE_KEY" "$UPDATED_DESC"
  board_add_comment "$ISSUE_KEY" "Card architected by Sorta.Fit on $(date '+%Y-%m-%d %H:%M'). Ready for implementation."

  runner_transition "$ISSUE_KEY" "$RUNNER_ARCHITECT_TO" "architected"
  BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
done

[[ "$BATCH_PROCESSED" -gt 0 ]] && break
SKIP_RETRIES=$((SKIP_RETRIES + 1))
if [[ "$SKIP_RETRIES" -ge "$MAX_SKIP_RETRIES" ]]; then
  log_info "Reached max skip retries ($MAX_SKIP_RETRIES). Moving on."
  break
fi
START_AT=$((START_AT + MAX_CARDS_ARCHITECT))
log_info "All cards skipped in batch. Fetching next batch (retry $SKIP_RETRIES/$MAX_SKIP_RETRIES)..."
done
