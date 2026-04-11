#!/usr/bin/env bats
# Integration tests for jira_curl error handling in adapters/jira.sh

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env

  # Create mock curl bin dir with a script that reads behavior from env vars
  MOCK_BIN_DIR="$TEST_TEMP_DIR/mock-bin"
  mkdir -p "$MOCK_BIN_DIR"

  # Write mock curl script using printf to avoid CRLF issues on Windows
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

  # Set required env vars for jira.sh
  export BOARD_EMAIL="test@example.com"
  export BOARD_API_TOKEN="test-token-do-not-use"
  export BOARD_DOMAIN="test.atlassian.net"
  export BOARD_PROJECT_KEY="TEST"
}

teardown() {
  teardown_test_env
}

# Helper: source jira.sh and call jira_curl with mock curl on PATH
run_jira_curl_with_mock() {
  local http_code="$1"
  local body="$2"
  local curl_exit="${3:-0}"

  # Write the body to a file to avoid quoting issues
  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' "$body" > "$body_file"

  run bash -c "
    exec 2>&1
    export PATH='$MOCK_BIN_DIR':\$PATH
    export MOCK_CURL_HTTP_CODE='$http_code'
    export MOCK_CURL_BODY=\$(cat '$body_file')
    export MOCK_CURL_EXIT='$curl_exit'
    export BOARD_EMAIL='test@example.com'
    export BOARD_API_TOKEN='test-token-do-not-use'
    export BOARD_DOMAIN='test.atlassian.net'
    source '$PROJECT_ROOT/core/utils.sh'
    source '$PROJECT_ROOT/adapters/jira.sh'
    jira_curl 'https://test.atlassian.net/rest/api/3/test'
  "
}

@test "jira_curl: HTML response returns error" {
  run_jira_curl_with_mock "200" "<html><body>Not JSON</body></html>"
  assert_failure
  assert_output --partial "HTML instead of JSON"
}

@test "jira_curl: HTTP 401 returns error" {
  run_jira_curl_with_mock "401" '{"error":"unauthorized"}'
  assert_failure
  assert_output --partial "HTTP 401"
}

@test "jira_curl: HTTP 404 returns error" {
  run_jira_curl_with_mock "404" '{"error":"not found"}'
  assert_failure
  assert_output --partial "HTTP 404"
}

@test "jira_curl: HTTP 500 returns error" {
  run_jira_curl_with_mock "500" '{"error":"server error"}'
  assert_failure
  assert_output --partial "HTTP 500"
}

@test "jira_curl: valid JSON with HTTP 200 returns success" {
  run_jira_curl_with_mock "200" '{"key":"TEST-1","fields":{}}'
  assert_success
  assert_output --partial '{"key":"TEST-1"'
}

@test "jira_curl: network error (curl exits non-zero) returns error" {
  run_jira_curl_with_mock "000" "" "1"
  assert_failure
  assert_output --partial "network error"
}

# ── board_get_card_status ────────────────────────────────────────────────────

# Helper: source jira.sh and call board_get_card_status with mock curl on PATH
run_board_get_card_status_with_mock() {
  local http_code="$1"
  local body="$2"

  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' "$body" > "$body_file"

  run bash -c "
    exec 2>&1
    export PATH='$MOCK_BIN_DIR':\$PATH
    export MOCK_CURL_HTTP_CODE='$http_code'
    export MOCK_CURL_BODY=\$(cat '$body_file')
    export MOCK_CURL_EXIT='0'
    export BOARD_EMAIL='test@example.com'
    export BOARD_API_TOKEN='test-token-do-not-use'
    export BOARD_DOMAIN='test.atlassian.net'
    source '$PROJECT_ROOT/core/utils.sh'
    source '$PROJECT_ROOT/adapters/jira.sh'
    board_get_card_status 'TEST-1'
  "
}

@test "board_get_card_status: returns status name and ID" {
  local mock_json='{"fields":{"status":{"name":"In Progress","id":"10000"}}}'
  run_board_get_card_status_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "In Progress|10000"
}

@test "board_get_card_status: returns done status" {
  local mock_json='{"fields":{"status":{"name":"Done","id":"10037"}}}'
  run_board_get_card_status_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "Done|10037"
}

