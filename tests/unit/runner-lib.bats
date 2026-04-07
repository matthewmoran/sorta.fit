#!/usr/bin/env bats
# Unit tests for core/runner-lib.sh

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  # Source utils.sh for logging functions
  source "$PROJECT_ROOT/core/utils.sh"
  # Define mock board_transition before sourcing runner-lib
  MOCK_BOARD_TRANSITION_CALLS=()
  board_transition() {
    MOCK_BOARD_TRANSITION_CALLS+=("$*")
  }
  export -f board_transition
  # Source runner-lib
  source "$PROJECT_ROOT/core/runner-lib.sh"
}

teardown() {
  teardown_test_env
}

# ── runner_transition ────────────────────────────────────────────────────────

@test "runner_transition: empty target_status logs no-transition and returns 0" {
  run runner_transition "TEST-1" "" "refined"
  assert_success
  assert_output --partial "no transition configured"
}

@test "runner_transition: valid target_status with mapping calls board_transition" {
  TRANSITION_TO_10070=5
  runner_transition "TEST-1" "10070" "refined"
  [[ ${#MOCK_BOARD_TRANSITION_CALLS[@]} -eq 1 ]]
  [[ "${MOCK_BOARD_TRANSITION_CALLS[0]}" == "TEST-1 5" ]]
}

@test "runner_transition: target_status without mapping logs warning" {
  # No TRANSITION_TO_99999 set
  run runner_transition "TEST-1" "99999" "refined"
  assert_success
  assert_output --partial "No transition mapping found"
}

# ── extract_pr_url (runner-lib version uses head -1) ─────────────────────────

@test "runner-lib extract_pr_url: extracts single URL" {
  # Re-source runner-lib to get its extract_pr_url (overrides utils.sh version)
  source "$PROJECT_ROOT/core/runner-lib.sh"
  run extract_pr_url "PR: https://github.com/owner/repo/pull/42"
  assert_success
  assert_output "https://github.com/owner/repo/pull/42"
}

@test "runner-lib extract_pr_url: multiple URLs returns first (head -1)" {
  source "$PROJECT_ROOT/core/runner-lib.sh"
  local text="First: https://github.com/owner/repo/pull/1
Second: https://github.com/owner/repo/pull/2"
  run extract_pr_url "$text"
  assert_success
  assert_output "https://github.com/owner/repo/pull/1"
}

@test "runner-lib extract_pr_url: no URL returns empty" {
  source "$PROJECT_ROOT/core/runner-lib.sh"
  run extract_pr_url "no links here"
  assert_success
  assert_output ""
}

# ── setup_worktree safety ───────────────────────────────────────────────────

@test "setup_worktree: rejects protected branch names" {
  for branch in main master dev develop; do
    run setup_worktree "TEST-1" "$branch" "$TEST_TEMP_DIR" "$TEST_TEMP_DIR/worktrees"
    assert_failure
  done
}
