#!/usr/bin/env bats
# Integration tests for core/loop.sh --validate mode

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  # Copy core files into temp SORTA_ROOT
  cp "$PROJECT_ROOT/core/config.sh" "$TEST_TEMP_DIR/core/config.sh"
  cp "$PROJECT_ROOT/core/utils.sh" "$TEST_TEMP_DIR/core/utils.sh"
  cp "$PROJECT_ROOT/core/loop.sh" "$TEST_TEMP_DIR/core/loop.sh"
  # Create a minimal adapter (just needs to be sourceable)
  printf '#!/usr/bin/env bash\n' > "$TEST_TEMP_DIR/adapters/jira.sh"
  cp "$PROJECT_ROOT/adapters/jira.config.sh.example" "$TEST_TEMP_DIR/adapters/jira.config.sh"
  # Create runner scripts
  printf '#!/usr/bin/env bash\n' > "$TEST_TEMP_DIR/runners/refine.sh"
  printf '#!/usr/bin/env bash\n' > "$TEST_TEMP_DIR/runners/code.sh"
}

teardown() {
  teardown_test_env
}

run_validate() {
  run bash -c "
    unset BOARD_ADAPTER BOARD_DOMAIN BOARD_API_TOKEN BOARD_PROJECT_KEY BOARD_EMAIL TARGET_REPO
    unset GIT_BASE_BRANCH POLL_INTERVAL RUNNERS_ENABLED RUNNER_REFINE_FROM RUNNER_CODE_FROM
    export HOME='$TEST_TEMP_DIR'
    cd '$TEST_TEMP_DIR'
    exec 2>&1
    bash '$TEST_TEMP_DIR/core/loop.sh' --validate
  "
}

@test "validate: valid config with existing runners passes" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  cat >> "$TEST_TEMP_DIR/.env" <<EOF
TARGET_REPO=$repo_dir
RUNNERS_ENABLED=refine,code
RUNNER_REFINE_FROM=10000
RUNNER_CODE_FROM=10001
EOF
  run_validate
  assert_success
  assert_output --partial "Validation passed"
}

@test "validate: missing runner script fails" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  cat >> "$TEST_TEMP_DIR/.env" <<EOF
TARGET_REPO=$repo_dir
RUNNERS_ENABLED=refine,nonexistent
RUNNER_REFINE_FROM=10000
EOF
  run_validate
  assert_failure
  assert_output --partial "Runner script not found"
}

@test "validate: missing RUNNER_FROM warns but does not fail" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  cat >> "$TEST_TEMP_DIR/.env" <<EOF
TARGET_REPO=$repo_dir
RUNNERS_ENABLED=refine
EOF
  run_validate
  assert_success
  assert_output --partial "RUNNER_REFINE_FROM is not set"
}

@test "validate: missing adapter config fails" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  cat >> "$TEST_TEMP_DIR/.env" <<EOF
TARGET_REPO=$repo_dir
RUNNERS_ENABLED=refine
RUNNER_REFINE_FROM=10000
EOF
  # Remove adapter config
  rm -f "$TEST_TEMP_DIR/adapters/jira.config.sh"
  run_validate
  assert_failure
  assert_output --partial "Adapter config not found"
}
