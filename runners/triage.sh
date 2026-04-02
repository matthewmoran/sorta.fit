#!/usr/bin/env bash
# Runner: Triage — analyzes bug reports
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
source "$SORTA_ROOT/core/runner-lib.sh"

log_info "Triage: checking $RUNNER_TRIAGE_FROM lane for bugs..."

START_AT=0
SKIP_RETRIES=0

while true; do
ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_TRIAGE_FROM" "$MAX_CARDS_TRIAGE" "$START_AT")

if [[ -z "$ISSUE_IDS" ]]; then
  [[ "$START_AT" -eq 0 ]] && log_info "No cards in $RUNNER_TRIAGE_FROM to triage."
  break
fi

BATCH_PROCESSED=0

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }

  # Check type filter (defaults to Bug)
  if [[ -n "$RUNNER_TRIAGE_FILTER_TYPE" ]]; then
    CARD_TYPE=$(board_get_card_type "$ISSUE_KEY") || { log_warn "Failed to fetch type for $ISSUE_KEY. Skipping."; continue; }
    if ! matches_type_filter "$CARD_TYPE" "$RUNNER_TRIAGE_FILTER_TYPE"; then
      log_info "Skipping $ISSUE_KEY (type: $CARD_TYPE, filter: $RUNNER_TRIAGE_FILTER_TYPE)"
      continue
    fi
  fi

  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY") || { log_warn "Failed to fetch description for $ISSUE_KEY. Skipping."; continue; }
  log_step "Triaging: $ISSUE_KEY — $TITLE"

  PROMPT=$(render_template "$SORTA_ROOT/prompts/triage.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  claude_rc=0
  run_claude_safe "$PROMPT_FILE" "$RESULT_FILE" "" "${RUNNER_TRIAGE_AGENT:-$CLAUDE_AGENT}" || claude_rc=$?
  if [[ "$claude_rc" -eq 2 ]]; then break; fi
  if [[ "$claude_rc" -ne 0 ]]; then
    log_error "Claude failed for $ISSUE_KEY"
    continue
  fi

  TRIAGE=$(cat "$RESULT_FILE")
  rm -f "$PROMPT_FILE" "$RESULT_FILE"

  if [[ -z "$TRIAGE" ]]; then
    log_warn "Empty triage for $ISSUE_KEY. Skipping."
    continue
  fi

  # Append triage to existing description
  UPDATED_DESC="$DESCRIPTION

---
## Triage Analysis (Sorta)
$TRIAGE"

  board_update_description "$ISSUE_KEY" "$UPDATED_DESC"
  board_add_comment "$ISSUE_KEY" "Bug triaged by Sorta.Fit on $(date '+%Y-%m-%d %H:%M')."

  runner_transition "$ISSUE_KEY" "$RUNNER_TRIAGE_TO" "triaged"
  BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
done

[[ "$BATCH_PROCESSED" -gt 0 ]] && break
SKIP_RETRIES=$((SKIP_RETRIES + 1))
if [[ "$SKIP_RETRIES" -ge "$MAX_SKIP_RETRIES" ]]; then
  log_info "Reached max skip retries ($MAX_SKIP_RETRIES). Moving on."
  break
fi
START_AT=$((START_AT + MAX_CARDS_TRIAGE))
log_info "All cards skipped in batch. Fetching next batch (retry $SKIP_RETRIES/$MAX_SKIP_RETRIES)..."
done
