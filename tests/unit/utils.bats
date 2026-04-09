#!/usr/bin/env bats
# Unit tests for core/utils.sh

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  # Source utils.sh (needs SORTA_ROOT set)
  source "$PROJECT_ROOT/core/utils.sh"
}

teardown() {
  teardown_test_env
}

# ── slugify ──────────────────────────────────────────────────────────────────

@test "slugify: converts uppercase to lowercase" {
  run slugify "HELLO WORLD"
  assert_success
  assert_output "hello-world"
}

@test "slugify: replaces spaces with dashes" {
  run slugify "hello world"
  assert_success
  assert_output "hello-world"
}

@test "slugify: removes special characters" {
  run slugify "hello@world!foo"
  assert_success
  assert_output "hello-world-foo"
}

@test "slugify: collapses consecutive dashes" {
  run slugify "hello---world"
  assert_success
  assert_output "hello-world"
}

@test "slugify: strips leading dashes" {
  run slugify "---hello"
  assert_success
  assert_output "hello"
}

@test "slugify: strips trailing dashes" {
  run slugify "hello---"
  assert_success
  assert_output "hello"
}

@test "slugify: truncates output to 40 characters" {
  run slugify "this is a very long string that should be truncated to forty characters maximum"
  assert_success
  # Output should be at most 40 chars
  [[ ${#output} -le 40 ]]
}

@test "slugify: handles empty input" {
  run slugify ""
  assert_success
  assert_output ""
}

@test "slugify: handles mixed case and special chars" {
  run slugify "SF-16 Add Tests & Validations!"
  assert_success
  assert_output "sf-16-add-tests-validations"
}

# ── matches_type_filter ──────────────────────────────────────────────────────

@test "matches_type_filter: empty filter matches all" {
  run matches_type_filter "Bug" ""
  assert_success
}

@test "matches_type_filter: exact match returns success" {
  run matches_type_filter "Bug" "Bug"
  assert_success
}

@test "matches_type_filter: no match returns failure" {
  run matches_type_filter "Story" "Bug"
  assert_failure
}

@test "matches_type_filter: multiple types in filter" {
  run matches_type_filter "Bug" "Story,Bug,Task"
  assert_success
}

@test "matches_type_filter: multiple types no match" {
  run matches_type_filter "Epic" "Story,Bug,Task"
  assert_failure
}

@test "matches_type_filter: whitespace around types trimmed" {
  run matches_type_filter "Bug" "Story , Bug , Task"
  assert_success
}

# ── extract_pr_url ───────────────────────────────────────────────────────────

@test "extract_pr_url: extracts single URL" {
  run extract_pr_url "PR opened at https://github.com/owner/repo/pull/123"
  assert_success
  assert_output "https://github.com/owner/repo/pull/123"
}

@test "extract_pr_url: multiple URLs returns last" {
  local text="First PR: https://github.com/owner/repo/pull/1
Second PR: https://github.com/owner/repo/pull/42"
  run extract_pr_url "$text"
  assert_success
  assert_output "https://github.com/owner/repo/pull/42"
}

@test "extract_pr_url: no URL returns empty" {
  run extract_pr_url "no links here"
  assert_success
  assert_output ""
}

@test "extract_pr_url: URL embedded in surrounding text" {
  run extract_pr_url "See https://github.com/org/project/pull/99 for details"
  assert_success
  assert_output "https://github.com/org/project/pull/99"
}

# ── require_command ──────────────────────────────────────────────────────────

@test "require_command: existing command returns success" {
  run require_command "bash"
  assert_success
}

@test "require_command: missing command returns failure" {
  run require_command "nonexistent_command_12345"
  assert_failure
}

# ── lock_acquire / lock_release ──────────────────────────────────────────────

@test "lock_acquire: fresh acquire succeeds" {
  local lock_dir="$TEST_TEMP_DIR/.test.lock"
  run lock_acquire "$lock_dir"
  assert_success
  [[ -d "$lock_dir" ]]
  lock_release "$lock_dir"
}

@test "lock_acquire: double acquire on live PID fails" {
  local lock_dir="$TEST_TEMP_DIR/.test.lock"
  lock_acquire "$lock_dir"
  run lock_acquire "$lock_dir"
  assert_failure
  lock_release "$lock_dir"
}

@test "lock_release: release then re-acquire succeeds" {
  local lock_dir="$TEST_TEMP_DIR/.test.lock"
  lock_acquire "$lock_dir"
  lock_release "$lock_dir"
  run lock_acquire "$lock_dir"
  assert_success
  lock_release "$lock_dir"
}

@test "lock_acquire: stale lock from dead PID is cleaned up" {
  local lock_dir="$TEST_TEMP_DIR/.test.lock"
  mkdir -p "$lock_dir"
  # Use a PID that is almost certainly not running
  echo "999999" > "$lock_dir/pid"
  # Verify that PID is not alive (skip test if it happens to be)
  if kill -0 999999 2>/dev/null; then
    skip "PID 999999 unexpectedly alive"
  fi
  run lock_acquire "$lock_dir"
  assert_success
  lock_release "$lock_dir"
}

# ── is_rate_limited ──────────────────────────────────────────────────────────

@test "is_rate_limited: no file returns not limited" {
  rm -f "$RATE_LIMIT_FILE"
  run is_rate_limited
  assert_failure  # return 1 = not limited
}

@test "is_rate_limited: recent file returns limited" {
  date +%s > "$RATE_LIMIT_FILE"
  run is_rate_limited
  assert_success  # return 0 = limited
  rm -f "$RATE_LIMIT_FILE"
}

@test "is_rate_limited: expired file returns not limited and removes file" {
  # Write a timestamp from 2 hours ago
  echo $(( $(date +%s) - 7200 )) > "$RATE_LIMIT_FILE"
  run is_rate_limited
  assert_failure  # return 1 = not limited
  [[ ! -f "$RATE_LIMIT_FILE" ]]
}
