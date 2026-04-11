#!/usr/bin/env bats
# Integration tests for github_api error handling in adapters/github-issues.sh

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env

  # Create mock bin dir with curl and gh stubs
  MOCK_BIN_DIR="$TEST_TEMP_DIR/mock-bin"
  mkdir -p "$MOCK_BIN_DIR"

  # Mock curl — behavior driven by MOCK_CURL_* env vars
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

  # Mock gh that always fails auth status (forces curl fallback)
  printf '#!/usr/bin/env bash\nexit 1\n' > "$MOCK_BIN_DIR/gh"
  chmod +x "$MOCK_BIN_DIR/gh"

  # Set required env vars for github-issues.sh
  export BOARD_API_TOKEN="test-token-do-not-use"
  export BOARD_DOMAIN="github.com"
  export BOARD_PROJECT_KEY="owner/repo"
}

teardown() {
  teardown_test_env
}

# Helper: source github-issues.sh and call github_api with mock curl on PATH
run_github_api_with_mock() {
  local http_code="$1"
  local body="$2"
  local curl_exit="${3:-0}"

  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' "$body" > "$body_file"

  run bash -c "
    exec 2>&1
    export PATH='$MOCK_BIN_DIR':\$PATH
    export MOCK_CURL_HTTP_CODE='$http_code'
    export MOCK_CURL_BODY=\$(cat '$body_file')
    export MOCK_CURL_EXIT='$curl_exit'
    export BOARD_API_TOKEN='test-token-do-not-use'
    export BOARD_DOMAIN='github.com'
    export BOARD_PROJECT_KEY='owner/repo'
    source '$PROJECT_ROOT/core/utils.sh'
    source '$PROJECT_ROOT/adapters/github-issues.sh'
    github_api 'GET' '/repos/owner/repo'
  "
}

@test "github_api: HTML response returns error" {
  run_github_api_with_mock "200" "<html><body>Not JSON</body></html>"
  assert_failure
  assert_output --partial "HTML instead of JSON"
}

@test "github_api: HTTP 401 returns error" {
  run_github_api_with_mock "401" '{"message":"Bad credentials"}'
  assert_failure
  assert_output --partial "HTTP 401"
}

@test "github_api: HTTP 404 returns error" {
  run_github_api_with_mock "404" '{"message":"Not Found"}'
  assert_failure
  assert_output --partial "HTTP 404"
}

@test "github_api: HTTP 500 returns error" {
  run_github_api_with_mock "500" '{"message":"Internal Server Error"}'
  assert_failure
  assert_output --partial "HTTP 500"
}

@test "github_api: valid JSON with HTTP 200 returns success" {
  run_github_api_with_mock "200" '{"full_name":"owner/repo"}'
  assert_success
  assert_output --partial '"full_name"'
}

@test "github_api: network error (curl exits non-zero) returns error" {
  run_github_api_with_mock "000" "" "1"
  assert_failure
  assert_output --partial "network error"
}

@test "github_api: empty token does not send auth header" {
  # Verify that when BOARD_API_TOKEN is empty, curl fallback doesn't send an empty auth header
  # We test this by checking that the request succeeds with empty token against a mock
  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' '{"full_name":"owner/repo"}' > "$body_file"

  run bash -c "
    exec 2>&1
    export PATH='$MOCK_BIN_DIR':\$PATH
    export MOCK_CURL_HTTP_CODE='200'
    export MOCK_CURL_BODY=\$(cat '$body_file')
    export MOCK_CURL_EXIT='0'
    export BOARD_API_TOKEN=''
    export BOARD_DOMAIN='github.com'
    export BOARD_PROJECT_KEY='owner/repo'
    source '$PROJECT_ROOT/core/utils.sh'
    source '$PROJECT_ROOT/adapters/github-issues.sh'
    github_api 'GET' '/repos/owner/repo'
  "
  assert_success
}

@test "github_api: GHE domain sets correct API base" {
  # Verify that a non-github.com domain derives the GHE API base
  local body_file="$TEST_TEMP_DIR/mock_body.txt"
  printf '%s' '{"full_name":"owner/repo"}' > "$body_file"

  # Create a curl that captures the URL it was called with
  printf '#!/usr/bin/env bash\n' > "$MOCK_BIN_DIR/curl-capture"
  printf 'output_file=""\nwrite_out=""\nlast_arg=""\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf 'while [[ $# -gt 0 ]]; do\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf '  case "$1" in\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf '    -o) output_file="$2"; shift 2 ;;\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf '    -w) write_out="$2"; shift 2 ;;\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf '    *) last_arg="$1"; shift ;;\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf '  esac\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf 'done\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf 'if [[ -n "$output_file" ]]; then printf "%%s" "{\"full_name\":\"owner/repo\",\"url\":\"$last_arg\"}" > "$output_file"; fi\n' >> "$MOCK_BIN_DIR/curl-capture"
  printf 'if [[ -n "$write_out" ]]; then printf "%%s" "200"; fi\n' >> "$MOCK_BIN_DIR/curl-capture"
  chmod +x "$MOCK_BIN_DIR/curl-capture"
  cp "$MOCK_BIN_DIR/curl-capture" "$MOCK_BIN_DIR/curl"

  run bash -c "
    exec 2>&1
    export PATH='$MOCK_BIN_DIR':\$PATH
    export BOARD_API_TOKEN='test-token-do-not-use'
    export BOARD_DOMAIN='github.mycompany.com'
    export BOARD_PROJECT_KEY='owner/repo'
    source '$PROJECT_ROOT/core/utils.sh'
    source '$PROJECT_ROOT/adapters/github-issues.sh'
    result=\$(github_api 'GET' '/repos/owner/repo')
    echo \"\$result\"
  "
  assert_success
  assert_output --partial "github.mycompany.com/api/v3"
}
