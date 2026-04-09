#!/usr/bin/env bats
# Integration tests for config loading pipeline
# Focused on default values and overrides (validation logic is in unit/config.bats)

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  cp "$PROJECT_ROOT/core/config.sh" "$TEST_TEMP_DIR/core/config.sh"
  cp "$PROJECT_ROOT/core/utils.sh" "$TEST_TEMP_DIR/core/utils.sh"
  cp "$PROJECT_ROOT/adapters/jira.config.sh.example" "$TEST_TEMP_DIR/adapters/jira.config.sh"
}

teardown() {
  teardown_test_env
}

@test "integration: default GIT_BASE_BRANCH is main when not set" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  run bash -c "
    unset BOARD_ADAPTER BOARD_DOMAIN BOARD_API_TOKEN BOARD_PROJECT_KEY BOARD_EMAIL TARGET_REPO
    unset GIT_BASE_BRANCH POLL_INTERVAL RUNNERS_ENABLED
    export HOME='$TEST_TEMP_DIR'
    cd '$TEST_TEMP_DIR'
    source '$TEST_TEMP_DIR/core/config.sh'
    echo \"\$GIT_BASE_BRANCH\"
  "
  assert_success
  assert_output "main"
}

@test "integration: default POLL_INTERVAL is 3600 when not set" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  run bash -c "
    unset BOARD_ADAPTER BOARD_DOMAIN BOARD_API_TOKEN BOARD_PROJECT_KEY BOARD_EMAIL TARGET_REPO
    unset GIT_BASE_BRANCH POLL_INTERVAL RUNNERS_ENABLED
    export HOME='$TEST_TEMP_DIR'
    cd '$TEST_TEMP_DIR'
    source '$TEST_TEMP_DIR/core/config.sh'
    echo \"\$POLL_INTERVAL\"
  "
  assert_success
  assert_output "3600"
}

@test "integration: default RUNNERS_ENABLED is refine,code when not set" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  run bash -c "
    unset BOARD_ADAPTER BOARD_DOMAIN BOARD_API_TOKEN BOARD_PROJECT_KEY BOARD_EMAIL TARGET_REPO
    unset GIT_BASE_BRANCH POLL_INTERVAL RUNNERS_ENABLED
    export HOME='$TEST_TEMP_DIR'
    cd '$TEST_TEMP_DIR'
    source '$TEST_TEMP_DIR/core/config.sh'
    echo \"\$RUNNERS_ENABLED\"
  "
  assert_success
  assert_output "refine,code"
}

@test "integration: custom values override defaults" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  cat >> "$TEST_TEMP_DIR/.env" <<EOF
TARGET_REPO=$repo_dir
GIT_BASE_BRANCH=develop
POLL_INTERVAL=60
RUNNERS_ENABLED=refine,architect,code
EOF
  run bash -c "
    unset BOARD_ADAPTER BOARD_DOMAIN BOARD_API_TOKEN BOARD_PROJECT_KEY BOARD_EMAIL TARGET_REPO
    unset GIT_BASE_BRANCH POLL_INTERVAL RUNNERS_ENABLED
    export HOME='$TEST_TEMP_DIR'
    cd '$TEST_TEMP_DIR'
    source '$TEST_TEMP_DIR/core/config.sh'
    echo \"\$GIT_BASE_BRANCH \$POLL_INTERVAL \$RUNNERS_ENABLED\"
  "
  assert_success
  assert_output "develop 60 refine,architect,code"
}
