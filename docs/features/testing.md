# Testing and Validation

## Overview

Sorta.Fit uses [bats-core](https://github.com/bats-core/bats-core) as its test framework, with bats-support and bats-assert for assertion helpers. Tests cover the core libraries (`core/utils.sh`, `core/config.sh`, `core/runner-lib.sh`), adapter error handling, config loading, and the `--validate` dry-run mode for `core/loop.sh`.

The test suite is designed around test-driven development: tests are written or updated before changing production code, and all tests must pass before merging.

## Usage

### Running Tests

```bash
bash test.sh              # Run all tests (unit + integration)
bash test.sh --unit       # Run unit tests only
bash test.sh --integration # Run integration tests only
npm test                  # Same as bash test.sh
```

### Prerequisites

bats-core and its helper libraries are installed as git submodules. After cloning, fetch them:

```bash
git submodule update --init --recursive
```

The test runner checks for bats-core and exits with a clear error if the submodules are missing.

### Validate Mode

`core/loop.sh` accepts a `--validate` flag that checks configuration and exits without starting the polling loop:

```bash
bash core/loop.sh --validate
```

This mode:
- Loads and validates `.env` configuration (adapter, domain, credentials, paths)
- Verifies the adapter config file exists
- Checks that each enabled runner's script file exists
- Warns if any runner is missing its `RUNNER_<NAME>_FROM` lane configuration
- Exits `0` on success, `1` on failure
- Skips preflight checks (does not require `claude` or `gh` to be installed)
- Skips lock acquisition (safe to run concurrently)

Validate mode is useful for CI environments, setup verification, and debugging configuration issues without needing all runtime dependencies installed.

## Test Structure

```
tests/
  unit/                          # Pure-function tests, no external deps
    utils.bats                   # slugify, matches_type_filter, extract_pr_url,
                                 #   lock_acquire/release, require_command, is_rate_limited
    render-template.bats         # render_template (depends on Node.js)
    config.bats                  # Config validation: adapter enum, domain regex,
                                 #   TARGET_REPO path checks, required variables
    runner-lib.bats              # runner_transition guard logic, extract_pr_url,
                                 #   setup_worktree safety checks
  integration/                   # Multi-module interaction tests
    config-loading.bats          # Full config loading pipeline, defaults, overrides
    adapter-validation.bats      # jira_curl error handling with mocked curl
    validate-mode.bats           # --validate flag on core/loop.sh
  helpers/
    setup.sh                     # Shared test utilities (temp dirs, mock env, helpers)
  libs/                          # Git submodules (not committed directly)
    bats-core/
    bats-support/
    bats-assert/
```

### Test File Mapping

| Source file | Test file(s) |
|-------------|-------------|
| `core/utils.sh` | `tests/unit/utils.bats`, `tests/unit/render-template.bats` |
| `core/config.sh` | `tests/unit/config.bats`, `tests/integration/config-loading.bats` |
| `core/runner-lib.sh` | `tests/unit/runner-lib.bats` |
| `core/loop.sh` | `tests/integration/validate-mode.bats` |
| `adapters/jira.sh` | `tests/integration/adapter-validation.bats` |

## Writing Tests

### Test Isolation

Every test runs in an isolated temporary directory. The shared helper (`tests/helpers/setup.sh`) provides:

- **`setup_test_env`** -- Creates a temp directory, sets `SORTA_ROOT` to it, and creates the directory structure tests expect (`core/`, `adapters/`, `runners/`).
- **`teardown_test_env`** -- Removes the temp directory. Call this in your `teardown()` function.
- **`write_valid_env`** -- Writes a minimal valid `.env` file with safe dummy values.
- **`create_test_git_repo`** -- Creates an initialized git repository for `TARGET_REPO` tests. Returns the repo path via stdout.
- **`run_config`** -- Runs `config.sh` in a clean subshell with board variables unset, so only `.env` values are tested.
- **`sed_inplace`** -- Portable `sed -i` wrapper that works on GNU sed (Linux, Windows git-bash).

### Basic Test Pattern

```bash
#!/usr/bin/env bats

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

@test "slugify: converts uppercase to lowercase" {
  run slugify "HELLO WORLD"
  assert_success
  assert_output "hello-world"
}
```

### Mocking External Commands

For tests that need to mock external tools (like `curl` in adapter tests), create a mock script in a temp `bin/` directory and prepend it to `$PATH`:

```bash
setup() {
  setup_test_env
  MOCK_BIN="$TEST_TEMP_DIR/bin"
  mkdir -p "$MOCK_BIN"
  # Create a mock curl that returns configurable responses
  printf '#!/usr/bin/env bash\n' > "$MOCK_BIN/curl"
  printf 'cat "$MOCK_RESPONSE_FILE"\n' >> "$MOCK_BIN/curl"
  chmod +x "$MOCK_BIN/curl"
  export PATH="$MOCK_BIN:$PATH"
}
```

### Testing Functions That Call `exit`

`config.sh` calls `exit 1` on validation failures. To prevent the test process from dying, run it in a subshell using the `run_config` helper or `run bash -c "..."`:

```bash
@test "missing BOARD_API_TOKEN exits with error" {
  write_valid_env
  sed_inplace '/BOARD_API_TOKEN/d' "$TEST_TEMP_DIR/.env"
  run_config
  assert_failure
  assert_output --partial "BOARD_API_TOKEN"
}
```

### What Gets Tested

**Unit tests** cover individual functions in isolation:
- String manipulation (`slugify`, `matches_type_filter`)
- URL extraction (`extract_pr_url`)
- Lock management (`lock_acquire`, `lock_release`, stale lock recovery)
- Config validation (adapter enum, domain regex, path checks, required variables)
- Template rendering (substitution, special characters, missing keys, edge cases)
- Runner library guards (`runner_transition` with missing/valid transitions, protected branch checks)

**Integration tests** cover multi-module interactions:
- Full config loading pipeline with defaults and overrides
- Adapter HTTP error handling (HTML responses, 4xx/5xx status codes, valid JSON)
- Validate mode end-to-end (valid config passes, missing runner fails)

## CI

Tests run automatically on GitHub Actions for pushes and pull requests to `main` and `dev`. The workflow checks out submodules, sets up Node.js, and runs `bash test.sh`. No matrix builds or caching -- unit tests complete in seconds.

All tests must pass before a PR can be merged. When changing a function in `core/utils.sh`, `core/config.sh`, `core/runner-lib.sh`, or `adapters/`, the corresponding test file must be updated in the same commit.
