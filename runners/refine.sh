#!/usr/bin/env bash
# Runner: Refine cards — generates structured specs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

log_info "Refiner: checking $RUNNER_REFINE_FROM lane..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_REFINE_FROM" "$MAX_CARDS_REFINE")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_REFINE_FROM. Nothing to refine."
  exit 0
fi

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID")

  # Check type filter
  if [[ -n "$RUNNER_REFINE_FILTER_TYPE" ]]; then
    CARD_TYPE=$(board_get_card_type "$ISSUE_KEY")
    if ! matches_type_filter "$CARD_TYPE" "$RUNNER_REFINE_FILTER_TYPE"; then
      log_info "Skipping $ISSUE_KEY (type: $CARD_TYPE, filter: $RUNNER_REFINE_FILTER_TYPE)"
      continue
    fi
  fi

  TITLE=$(board_get_card_title "$ISSUE_KEY")
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY")
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY")

  log_step "Refining: $ISSUE_KEY — $TITLE"

  PROMPT=$(render_template "$SORTA_ROOT/prompts/refine.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION" \
    CARD_COMMENTS "$COMMENTS")

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

  board_update_description "$ISSUE_KEY" "$(cat "$RESULT_FILE")"
  board_add_comment "$ISSUE_KEY" "Card refined by Sorta.Fit on $(date '+%Y-%m-%d %H:%M'). Review and move to Agent lane when ready."

  if [[ -n "$RUNNER_REFINE_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_REFINE_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY refined and moved to $RUNNER_REFINE_TO"
  else
    log_info "Done: $ISSUE_KEY refined (no transition configured)"
  fi

  rm -f "$PROMPT_FILE" "$RESULT_FILE"
done
