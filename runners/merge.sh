#!/usr/bin/env bash
# Runner: Merge — merges approved PRs and transitions cards to Done
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

GH_CMD=$(find_gh)

# Validate MERGE_STRATEGY
case "$MERGE_STRATEGY" in
  merge|squash|rebase) ;;
  *)
    log_error "Invalid MERGE_STRATEGY: $MERGE_STRATEGY (must be merge, squash, or rebase)"
    exit 1
    ;;
esac

log_info "Merge: checking $RUNNER_MERGE_FROM lane for approved PRs..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_MERGE_FROM" "$MAX_CARDS_MERGE")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_MERGE_FROM. Nothing to merge."
  exit 0
fi

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }
  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  # Find PR URL in comments
  PR_URL=$(echo "$COMMENTS" | grep -oE 'https://github\.com/[^/]+/[^/]+/pull/[0-9]+' | head -1)

  if [[ -z "$PR_URL" ]]; then
    log_info "$ISSUE_KEY: no PR URL in comments. Skipping."
    continue
  fi

  # Check PR review decision
  PR_STATE=$("$GH_CMD" pr view "$PR_URL" --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")

  APPROVED=false
  if [[ "$PR_STATE" == "APPROVED" ]]; then
    APPROVED=true
  fi

  # If gh doesn't return reviewDecision, check reviews directly
  if [[ -z "$PR_STATE" || "$PR_STATE" == "null" ]]; then
    LATEST_REVIEW=$("$GH_CMD" pr view "$PR_URL" --json reviews --jq '.reviews[-1].state' 2>/dev/null || echo "")
    if [[ "$LATEST_REVIEW" == "APPROVED" ]]; then
      APPROVED=true
    fi
  fi

  if [[ "$APPROVED" == false ]]; then
    log_info "$ISSUE_KEY: PR not approved. Skipping."
    continue
  fi

  log_step "Merging: $ISSUE_KEY — $TITLE (--$MERGE_STRATEGY)"

  MERGE_OUTPUT=$("$GH_CMD" pr merge "$PR_URL" --"$MERGE_STRATEGY" 2>&1) || {
    log_error "Merge failed for $ISSUE_KEY: $MERGE_OUTPUT"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit merge failed on $(date '+%Y-%m-%d %H:%M'). PR: $PR_URL. Error: $MERGE_OUTPUT"
    continue
  }

  board_add_comment "$ISSUE_KEY" "Merged by Sorta.Fit on $(date '+%Y-%m-%d %H:%M'). PR: $PR_URL ($MERGE_STRATEGY)"

  if [[ -n "$RUNNER_MERGE_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_MERGE_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY merged and moved to $RUNNER_MERGE_TO"
  else
    log_info "Done: $ISSUE_KEY merged (no transition configured)"
  fi

  # Promotion PR: if GIT_RELEASE_BRANCH is set and differs from GIT_BASE_BRANCH,
  # ensure an open PR exists from base → release branch
  if [[ -n "$GIT_RELEASE_BRANCH" && "$GIT_RELEASE_BRANCH" != "$GIT_BASE_BRANCH" ]]; then
    EXISTING_PR=$("$GH_CMD" pr list --base "$GIT_RELEASE_BRANCH" --head "$GIT_BASE_BRANCH" --json number --jq '.[0].number' 2>/dev/null || echo "")

    if [[ -z "$EXISTING_PR" || "$EXISTING_PR" == "null" ]]; then
      log_step "Opening promotion PR: $GIT_BASE_BRANCH → $GIT_RELEASE_BRANCH"
      PROMO_URL=$("$GH_CMD" pr create \
        --base "$GIT_RELEASE_BRANCH" \
        --head "$GIT_BASE_BRANCH" \
        --title "Promote $GIT_BASE_BRANCH → $GIT_RELEASE_BRANCH" \
        --body "Automated promotion PR created by Sorta.Fit on $(date '+%Y-%m-%d %H:%M')." 2>&1) || {
        log_warn "Failed to create promotion PR: $PROMO_URL"
      }
      if [[ -n "$PROMO_URL" && ! "$PROMO_URL" =~ ^Failed ]]; then
        log_info "Promotion PR opened: $PROMO_URL"
      fi
    fi
  fi
done
