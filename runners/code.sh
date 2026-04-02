#!/usr/bin/env bash
# Runner: Code — implements cards in isolated worktrees
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
source "$SORTA_ROOT/core/runner-lib.sh"

WORKTREE_DIR="$SORTA_ROOT/.worktrees"

log_info "Coder: checking $RUNNER_CODE_FROM lane..."

REPO_ROOT="$TARGET_REPO"

log_info "Fetching latest $GIT_BASE_BRANCH..."
git -C "$REPO_ROOT" fetch origin "$GIT_BASE_BRANCH" 2>/dev/null || {
  log_error "Could not fetch origin/$GIT_BASE_BRANCH"
  exit 1
}

GH_CMD=$(find_gh)

START_AT=0
SKIP_RETRIES=0

while true; do
ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_CODE_FROM" "$MAX_CARDS_CODE" "$START_AT")

if [[ -z "$ISSUE_IDS" ]]; then
  [[ "$START_AT" -eq 0 ]] && log_info "No cards in $RUNNER_CODE_FROM. Nothing to code."
  break
fi

BATCH_PROCESSED=0

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }
  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY") || { log_warn "Failed to fetch description for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  log_step "Implementing: $ISSUE_KEY — $TITLE"

  BRANCH_SLUG=$(slugify "$TITLE")
  BRANCH_NAME="claude/${ISSUE_KEY}-${BRANCH_SLUG}"

  CARD_WORKTREE=$(setup_worktree "$ISSUE_KEY" "$BRANCH_NAME" "$REPO_ROOT" "$WORKTREE_DIR") || {
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: worktree creation failed on $(date '+%Y-%m-%d %H:%M')."
    continue
  }

  # Build prompt
  PROMPT=$(render_template "$SORTA_ROOT/prompts/code.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION" \
    CARD_COMMENTS "$COMMENTS" \
    BRANCH_NAME "$BRANCH_NAME" \
    BASE_BRANCH "$GIT_BASE_BRANCH")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  log_info "Running Claude Code in worktree..."
  claude_rc=0
  run_claude_safe "$PROMPT_FILE" "$RESULT_FILE" "$CARD_WORKTREE" || claude_rc=$?
  if [[ "$claude_rc" -ne 0 ]]; then
    [[ "$claude_rc" -eq 2 ]] && { git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true; break; }
    log_error "Claude failed for $ISSUE_KEY"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: implementation failed on $(date '+%Y-%m-%d %H:%M'). Manual intervention needed."
    git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    continue
  fi

  IMPLEMENTATION_RESULT=$(cat "$RESULT_FILE")
  rm -f "$PROMPT_FILE" "$RESULT_FILE"

  # Check for commits
  COMMIT_COUNT=$(git -C "$REPO_ROOT" log "origin/$GIT_BASE_BRANCH..$BRANCH_NAME" --oneline 2>/dev/null | wc -l)
  if [[ "$COMMIT_COUNT" -eq 0 ]]; then
    log_warn "No commits on branch for $ISSUE_KEY."
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: no commits produced on $(date '+%Y-%m-%d %H:%M'). Review needed."
    git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    continue
  fi

  log_info "$COMMIT_COUNT commit(s) on branch."

  # Push branch to remote
  git -C "$CARD_WORKTREE" push -u origin "$BRANCH_NAME" 2>/dev/null || {
    log_error "Failed to push branch $BRANCH_NAME for $ISSUE_KEY"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: push failed on $(date '+%Y-%m-%d %H:%M'). Branch: $BRANCH_NAME"
    git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    continue
  }

  # Prepare PR body
  PR_BODY_FILE=$(mktemp)
  cat > "$PR_BODY_FILE" << PREOF
## $ISSUE_KEY: $TITLE

### Implementation Notes
$IMPLEMENTATION_RESULT

### Test Plan
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Acceptance criteria met
- [ ] Manual QA

---
Automated by Sorta.Fit
PREOF

  # Check for existing open PR on this branch
  EXISTING_PR_URL=$("$GH_CMD" pr list --head "$BRANCH_NAME" --state open --json url --jq '.[0].url' 2>/dev/null || echo "")

  if [[ -n "$EXISTING_PR_URL" && "$EXISTING_PR_URL" != "null" ]]; then
    # Rework case — update existing PR instead of creating a duplicate
    PR_URL="$EXISTING_PR_URL"
    pr_edit_ok=false
    "$GH_CMD" pr edit "$PR_URL" --body-file "$PR_BODY_FILE" 2>/dev/null && pr_edit_ok=true || {
      log_warn "Failed to update PR body for $PR_URL"
    }
    "$GH_CMD" pr comment "$PR_URL" --body "Rework pushed by Sorta.Fit — ready for re-review" 2>/dev/null || {
      log_warn "Failed to post rework comment on $PR_URL"
    }
    rm -f "$PR_BODY_FILE"
    if [[ "$pr_edit_ok" == true ]]; then
      log_info "PR updated: $PR_URL"
      board_add_comment "$ISSUE_KEY" "PR updated: $PR_URL — Rework pushed by Sorta.Fit $(date '+%Y-%m-%d %H:%M')"
    else
      log_warn "PR body update failed, but rework commits pushed to branch"
      board_add_comment "$ISSUE_KEY" "Rework pushed to branch (PR body update failed): $PR_URL — Sorta.Fit $(date '+%Y-%m-%d %H:%M')"
    fi
  else
    # New PR case — create with retry (GitHub may not have indexed the pushed ref yet)
    pr_created=false
    for attempt in 1 2 3; do
      PR_URL=$("$GH_CMD" pr create \
        --title "$ISSUE_KEY: $TITLE" \
        --body-file "$PR_BODY_FILE" \
        --base "$GIT_BASE_BRANCH" \
        --head "$BRANCH_NAME" 2>&1) && {
        pr_created=true
        break
      }
      if [[ $attempt -lt 3 ]]; then
        log_warn "PR creation attempt $attempt failed for $ISSUE_KEY, retrying in 5s..."
        sleep 5
      fi
    done

    if [[ "$pr_created" != "true" ]]; then
      log_error "PR creation failed for $ISSUE_KEY after 3 attempts: $PR_URL"
      board_add_comment "$ISSUE_KEY" "Sorta.Fit: branch pushed but PR creation failed on $(date '+%Y-%m-%d %H:%M'). Branch: $BRANCH_NAME"
      runner_transition "$ISSUE_KEY" "$RUNNER_CODE_TO" "implemented"
      git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
      rm -f "$PR_BODY_FILE"
      continue
    fi

    rm -f "$PR_BODY_FILE"
    log_info "PR created: $PR_URL"
    board_add_comment "$ISSUE_KEY" "PR opened: $PR_URL — Sorta.Fit $(date '+%Y-%m-%d %H:%M')"
  fi

  runner_transition "$ISSUE_KEY" "$RUNNER_CODE_TO" "implemented"

  git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
  BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
done

[[ "$BATCH_PROCESSED" -gt 0 ]] && break
SKIP_RETRIES=$((SKIP_RETRIES + 1))
if [[ "$SKIP_RETRIES" -ge "$MAX_SKIP_RETRIES" ]]; then
  log_info "Reached max skip retries ($MAX_SKIP_RETRIES). Moving on."
  break
fi
START_AT=$((START_AT + MAX_CARDS_CODE))
log_info "All cards skipped in batch. Fetching next batch (retry $SKIP_RETRIES/$MAX_SKIP_RETRIES)..."
done

rmdir "$WORKTREE_DIR" 2>/dev/null || true
