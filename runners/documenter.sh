#!/usr/bin/env bash
# Runner: Documenter — generates and maintains project docs from card specs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"
source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"

PROTECTED_BRANCHES="main master dev develop"
WORKTREE_DIR="$SORTA_ROOT/.worktrees"

log_info "Documenter: checking $RUNNER_DOCUMENTER_FROM lane..."

ISSUE_IDS=$(board_get_cards_in_status "$RUNNER_DOCUMENTER_FROM" "$MAX_CARDS_DOCUMENTER")

if [[ -z "$ISSUE_IDS" ]]; then
  log_info "No cards in $RUNNER_DOCUMENTER_FROM. Nothing to document."
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel)

log_info "Fetching latest $GIT_BASE_BRANCH..."
git fetch origin "$GIT_BASE_BRANCH" 2>/dev/null || {
  log_error "Could not fetch origin/$GIT_BASE_BRANCH"
  exit 1
}

GH_CMD=$(find_gh)

for ISSUE_ID in $ISSUE_IDS; do
  ISSUE_KEY=$(board_get_card_key "$ISSUE_ID") || { log_warn "Failed to fetch key for issue $ISSUE_ID. Skipping."; continue; }
  TITLE=$(board_get_card_title "$ISSUE_KEY") || { log_warn "Failed to fetch title for $ISSUE_KEY. Skipping."; continue; }
  DESCRIPTION=$(board_get_card_description "$ISSUE_KEY") || { log_warn "Failed to fetch description for $ISSUE_KEY. Skipping."; continue; }
  COMMENTS=$(board_get_card_comments "$ISSUE_KEY") || { log_warn "Failed to fetch comments for $ISSUE_KEY. Skipping."; continue; }

  log_step "Documenting: $ISSUE_KEY — $TITLE"

  BRANCH_SLUG=$(slugify "$TITLE")
  BRANCH_NAME="claude/${ISSUE_KEY}-docs-${BRANCH_SLUG}"

  # Safety check
  for protected in $PROTECTED_BRANCHES; do
    if [[ "$BRANCH_NAME" == "$protected" ]]; then
      log_error "Branch name matches protected branch. Skipping."
      continue 2
    fi
  done

  CARD_WORKTREE="$WORKTREE_DIR/$ISSUE_KEY"

  # Clean up leftover worktree
  if [[ -d "$CARD_WORKTREE" ]]; then
    log_warn "Cleaning up leftover worktree..."
    git worktree remove "$CARD_WORKTREE" --force 2>/dev/null || rm -rf "$CARD_WORKTREE" 2>/dev/null || {
      log_warn "Locked worktree for $ISSUE_KEY. Using alternate directory."
      CARD_WORKTREE="${CARD_WORKTREE}-$(date +%s)"
    }
  fi

  # Create or reuse branch
  if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
    log_info "Branch $BRANCH_NAME already exists (retry case)."
  else
    log_info "Creating branch: $BRANCH_NAME from origin/$GIT_BASE_BRANCH"
    git branch "$BRANCH_NAME" "origin/$GIT_BASE_BRANCH"
  fi

  # Create worktree
  mkdir -p "$WORKTREE_DIR"
  git worktree add "$CARD_WORKTREE" "$BRANCH_NAME" 2>/dev/null || {
    log_error "Could not create worktree for $ISSUE_KEY"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: worktree creation failed on $(date '+%Y-%m-%d %H:%M')."
    continue
  }

  # Copy Claude permissions into worktree
  if [[ -f "$REPO_ROOT/.claude/settings.local.json" ]]; then
    mkdir -p "$CARD_WORKTREE/.claude"
    cp "$REPO_ROOT/.claude/settings.local.json" "$CARD_WORKTREE/.claude/settings.local.json"
  else
    log_warn "Missing .claude/settings.local.json — Claude Code won't have permissions to write files or run commands."
    log_warn "Create it with: echo '{\"permissions\":{\"allow\":[\"Bash(*)\",\"Read(*)\",\"Write(*)\",\"Edit(*)\",\"Glob(*)\",\"Grep(*)\"]}}' > .claude/settings.local.json"
  fi

  # Install dependencies
  log_info "Installing dependencies..."
  (cd "$CARD_WORKTREE" && npm ci --silent 2>/dev/null) || {
    log_warn "npm ci failed, trying npm install..."
    (cd "$CARD_WORKTREE" && npm install --silent 2>/dev/null) || true
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
  (cd "$CARD_WORKTREE" && claude -p "$(cat "$PROMPT_FILE")" > "$RESULT_FILE" 2>&1) || {
    log_error "Claude failed for $ISSUE_KEY"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: documentation generation failed on $(date '+%Y-%m-%d %H:%M'). Manual intervention needed."
    git worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    rm -f "$PROMPT_FILE" "$RESULT_FILE"
    continue
  }

  DOCUMENTATION_RESULT=$(cat "$RESULT_FILE")
  rm -f "$PROMPT_FILE" "$RESULT_FILE"

  # Check for commits
  COMMIT_COUNT=$(git log "origin/$GIT_BASE_BRANCH..$BRANCH_NAME" --oneline 2>/dev/null | wc -l)
  if [[ "$COMMIT_COUNT" -eq 0 ]]; then
    log_warn "No commits on branch for $ISSUE_KEY — no documentation changes needed."
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: no documentation changes needed on $(date '+%Y-%m-%d %H:%M')."
    git worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    continue
  fi

  log_info "$COMMIT_COUNT commit(s) on branch."

  # Push branch to remote
  (cd "$CARD_WORKTREE" && git push -u origin "$BRANCH_NAME" 2>/dev/null) || {
    log_error "Failed to push branch $BRANCH_NAME for $ISSUE_KEY"
    board_add_comment "$ISSUE_KEY" "Sorta.Fit: push failed on $(date '+%Y-%m-%d %H:%M'). Branch: $BRANCH_NAME"
    git worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
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
    if [[ -n "$RUNNER_DOCUMENTER_TO" ]]; then
      local_transition="TRANSITION_TO_${RUNNER_DOCUMENTER_TO}"
      board_transition "$ISSUE_KEY" "${!local_transition}"
    fi
    git worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
    rm -f "$PR_BODY_FILE"
    continue
  }

  rm -f "$PR_BODY_FILE"
  log_info "PR created: $PR_URL"

  board_add_comment "$ISSUE_KEY" "Docs PR opened: $PR_URL — Sorta.Fit $(date '+%Y-%m-%d %H:%M')"

  if [[ -n "$RUNNER_DOCUMENTER_TO" ]]; then
    local_transition="TRANSITION_TO_${RUNNER_DOCUMENTER_TO}"
    board_transition "$ISSUE_KEY" "${!local_transition}"
    log_info "Done: $ISSUE_KEY documented and moved to $RUNNER_DOCUMENTER_TO"
  else
    log_info "Done: $ISSUE_KEY documented (no transition configured)"
  fi

  git worktree remove "$CARD_WORKTREE" --force 2>/dev/null || true
done

rmdir "$WORKTREE_DIR" 2>/dev/null || true
