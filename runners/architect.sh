#!/usr/bin/env bash
# Runner: Architect — analyzes codebase and enriches refined specs with implementation plans
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

log_info "Architect: checking $RUNNER_ARCHITECT_FROM lane..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_ARCHITECT_FROM" "$MAX_CARDS_ARCHITECT")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_ARCHITECT_FROM. Nothing to architect."
  exit 0
fi

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

  (cd "$SORTA_ROOT" && claude -p "$(cat "$PROMPT_FILE")" > "$RESULT_FILE" 2>/dev/null) || {
    log_error "Claude failed for $ISSUE_KEY, skipping"
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  }

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

  if [[ -n "$RUNNER_ARCHITECT_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_ARCHITECT_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY architected and moved to $RUNNER_ARCHITECT_TO"
  else
    log_info "Done: $ISSUE_KEY architected (no transition configured)"
  fi
done
