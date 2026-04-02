#!/usr/bin/env bash
# Runner: Bounce — moves rejected PRs back for rework
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

GH_CMD=$(find_gh)
MAX_BOUNCES="${MAX_BOUNCES:-3}"
BOUNCE_ESCALATE_TO="${RUNNER_BOUNCE_ESCALATE:-}"

log_info "Bounce: checking $RUNNER_BOUNCE_FROM lane for rejected PRs..."

START_AT=0
SKIP_RETRIES=0

while true; do
ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_BOUNCE_FROM" "$MAX_CARDS_BOUNCE" "$START_AT")

if [[ -z "$ISSUE_IDS" ]]; then
  [[ "$START_AT" -eq 0 ]] && log_info "No cards in $RUNNER_BOUNCE_FROM. Nothing to bounce."
  break
fi

BATCH_PROCESSED=0

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }
  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  # Find PR URL in comments
  PR_URL=$(echo "$COMMENTS" | grep -oE 'https://github\.com/[^/]+/[^/]+/pull/[0-9]+' | head -1)

  if [[ -z "$PR_URL" ]]; then
    log_info "No PR URL for $ISSUE_KEY. Skipping."
    continue
  fi

  # Count previous bounces
  BOUNCE_COUNT=$(echo "$COMMENTS" | grep -c "Bounced by Sorta" || true)

  # If already at max bounces, escalate instead of bouncing again
  if [[ "$BOUNCE_COUNT" -ge "$MAX_BOUNCES" ]]; then
    # Only escalate once — check if we already did
    if echo "$COMMENTS" | grep -q "Escalated by Sorta"; then
      log_info "$ISSUE_KEY already escalated. Skipping."
      continue
    fi

    log_warn "$ISSUE_KEY has bounced $BOUNCE_COUNT times (max: $MAX_BOUNCES). Escalating for human review."
    board_add_comment "$ISSUE_KEY" "Escalated by Sorta.Fit on $(date '+%Y-%m-%d %H:%M'). This card has been bounced $BOUNCE_COUNT times and needs human attention. PR: $PR_URL"

    if [[ -n "$BOUNCE_ESCALATE_TO" ]]; then
      local_transition="TRANSITION_TO_${BOUNCE_ESCALATE_TO}"
      board_transition "$ISSUE_KEY" "${!local_transition}"
      log_info "$ISSUE_KEY escalated to $BOUNCE_ESCALATE_TO"
    fi
    continue
  fi

  # Check the PR review state
  PR_STATE=$("$GH_CMD" pr view "$PR_URL" --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")

  CHANGES_REQUESTED=false
  if [[ "$PR_STATE" == "CHANGES_REQUESTED" ]]; then
    CHANGES_REQUESTED=true
  fi

  # If gh doesn't return reviewDecision, check reviews directly
  if [[ -z "$PR_STATE" || "$PR_STATE" == "null" ]]; then
    LATEST_REVIEW=$("$GH_CMD" pr view "$PR_URL" --json reviews --jq '.reviews[-1].state' 2>/dev/null || echo "")
    if [[ "$LATEST_REVIEW" == "CHANGES_REQUESTED" ]]; then
      CHANGES_REQUESTED=true
    fi
  fi

  if [[ "$CHANGES_REQUESTED" == false ]]; then
    log_info "$ISSUE_KEY: PR not rejected. Skipping."
    continue
  fi

  log_step "Bouncing: $ISSUE_KEY — $TITLE (attempt $((BOUNCE_COUNT + 1))/$MAX_BOUNCES)"

  # Get the review comments to include as context for the next code cycle
  REVIEW_COMMENTS=$("$GH_CMD" pr view "$PR_URL" --json reviews --jq '[.reviews[] | select(.state == "CHANGES_REQUESTED") | .body] | last' 2>/dev/null || echo "")

  BOUNCE_MSG="Bounced by Sorta.Fit on $(date '+%Y-%m-%d %H:%M') (attempt $((BOUNCE_COUNT + 1))/$MAX_BOUNCES). PR review requested changes."
  if [[ -n "$REVIEW_COMMENTS" && "$REVIEW_COMMENTS" != "null" ]]; then
    BOUNCE_MSG="$BOUNCE_MSG

Review feedback:
$REVIEW_COMMENTS"
  fi

  board_add_comment "$ISSUE_KEY" "$BOUNCE_MSG"

  if [[ -n "$RUNNER_BOUNCE_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_BOUNCE_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY bounced to $RUNNER_BOUNCE_TO for rework"
  else
    log_info "Done: $ISSUE_KEY bounced (no transition configured)"
  fi
  BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
done

[[ "$BATCH_PROCESSED" -gt 0 ]] && break
SKIP_RETRIES=$((SKIP_RETRIES + 1))
if [[ "$SKIP_RETRIES" -ge "$MAX_SKIP_RETRIES" ]]; then
  log_info "Reached max skip retries ($MAX_SKIP_RETRIES). Moving on."
  break
fi
START_AT=$((START_AT + MAX_CARDS_BOUNCE))
log_info "All cards skipped in batch. Fetching next batch (retry $SKIP_RETRIES/$MAX_SKIP_RETRIES)..."
done
