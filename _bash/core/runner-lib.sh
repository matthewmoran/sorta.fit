#!/usr/bin/env bash
# Sorta.Fit — Shared runner library
# Source this after config.sh, utils.sh, and the adapter.
# Provides common functions used across multiple runners.

# Transition a card to a target status with guard checks
# Usage: runner_transition <issue_key> <target_status> <verb>
# Examples:
#   runner_transition "$ISSUE_KEY" "$RUNNER_REFINE_TO" "refined"
#   runner_transition "$ISSUE_KEY" "" "architected"  # logs "no transition configured"
runner_transition() {
  local issue_key="$1"
  local target_status="$2"
  local verb="$3"

  if [[ -z "$target_status" ]]; then
    log_info "Done: $issue_key $verb (no transition configured)"
    return 0
  fi

  # Sanitize status ID for bash variable name (replace non-alphanumeric with _)
  local safe_status="${target_status//[^a-zA-Z0-9_]/_}"
  local transition_var="TRANSITION_TO_${safe_status}"
  if [[ -n "${!transition_var:-}" ]]; then
    board_transition "$issue_key" "${!transition_var}"
    log_info "Done: $issue_key $verb and moved to $target_status"
  else
    log_warn "No transition mapping found for status $target_status — card $verb but not moved. Add $transition_var to your adapter config."
  fi
}

# Set up a git worktree for a card (used by code and documenter runners)
# Usage: CARD_WORKTREE=$(setup_worktree <issue_key> <branch_name> <repo_root> <worktree_dir>)
# Returns 0 and prints worktree path on success, returns 1 on failure.
setup_worktree() {
  local issue_key="$1"
  local branch_name="$2"
  local repo_root="$3"
  local worktree_dir="$4"
  local protected_branches="main master dev develop"
  local card_worktree="$worktree_dir/$issue_key"

  # Safety check — never work on protected branches
  for protected in $protected_branches; do
    if [[ "$branch_name" == "$protected" ]]; then
      log_error "Branch name matches protected branch. Skipping."
      return 1
    fi
  done

  # Clean up leftover worktree from a previous attempt
  if [[ -d "$card_worktree" ]]; then
    log_warn "Cleaning up leftover worktree..."
    git -C "$repo_root" worktree remove "$card_worktree" --force 2>/dev/null || rm -rf "$card_worktree" 2>/dev/null || {
      log_warn "Locked worktree for $issue_key. Using alternate directory."
      card_worktree="${card_worktree}-$(date +%s)"
    }
  fi

  # Create or reuse branch
  if git -C "$repo_root" rev-parse --verify "$branch_name" >/dev/null 2>&1; then
    log_info "Branch $branch_name already exists (retry case)." >&2
  else
    log_info "Creating branch: $branch_name from origin/$GIT_BASE_BRANCH" >&2
    git -C "$repo_root" branch "$branch_name" "origin/$GIT_BASE_BRANCH" >&2
  fi

  # Create worktree (prune stale entries first to avoid "branch already checked out" errors)
  mkdir -p "$worktree_dir"
  git -C "$repo_root" worktree prune 2>/dev/null
  git -C "$repo_root" worktree add "$card_worktree" "$branch_name" 2>/dev/null >&2 || {
    log_error "Could not create worktree for $issue_key"
    return 1
  }

  # Copy Claude permissions into worktree
  if [[ -f "$repo_root/.claude/settings.local.json" ]]; then
    mkdir -p "$card_worktree/.claude"
    cp "$repo_root/.claude/settings.local.json" "$card_worktree/.claude/settings.local.json"
  else
    log_warn "Missing .claude/settings.local.json — Claude Code won't have permissions to write files or run commands."
    log_warn "Create it with: cp .claude/settings.local.json.example .claude/settings.local.json"
  fi

  # Install dependencies
  log_info "Installing dependencies..." >&2
  (cd "$card_worktree" && npm ci --silent 2>/dev/null) || {
    log_warn "npm ci failed, trying npm install..."
    (cd "$card_worktree" && npm install --silent 2>/dev/null) || true
  }

  echo "$card_worktree"
  return 0
}

# Run Claude with cleanup on failure
# Usage: run_claude_safe <prompt_file> <result_file> [work_dir] [agent]
# Returns 0 on success, 1 on error (files cleaned), 2 on rate limit (files cleaned)
run_claude_safe() {
  local prompt_file="$1"
  local result_file="$2"
  local work_dir="${3:-}"
  local agent="${4:-}"
  local rc=0

  if [[ -n "$work_dir" ]]; then
    run_claude "$prompt_file" "$result_file" "$work_dir" "$agent" || rc=$?
  else
    run_claude "$prompt_file" "$result_file" "" "$agent" || rc=$?
  fi

  if [[ "$rc" -ne 0 ]]; then
    rm -f "$prompt_file" "$result_file"
  fi
  return "$rc"
}

# Extract a GitHub PR URL from comment text
# Usage: PR_URL=$(extract_pr_url "$COMMENTS")
extract_pr_url() {
  echo "$1" | grep -oE 'https://github\.com/[^/]+/[^/]+/pull/[0-9]+' | head -1
}

# Check if a PR has a specific review state (APPROVED, CHANGES_REQUESTED, etc.)
# Usage: check_pr_review_state <pr_url> <expected_state>
# Returns 0 if matched, 1 otherwise
check_pr_review_state() {
  local pr_url="$1"
  local expected="$2"
  local gh_cmd
  gh_cmd=$(find_gh)

  local state
  state=$("$gh_cmd" pr view "$pr_url" --json reviewDecision --jq '.reviewDecision' 2>/dev/null || echo "")

  if [[ "$state" == "$expected" ]]; then
    return 0
  fi

  # Fallback: check reviews directly
  if [[ -z "$state" || "$state" == "null" ]]; then
    local latest
    latest=$("$gh_cmd" pr view "$pr_url" --json reviews --jq '.reviews[-1].state' 2>/dev/null || echo "")
    if [[ "$latest" == "$expected" ]]; then
      return 0
    fi
  fi

  return 1
}
