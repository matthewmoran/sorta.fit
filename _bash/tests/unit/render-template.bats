#!/usr/bin/env bats
# Unit tests for render_template in core/utils.sh

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  source "$PROJECT_ROOT/core/utils.sh"
}

teardown() {
  teardown_test_env
}

@test "render_template: single key substitution" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "Hello {{NAME}}!" > "$tmpl"
  run render_template "$tmpl" NAME "World"
  assert_success
  assert_output "Hello World!"
}

@test "render_template: multiple key substitution" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "{{GREETING}} {{NAME}}, welcome to {{PLACE}}." > "$tmpl"
  run render_template "$tmpl" GREETING "Hello" NAME "Alice" PLACE "Wonderland"
  assert_success
  assert_output "Hello Alice, welcome to Wonderland."
}

@test "render_template: missing key left as-is" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "Hello {{NAME}}, your ID is {{UNKNOWN_KEY}}." > "$tmpl"
  run render_template "$tmpl" NAME "Bob"
  assert_success
  assert_output "Hello Bob, your ID is {{UNKNOWN_KEY}}."
}

@test "render_template: value with dollar sign" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "Price: {{PRICE}}" > "$tmpl"
  run render_template "$tmpl" PRICE '$100'
  assert_success
  assert_output 'Price: $100'
}

@test "render_template: value with backticks" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "Run: {{CMD}}" > "$tmpl"
  run render_template "$tmpl" CMD '`echo hello`'
  assert_success
  assert_output 'Run: `echo hello`'
}

@test "render_template: value with single quotes" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "Say: {{MSG}}" > "$tmpl"
  run render_template "$tmpl" MSG "it's working"
  assert_success
  assert_output "Say: it's working"
}

@test "render_template: value with double quotes" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "Say: {{MSG}}" > "$tmpl"
  run render_template "$tmpl" MSG 'She said "hello"'
  assert_success
  assert_output 'Say: She said "hello"'
}

@test "render_template: missing template file returns error" {
  run render_template "$TEST_TEMP_DIR/nonexistent.md" KEY "value"
  assert_failure
}

@test "render_template: empty template file returns empty output" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  touch "$tmpl"
  run render_template "$tmpl" KEY "value"
  assert_success
  assert_output ""
}

@test "render_template: same key appears multiple times" {
  local tmpl="$TEST_TEMP_DIR/tmpl.md"
  echo "{{X}} and {{X}} again" > "$tmpl"
  run render_template "$tmpl" X "foo"
  assert_success
  assert_output "foo and foo again"
}