# ── board_get_card_links ─────────────────────────────────────────────────────

# Helper: source jira.sh and call board_get_card_links with mock curl on PATH
run_board_get_card_links_with_mock() {
  local http_code="$1"
  local body="$2"

  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' "$body" > "$body_file"

  run bash -c "
    exec 2>&1
    export PATH='$MOCK_BIN_DIR':\$PATH
    export MOCK_CURL_HTTP_CODE='$http_code'
    export MOCK_CURL_BODY=\$(cat '$body_file')
    export MOCK_CURL_EXIT='0'
    export BOARD_EMAIL='test@example.com'
    export BOARD_API_TOKEN='test-token-do-not-use'
    export BOARD_DOMAIN='test.atlassian.net'
    export BOARD_PROJECT_KEY='TEST'
    source '$PROJECT_ROOT/core/utils.sh'
    source '$PROJECT_ROOT/adapters/jira.sh'
    board_get_card_links 'TEST-1'
  "
}

@test "board_get_card_links: parses blocks/is-blocked-by issue links" {
  local mock_json='{"fields":{"issuelinks":[{"type":{"name":"Blocks","inward":"is blocked by","outward":"blocks"},"inwardIssue":{"key":"TEST-2","fields":{"status":{"name":"In Progress","id":"10000"}}}}],"parent":null,"subtasks":[],"labels":[],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "blocks|inward|TEST-2|In Progress|10000"
}

@test "board_get_card_links: parses outward block link" {
  local mock_json='{"fields":{"issuelinks":[{"type":{"name":"Blocks","inward":"is blocked by","outward":"blocks"},"outwardIssue":{"key":"TEST-3","fields":{"status":{"name":"Done","id":"10037"}}}}],"parent":null,"subtasks":[],"labels":[],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "blocks|outward|TEST-3|Done|10037"
}

@test "board_get_card_links: parses parent relationship" {
  local mock_json='{"fields":{"issuelinks":[],"parent":{"key":"TEST-PARENT","fields":{"status":{"name":"In Progress","id":"10000"}}},"subtasks":[],"labels":[],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "parent|inward|TEST-PARENT|In Progress|10000"
}

@test "board_get_card_links: parses subtask relationships" {
  local mock_json='{"fields":{"issuelinks":[],"parent":null,"subtasks":[{"key":"TEST-SUB1","fields":{"status":{"name":"Done","id":"10037"}}},{"key":"TEST-SUB2","fields":{"status":{"name":"In Progress","id":"10000"}}}],"labels":[],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "subtask|outward|TEST-SUB1|Done|10037"
  assert_output --partial "subtask|outward|TEST-SUB2|In Progress|10000"
}

@test "board_get_card_links: parses depends-on label" {
  local mock_json='{"fields":{"issuelinks":[],"parent":null,"subtasks":[],"labels":["depends-on:PROJ-99","feature"],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "label|inward|PROJ-99|Unknown|"
}

@test "board_get_card_links: parses blocked label" {
  local mock_json='{"fields":{"issuelinks":[],"parent":null,"subtasks":[],"labels":["blocked"],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "label|inward||Unknown|"
}

@test "board_get_card_links: empty links returns no output" {
  local mock_json='{"fields":{"issuelinks":[],"parent":null,"subtasks":[],"labels":[],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output ""
}

@test "board_get_card_links: mixed links and labels" {
  local mock_json='{"fields":{"issuelinks":[{"type":{"name":"Blocks","inward":"is blocked by","outward":"blocks"},"inwardIssue":{"key":"TEST-5","fields":{"status":{"name":"Done","id":"10037"}}}}],"parent":{"key":"TEST-EPIC","fields":{"status":{"name":"In Progress","id":"10000"}}},"subtasks":[],"labels":["depends-on:OTHER-1"],"status":{"name":"To Do","id":"10001"}}}'
  run_board_get_card_links_with_mock "200" "$mock_json"
  assert_success
  assert_output --partial "blocks|inward|TEST-5|Done|10037"
  assert_output --partial "parent|inward|TEST-EPIC|In Progress|10000"
  assert_output --partial "label|inward|OTHER-1|Unknown|"
}
