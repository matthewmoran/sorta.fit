#!/usr/bin/env bats
# Integration tests for linear_graphql error handling in adapters/linear.sh

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env

  # Create mock curl bin dir with a script that reads behavior from env vars
  MOCK_BIN_DIR="$TEST_TEMP_DIR/mock-bin"
  mkdir -p "$MOCK_BIN_DIR"

  printf '#!/usr/bin/env bash\n' > "$MOCK_BIN_DIR/curl"
  printf 'output_file=""\nwrite_out=""\n' >> "$MOCK_BIN_DIR/curl"
  printf 'while [[ $# -gt 0 ]]; do\n' >> "$MOCK_BIN_DIR/curl"
  printf '  case "$1" in\n' >> "$MOCK_BIN_DIR/curl"
  printf '    -o) output_file="$2"; shift 2 ;;\n' >> "$MOCK_BIN_DIR/curl"
  printf '    -w) write_out="$2"; shift 2 ;;\n' >> "$MOCK_BIN_DIR/curl"
  printf '    *) shift ;;\n' >> "$MOCK_BIN_DIR/curl"
  printf '  esac\n' >> "$MOCK_BIN_DIR/curl"
  printf 'done\n' >> "$MOCK_BIN_DIR/curl"
  printf 'if [[ "${MOCK_CURL_EXIT:-0}" -ne 0 ]]; then exit "$MOCK_CURL_EXIT"; fi\n' >> "$MOCK_BIN_DIR/curl"
  printf 'if [[ -n "$output_file" ]]; then printf "%%s" "${MOCK_CURL_BODY:-}" > "$output_file"; fi\n' >> "$MOCK_BIN_DIR/curl"
  printf 'if [[ -n "$write_out" ]]; then printf "%%s" "${MOCK_CURL_HTTP_CODE:-200}"; fi\n' >> "$MOCK_BIN_DIR/curl"
  chmod +x "$MOCK_BIN_DIR/curl"

  # Set required env vars for linear.sh
  export BOARD_API_TOKEN="test-token-do-not-use"
  export BOARD_DOMAIN="api.linear.app"
  export BOARD_PROJECT_KEY="TEST"
}

teardown() {
  teardown_test_env
}

# Helper: source linear.sh and call linear_graphql with mock curl on PATH
# Uses a wrapper script file to avoid quoting issues with bash -c and braces
run_linear_graphql_with_mock() {
  local http_code="$1"
  local body="$2"
  local curl_exit="${3:-0}"

  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' "$body" > "$body_file"

  # Write the test script to a file to avoid bash -c quoting issues with braces
  local test_script="$TEST_TEMP_DIR/test_script.sh"
  cat > "$test_script" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
exec 2>&1
export PATH='$MOCK_BIN_DIR':\$PATH
export MOCK_CURL_HTTP_CODE='$http_code'
export MOCK_CURL_BODY=\$(cat '$body_file')
export MOCK_CURL_EXIT='$curl_exit'
export BOARD_API_TOKEN='test-token-do-not-use'
export BOARD_DOMAIN='api.linear.app'
export BOARD_PROJECT_KEY='TEST'
source '$PROJECT_ROOT/core/utils.sh'
source '$PROJECT_ROOT/adapters/linear.sh'
linear_graphql '{ viewer { id } }'
SCRIPT
  chmod +x "$test_script"

  run bash "$test_script"
}

@test "linear_graphql: HTML response returns error" {
  run_linear_graphql_with_mock "200" "<html><body>Not JSON</body></html>"
  assert_failure
  assert_output --partial "HTML instead of JSON"
}

@test "linear_graphql: HTTP 401 returns error" {
  run_linear_graphql_with_mock "401" '{"errors":[{"message":"unauthorized"}]}'
  assert_failure
  assert_output --partial "HTTP 401"
}

@test "linear_graphql: HTTP 500 returns error" {
  run_linear_graphql_with_mock "500" '{"errors":[{"message":"server error"}]}'
  assert_failure
  assert_output --partial "HTTP 500"
}

@test "linear_graphql: valid response with HTTP 200 returns success" {
  run_linear_graphql_with_mock "200" '{"data":{"viewer":{"id":"abc123"}}}'
  assert_success
  assert_output --partial '"viewer"'
}

@test "linear_graphql: network error (curl exits non-zero) returns error" {
  run_linear_graphql_with_mock "000" "" "1"
  assert_failure
  assert_output --partial "network error"
}

@test "linear_graphql: GraphQL error in response body returns error" {
  run_linear_graphql_with_mock "200" '{"errors":[{"message":"Variable teamKey is required"}],"data":null}'
  assert_failure
  assert_output --partial "GraphQL error"
}
