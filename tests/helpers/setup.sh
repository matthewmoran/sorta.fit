#!/usr/bin/env bash
# Sorta.Fit — Shared test helper for bats tests

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/libs/bats-support/load.bash"
load "${TESTS_DIR}/libs/bats-assert/load.bash"

# Create a temporary directory for test isolation
setup_test_env() {
  TEST_TEMP_DIR="$(mktemp -d)"
  export SORTA_ROOT="$TEST_TEMP_DIR"
  mkdir -p "$TEST_TEMP_DIR/core"
  mkdir -p "$TEST_TEMP_DIR/adapters"
  mkdir -p "$TEST_TEMP_DIR/runners"
}

# Clean up temporary directory
teardown_test_env() {
  if [[ -n "${TEST_TEMP_DIR:-}" && -d "$TEST_TEMP_DIR" ]]; then
    rm -rf "$TEST_TEMP_DIR"
  fi
}

# Write a minimal valid .env file for testing
write_valid_env() {
  local env_file="${1:-$TEST_TEMP_DIR/.env}"
  cat > "$env_file" <<'ENVEOF'
BOARD_ADAPTER=jira
BOARD_DOMAIN=test.atlassian.net
BOARD_API_TOKEN=test-token-do-not-use
BOARD_PROJECT_KEY=TEST
BOARD_EMAIL=test@example.com
ENVEOF
}

# Create a minimal git repo for TARGET_REPO tests
# Uses a unique dir name each call to avoid conflicts in loops
create_test_git_repo() {
  local repo_dir="$TEST_TEMP_DIR/test-repo-$$-$RANDOM"
  mkdir -p "$repo_dir"
  git -C "$repo_dir" init --quiet >&2
  git -C "$repo_dir" config user.email "test@test.com" >&2
  git -C "$repo_dir" config user.name "Test" >&2
  touch "$repo_dir/.gitkeep"
  git -C "$repo_dir" add . >&2
  git -C "$repo_dir" commit --quiet -m "init" >&2
  echo "$repo_dir"
}

# Mock board_transition for runner-lib tests
board_transition() {
  MOCK_BOARD_TRANSITION_CALLS+=("$*")
}

# Mock logging functions (capture to arrays)
mock_log_info() { MOCK_LOG_INFO+=("$*"); }
mock_log_warn() { MOCK_LOG_WARN+=("$*"); }
mock_log_error() { MOCK_LOG_ERROR+=("$*"); }
