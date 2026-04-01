#!/usr/bin/env bash
# Runner: Triage — analyzes bug reports
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

log_info "Triage: checking $RUNNER_TRIAGE_FROM lane for bugs..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_TRIAGE_FROM" "$MAX_CARDS_TRIAGE")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_TRIAGE_FROM to triage."
  exit 0
fi

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID")

  # Check type filter (defaults to Bug)
  if [[ -n "$RUNNER_TRIAGE_FILTER_TYPE" ]]; then
    CARD_TYPE=$(board_get_card_type "$ISSUE_KEY")
    if ! matches_type_filter "$CARD_TYPE" "$RUNNER_TRIAGE_FILTER_TYPE"; then
      log_info "Skipping $ISSUE_KEY (type: $CARD_TYPE, filter: $RUNNER_TRIAGE_FILTER_TYPE)"
      continue
    fi
  fi

  TITLE=$(board_get_card_title "$ISSUE_KEY")
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY")
  log_step "Triaging: $ISSUE_KEY — $TITLE"

  PROMPT=$(render_template "$SORTA_ROOT/prompts/triage.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  (claude -p "$(cat "$PROMPT_FILE")" > "$RESULT_FILE" 2>/dev/null) || {
    log_error "Claude failed for $ISSUE_KEY"
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  }

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

  if [[ -n "$RUNNER_TRIAGE_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_TRIAGE_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY triaged and moved to $RUNNER_TRIAGE_TO"
  else
    log_info "Done: $ISSUE_KEY triaged (no transition configured)"
  fi
done
