#!/usr/bin/env bats
# Unit tests for core/config.sh validation

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  # Copy core/config.sh into the temp SORTA_ROOT so its SORTA_ROOT resolution works
  cp "$PROJECT_ROOT/core/config.sh" "$TEST_TEMP_DIR/core/config.sh"
  cp "$PROJECT_ROOT/core/utils.sh" "$TEST_TEMP_DIR/core/utils.sh"
  # Create adapter config example so config.sh doesn't error on missing adapter config
  cp "$PROJECT_ROOT/adapters/jira.config.sh.example" "$TEST_TEMP_DIR/adapters/jira.config.sh"
}

teardown() {
  teardown_test_env
}

@test "config: valid config loads without error" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  run_config
  assert_success
}

@test "config: missing BOARD_ADAPTER exits with error" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  # Remove BOARD_ADAPTER line
  sed_inplace '/^BOARD_ADAPTER/d' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
}

@test "config: invalid BOARD_ADAPTER exits with error" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  sed_inplace 's/^BOARD_ADAPTER=.*/BOARD_ADAPTER=dropbox/' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "Unknown adapter"
}

@test "config: BOARD_DOMAIN with protocol prefix fails" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  sed_inplace 's/^BOARD_DOMAIN=.*/BOARD_DOMAIN=https:\/\/foo.atlassian.net/' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "Invalid BOARD_DOMAIN"
}

@test "config: BOARD_DOMAIN with trailing slash fails" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  sed_inplace 's/^BOARD_DOMAIN=.*/BOARD_DOMAIN=foo.atlassian.net\//' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "Invalid BOARD_DOMAIN"
}

@test "config: BOARD_DOMAIN with single char fails" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  sed_inplace 's/^BOARD_DOMAIN=.*/BOARD_DOMAIN=x/' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "Invalid BOARD_DOMAIN"
}

@test "config: missing BOARD_API_TOKEN exits with error" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  sed_inplace '/^BOARD_API_TOKEN/d' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
}

@test "config: missing BOARD_PROJECT_KEY exits with error" {
  write_valid_env
  local repo_dir
  repo_dir=$(create_test_git_repo)
  echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
  sed_inplace '/^BOARD_PROJECT_KEY/d' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
}

@test "config: TARGET_REPO as relative path exits with error" {
  write_valid_env
  echo "TARGET_REPO=./repo" >> "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "absolute path"
}

@test "config: TARGET_REPO pointing to non-existent dir exits with error" {
  write_valid_env
  echo "TARGET_REPO=/nonexistent/path/to/repo" >> "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "does not exist"
}

@test "config: TARGET_REPO pointing to non-git dir exits with error" {
  write_valid_env
  local non_git_dir="$TEST_TEMP_DIR/not-a-repo"
  mkdir -p "$non_git_dir"
  echo "TARGET_REPO=$non_git_dir" >> "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "not a git repository"
}

@test "config: valid adapter names accepted" {
  for adapter in jira linear github-issues; do
    write_valid_env
    local repo_dir
    repo_dir=$(create_test_git_repo)
    echo "TARGET_REPO=$repo_dir" >> "$TEST_TEMP_DIR/.env"
    sed_inplace "s/^BOARD_ADAPTER=.*/BOARD_ADAPTER=$adapter/" "$TEST_TEMP_DIR/.env"
    # Create adapter config for this adapter
    touch "$TEST_TEMP_DIR/adapters/${adapter}.config.sh"
    run_config
    assert_success
  done
}
