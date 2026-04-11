# Sorta.Fit -- Contributing

Thank you for your interest in contributing to Sorta. This document covers the workflow, conventions, and guidelines for making changes.

## Getting Started

1. Fork the repository on GitHub.
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/sorta.fit.git
   cd Sorta.Fit
   ```
3. Create a feature branch from `main`:
   ```bash
   git checkout -b your-branch-name main
   ```
4. Make your changes, test them, and commit.
5. Push your branch and open a pull request against `main`.

## Code Style

All bash scripts must follow these conventions:

- **Shebang:** `#!/usr/bin/env bash` on the first line.
- **Strict mode:** `set -euo pipefail` immediately after the shebang and comment header.
- **Logging:** Use the functions from `core/utils.sh` (`log_info`, `log_warn`, `log_error`, `log_step`). Do not use bare `echo` for status output.
- **Line endings:** Unix (LF) only. Configure your editor to save with LF. On Windows, set `git config core.autocrlf input`.
- **Indentation:** Two spaces. No tabs.
- **Variables:** Use uppercase for exported/environment variables (`BOARD_ADAPTER`). Use lowercase for local variables (`issue_key`). Quote all variable expansions (`"$var"`, not `$var`).
- **No hardcoded values:** Board URLs, status names, and IDs must come from environment variables or adapter config. Never hardcode project-specific values.
- **No external dependencies:** Bash scripts must only rely on tools listed in the prerequisites (bash, git, node, curl, gh, claude). Do not introduce Python, jq, or other tools.
- **Comments:** Include a file-level comment after the shebang explaining the script's purpose. Inline comments are welcome for non-obvious logic but should not restate what the code already says.

## Adding a Runner

1. Create `runners/{name}.sh`.

2. Use the standard boilerplate:
   ```bash
   #!/usr/bin/env bash
   # Runner: {Description}
   set -euo pipefail

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

   source "$SORTA_ROOT/core/config.sh"
   source "$SORTA_ROOT/core/utils.sh"
   source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
   ```

3. Follow the pattern used by existing runners:
   - Query cards from a lane using `board_get_cards_in_status`
   - For each card, fetch its details with `board_get_card_*` functions
   - Render a prompt using `render_template`
   - Run Claude with `claude -p`
   - Update the board with `board_update_description`, `board_add_comment`, and/or `board_transition`

4. Create a corresponding prompt template at `prompts/{name}.md` using `{{PLACEHOLDER}}` syntax for variable substitution.

5. Add your runner name to the `RUNNERS_ENABLED` list in `.env` to include it in the polling loop, or document it as a standalone/manual runner.

6. Document the runner in `docs/runners.md` following the format used for existing runners.

For a comprehensive guide covering the runner anatomy, prompt templates, .env configuration, and the board adapter interface, see [Writing New Runners](writing-runners.md).

## Adding an Adapter

1. Create `adapters/{name}.sh` implementing all `board_*` functions documented in `docs/adapters.md`.

2. Create `adapters/{name}.config.sh.example` with placeholder status and transition IDs.

3. Test the adapter:
   - Run `board_discover` and verify output
   - Test each `board_*` function individually against a test project
   - Run `bash runners/refine.sh` end-to-end to verify the full pipeline

4. Document the adapter in `docs/adapters.md`.

## Adding a Prompt Template

1. Create `prompts/{name}.md`.

2. Use `{{PLACEHOLDER}}` syntax for variables that will be substituted at runtime by `render_template`.

3. Be explicit about the expected output format. Include a format specification with exact headings and structure so Claude's output can be consumed reliably by the calling runner.

4. End the prompt with a reminder like "Output ONLY the {thing}. No preamble." to keep Claude's response clean.

## Testing

Sorta.Fit uses [bats-core](https://github.com/bats-core/bats-core) for automated testing. All changes to core modules must follow TDD -- write or update tests before changing production code.

### Running Tests

```bash
bash test.sh              # Run all tests
bash test.sh --unit       # Unit tests only
bash test.sh --integration # Integration tests only
npm test                  # Same as bash test.sh
```

After cloning, fetch the test library submodules:

```bash
git submodule update --init --recursive
```

### Test Requirements

- When changing a function in `core/utils.sh`, `core/config.sh`, `core/runner-lib.sh`, or `adapters/`, the corresponding test file in `tests/` must be updated in the same commit
- All tests must pass before opening a PR
- Unit tests go in `tests/unit/`, integration tests in `tests/integration/`
- Shared helpers go in `tests/helpers/setup.sh`

For full details on test structure, writing tests, and the validate mode, see [Testing and Validation](features/testing.md).

### Manual Testing

For end-to-end verification against a live board:

1. Create a test project on your issue board (e.g., a Jira project named `TEST`).
2. Configure `.env` to point at the test project.
3. Create a few cards in the To Do lane with titles and brief descriptions.
4. Run runners individually and verify the results on the board.
5. Validate config without running the loop: `bash core/loop.sh --validate`

## Pull Request Guidelines

- Keep PRs focused on a single change. One runner, one adapter, or one bug fix per PR.
- Include a clear description of what the PR does and how to test it.
- Ensure all scripts have the correct shebang and strict mode.
- Verify Unix line endings on all files.
- Do not include `.env` files, API tokens, or other secrets.

## Conventions Summary

| Convention | Rule |
|-----------|------|
| Shell | `#!/usr/bin/env bash` + `set -euo pipefail` |
| Logging | Use `core/utils.sh` functions |
| Line endings | LF only |
| Indentation | 2 spaces |
| Variables | Uppercase for env/exported, lowercase for local |
| Dependencies | bash, git, node, curl, gh, claude only |
| Secrets | Never committed, always via `.env` |
| Templates | `{{PLACEHOLDER}}` syntax in `prompts/*.md` |
