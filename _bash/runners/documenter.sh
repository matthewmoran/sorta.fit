#!/usr/bin/env bash
# Runner: Documenter — generates and maintains project docs from card specs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
source "$SORTA_ROOT/core/runner-lib.sh"

WORKTREE_DIR="$SORTA_ROOT/.worktrees"

log_info "Documenter: checking $RUNNER_DOCUMENTER_FROM lane..."

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
ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_DOCUMENTER_FROM" "$MAX_CARDS_DOCUMENTER" "$START_AT")

if [[ -z "$ISSUE_IDS" ]]; then
  [[ "$START_AT" -eq 0 ]] && log_info "No cards in $RUNNER_DOCUMENTER_FROM. Nothing to document."
  break
fi

BATCH_PROCESSED=0

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }
  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY") || { log_warn "Failed to fetch description for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  # Skip if already documented
  if echo "$COMMENTS" | grep -q "Docs PR opened"; then
    log_info "$ISSUE_KEY already documented. Skipping."
    continue
  fi
  if echo "$COMMENTS" | grep -q "no documentation changes needed"; then
    log_info "$ISSUE_KEY already checked — no docs needed. Skipping."
    continue
  fi

  log_step "Documenting: $ISSUE_KEY — $TITLE"

  BRANCH_SLUG=$(slugify "$TITLE")
  BRANCH_NAME="claude/${ISSUE_KEY}-docs-${BRANCH_SLUG}"

  CARD_WORKTREE=$(setup_worktree "$ISSUE_KEY" "$BRANCH_NAME" "$REPO_ROOT" "$WORKTREE_DIR") || {
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: worktree creation failed on $(date '+%Y-%m-%d %H:%M')."
    continue
  }

  # Build prompt
  PROMPT=$(render_template "$SORTA_ROOT/prompts/documenter.md" \
    CARD_KEY "$ISSUE_KEY" \
    CARD_TITLE "$TITLE" \
    CARD_DESCRIPTION "$DESCRIPTION" \
    CARD_COMMENTS "$COMMENTS" \
    BRANCH_NAME "$BRANCH_NAME" \
    BASE_BRANCH "$GIT_BASE_BRANCH" \
    DOCS_DIR "$DOCS_DIR" \
    DOCS_ORGANIZE_BY "$DOCS_ORGANIZE_BY")

  PROMPT_FILE=$(mktemp)
  RESULT_FILE=$(mktemp)
  printf '%s' "$PROMPT" > "$PROMPT_FILE"

  log_info "Running Claude Code in worktree..."
  claude_rc=0
  run_claude_safe "$PROMPT_FILE" "$RESULT_FILE" "$CARD_WORKTREE" "${RUNNER_DOCUMENTER_AGENT:-$CLAUDE_AGENT}" || claude_rc=$?
  if [[ "$claude_rc" -ne 0 ]]; then
    [[ "$claude_rc" -eq 2 ]] && { git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true; break; }
    log_error "Claude failed for $ISSUE_KEY"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: documentation generation failed on $(date '+%Y-%m-%d %H:%M'). Manual intervention needed."
    git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    continue
  fi

  DOCUMENTATION_RESULT=$(cat "$RESULT_FILE")
  rm -f "$PROMPT_FILE" "$RESULT_FILE"

  # Check for commits
  COMMIT_COUNT=$(git -C "$REPO_ROOT" log "origin/$GIT_BASE_BRANCH..$BRANCH_NAME" --oneline 2>/dev/null | wc -l)
  if [[ "$COMMIT_COUNT" -eq 0 ]]; then
    log_warn "No commits on branch for $ISSUE_KEY — no documentation changes needed."
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: no documentation changes needed on $(date '+%Y-%m-%d %H:%M')."
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

  # Create PR
  PR_BODY_FILE=$(mktemp)
  cat > "$PR_BODY_FILE" << PREOF
## $ISSUE_KEY: $TITLE — Documentation

### Documentation Changes
$DOCUMENTATION_RESULT

### Review Checklist
- [ ] Documentation is accurate and matches the feature spec
- [ ] Existing docs updated where appropriate (not duplicated)
- [ ] File placement follows \`$DOCS_DIR\` convention

---
Automated by Sorta.Fit
PREOF

  PR_URL=$("$GH_CMD" pr create \
    --title "$ISSUE_KEY: docs — $TITLE" \
    --body-file "$PR_BODY_FILE" \
    --base "$GIT_BASE_BRANCH" \
    --head "$BRANCH_NAME" 2>&1) || {
    log_error "PR creation failed for $ISSUE_KEY: $PR_URL"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: branch pushed but PR creation failed on $(date '+%Y-%m-%d %H:%M'). Branch: $BRANCH_NAME"
    runner_transition "$ISSUE_KEY" "$RUNNER_DOCUMENTER_TO" "documented"
    git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    rm -f "$PR_BODY_FILE"
    continue
  }

  rm -f "$PR_BODY_FILE"
  log_info "PR created: $PR_URL"

  board_add_comment "$ISSUE_KEY" "Docs PR opened: $PR_URL — Sorta.Fit $(date '+%Y-%m-%d %H:%M')"

  runner_transition "$ISSUE_KEY" "$RUNNER_DOCUMENTER_TO" "documented"

  git -C "$REPO_ROOT" worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
  BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
done

[[ "$BATCH_PROCESSED" -gt 0 ]] && break
SKIP_RETRIES=$((SKIP_RETRIES + 1))
if [[ "$SKIP_RETRIES" -ge "$MAX_SKIP_RETRIES" ]]; then
  log_info "Reached max skip retries ($MAX_SKIP_RETRIES). Moving on."
  break
fi
START_AT=$((START_AT + MAX_CARDS_DOCUMENTER))
log_info "All cards skipped in batch. Fetching next batch (retry $SKIP_RETRIES/$MAX_SKIP_RETRIES)..."
done

rmdir "$WORKTREE_DIR" 2>/dev/null || true
