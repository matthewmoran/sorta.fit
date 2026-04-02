#!/usr/bin/env bash
# Runner: Refine cards — generates structured specs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

log_info "Refiner: checking $RUNNER_REFINE_FROM lane..."

START_AT=0
SKIP_RETRIES=0

while true; do
ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_REFINE_FROM" "$MAX_CARDS_REFINE" "$START_AT")

if [[ -z "$ISSUE_IDS" ]]; then
  [[ "$START_AT" -eq 0 ]] && log_info "No cards in $RUNNER_REFINE_FROM. Nothing to refine."
  break
fi

BATCH_PROCESSED=0

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }

  # Check type filter
  if [[ -n "$RUNNER_REFINE_FILTER_TYPE" ]]; then
    CARD_TYPE=$(board_get_card_type "$ISSUE_KEY") || { log_warn "Failed to fetch type for $ISSUE_KEY. Skipping."; continue; }
    if ! matches_type_filter "$CARD_TYPE" "$RUNNER_REFINE_FILTER_TYPE"; then
      log_info "Skipping $ISSUE_KEY (type: $CARD_TYPE, filter: $RUNNER_REFINE_FILTER_TYPE)"
      continue
    fi
  fi

  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY") || { log_warn "Failed to fetch description for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  log_step "Refining: $ISSUE_KEY — $TITLE"

  PROMPT=$(render_template "$SORTA_ROOT/prompts/refine.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION" \
    CARD_COMMENTS "$COMMENTS")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  claude_rc=0
  run_claude "$PROMPT_FILE" "$RESULT_FILE" || claude_rc=$?
  if [[ "$claude_rc" -eq 2 ]]; then rm -f "$PROMPT_FILE" "$RESULT_FILE"; break; fi
  if [[ "$claude_rc" -ne 0 ]]; then
    log_error "Claude failed for $ISSUE_KEY, skipping"
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  fi

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
  BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
done

[[ "$BATCH_PROCESSED" -gt 0 ]] && break
SKIP_RETRIES=$((SKIP_RETRIES + 1))
if [[ "$SKIP_RETRIES" -ge "$MAX_SKIP_RETRIES" ]]; then
  log_info "Reached max skip retries ($MAX_SKIP_RETRIES). Moving on."
  break
fi
START_AT=$((START_AT + MAX_CARDS_REFINE))
log_info "All cards skipped in batch. Fetching next batch (retry $SKIP_RETRIES/$MAX_SKIP_RETRIES)..."
done
