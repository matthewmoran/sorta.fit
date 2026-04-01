#!/usr/bin/env bash
# Runner: Review — reviews PR diffs and posts feedback
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

log_info "Reviewer: checking $RUNNER_REVIEW_FROM lane..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_REVIEW_FROM" "$MAX_CARDS_REVIEW")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_REVIEW_FROM. Nothing to review."
  exit 0
fi

GH_CMD=$(find_gh)

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID")
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY")

  # Find PR URL in comments
  PR_URL=$(echo "$COMMENTS" | grep -oE 'https://github\.com/[^/]+/[^/]+/pull/[0-9]+' | head -1)

  if [[ -z "$PR_URL" ]]; then
    log_info "No PR URL found for $ISSUE_KEY. Skipping."
    continue
  fi

  # Check if already reviewed by Sorta.Fit
  if echo "$COMMENTS" | grep -q "Code Review —"; then
    log_info "$ISSUE_KEY already reviewed. Skipping."
    continue
  fi

  log_step "Reviewing: $ISSUE_KEY — $PR_URL"

  # Get PR diff
  PR_DIFF=$("$GH_CMD" pr diff "$PR_URL" 2>&1) || {
    log_error "Failed to get diff for $PR_URL"
    continue
  }

  if [[ -z "$PR_DIFF" ]]; then
    log_warn "Empty diff for $PR_URL. Skipping."
    continue
  fi

  # Truncate large diffs
  MAX_CHARS=100000
  if [[ ${#PR_DIFF} -gt $MAX_CHARS ]]; then
    log_warn "Diff too large (${#PR_DIFF} chars). Truncating."
    PR_DIFF="${PR_DIFF:0:$MAX_CHARS}

... [diff truncated] ..."
  fi

  # Build prompt
  PROMPT=$(render_template "$SORTA_ROOT/prompts/review.md" \
    CARD_KEY "$ISSUE_KEY" \
    PR_URL "$PR_URL" \
    PR_DIFF "$PR_DIFF")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  log_info "Running Claude for review..."
  (claude -p "$(cat "$PROMPT_FILE")" > "$RESULT_FILE" 2>/dev/null) || {
    log_error "Claude failed for review of $ISSUE_KEY"
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  }

  REVIEW=$(cat "$RESULT_FILE")
  rm -f "$PROMPT_FILE" "$RESULT_FILE"

  if [[ -z "$REVIEW" ]]; then
    log_warn "Empty review for $ISSUE_KEY. Skipping."
    continue
  fi

  # Parse verdict line from Claude's output
  REVIEW_EVENT="comment"
  VERDICT_LINE=$(echo "$REVIEW" | grep -oE '^VERDICT: (APPROVE|REQUEST_CHANGES)' | tail -1)
  if [[ "$VERDICT_LINE" == "VERDICT: APPROVE" ]]; then
    REVIEW_EVENT="approve"
  elif [[ "$VERDICT_LINE" == "VERDICT: REQUEST_CHANGES" ]]; then
    REVIEW_EVENT="request-changes"
  fi

  # Strip the verdict line from the review body before posting
  REVIEW=$(echo "$REVIEW" | sed '/^VERDICT: /d')

  # Post to GitHub
  log_info "Posting review ($REVIEW_EVENT) to $PR_URL..."
  REVIEW_BODY_FILE=$(mktemp)
  printf '%s' "$REVIEW" > "$REVIEW_BODY_FILE"

  "$GH_CMD" pr review "$PR_URL" --"$REVIEW_EVENT" --body-file "$REVIEW_BODY_FILE" 2>/dev/null || {
    log_warn "PR review failed. Falling back to comment."
    "$GH_CMD" pr comment "$PR_URL" --body-file "$REVIEW_BODY_FILE" 2>/dev/null || \
      log_error "Could not post review to $PR_URL"
  }
  rm -f "$REVIEW_BODY_FILE"

  # Post full review to card so board watchers see everything
  VERDICT_LABEL="Comment"
  if [[ "$REVIEW_EVENT" == "approve" ]]; then
    VERDICT_LABEL="Approved"
  elif [[ "$REVIEW_EVENT" == "request-changes" ]]; then
    VERDICT_LABEL="Changes Requested"
  fi

  board_add_comment "$ISSUE_KEY" "Code Review — $VERDICT_LABEL ($PR_URL)

$REVIEW"

  if [[ -n "$RUNNER_REVIEW_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_REVIEW_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Review complete for $ISSUE_KEY. Moved to $RUNNER_REVIEW_TO."
  else
    log_info "Review complete for $ISSUE_KEY. Card stays in $RUNNER_REVIEW_FROM."
  fi
done
