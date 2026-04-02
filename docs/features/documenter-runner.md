# Documenter Runner

The documenter runner generates and maintains project documentation from board cards. When a card reaches the configured lane, the runner creates an isolated worktree, passes the card spec and codebase to Claude, and opens a PR with the resulting documentation changes.

```
[Done] --documenter--> PR opened --> [Done]
```

## Overview

When a card reaches the documenter's pickup lane, the runner:

1. Fetches the card's title, description, and comments
2. Skips cards that have already been documented (checks for "Docs PR opened" or "no documentation changes needed" in comments)
3. Creates an isolated git worktree on a new branch (`claude/{ISSUE_KEY}-docs-{slug}`)
4. Copies `.claude/settings.local.json` into the worktree so Claude has file permissions
5. Renders the `prompts/documenter.md` template with the card data, docs directory, and organization strategy
6. Passes the prompt to Claude Code CLI, which reads the card spec, explores relevant source code, and produces or updates markdown files
7. If Claude produces commits, pushes the branch and opens a PR via `gh pr create`
8. Posts a board comment linking the PR
9. Transitions the card to the configured target lane
10. Cleans up the worktree

If Claude produces no commits, the runner logs a warning, posts a "no documentation changes needed" comment, and moves on without transitioning the card or opening a PR.

## Usage

### Running Standalone

```bash
bash runners/documenter.sh
```

### In the Polling Loop

Add `documenter` to `RUNNERS_ENABLED` in `.env`:

```bash
RUNNERS_ENABLED=refine,architect,code,review,merge,documenter
```

Place `documenter` after `merge` (or wherever in the pipeline makes sense for your workflow). Cards typically reach the documenter after implementation is complete.

## Configuration

All configuration is set in `.env`. Defaults are defined in `core/config.sh`.

| Variable | Purpose | Default |
|---|---|---|
| `RUNNER_DOCUMENTER_FROM` | Status ID of the lane to pick up cards from | (empty) |
| `RUNNER_DOCUMENTER_TO` | Status ID to transition cards to after documenting | (empty -- no transition) |
| `MAX_CARDS_DOCUMENTER` | Maximum cards to process per polling cycle | `5` |
| `DOCS_DIR` | Target directory for generated docs (relative to repo root) | `docs` |
| `DOCS_ORGANIZE_BY` | Organization strategy for documentation | `feature` |

### Finding Status IDs

Status IDs are board-specific. Use the setup wizard (`bash setup.sh`) to discover them, or call `board_discover` directly:

```bash
bash -c "source core/config.sh && source adapters/jira.sh && board_discover"
```

### Setup Wizard

The setup wizard UI includes the documenter runner in its runner configuration panel. Lane routing fields and the docs-specific settings are exposed in the wizard and saved to `.env` when you complete setup.

## How It Works

### Worktree Isolation

Like the code runner, the documenter never modifies the main working tree. Each card gets its own worktree under `.worktrees/{ISSUE_KEY}`, with a branch named `claude/{ISSUE_KEY}-docs-{slug}`. The `-docs-` segment distinguishes documentation branches from code branches created by the code runner.

Protected branches (`main`, `master`, `dev`, `develop`) are never checked out.

### Documentation Organization

With `DOCS_ORGANIZE_BY=feature` (the default), Claude organizes documentation by overall feature rather than by individual card:

- New features get a new file in `docs/features/` (e.g., `docs/features/board-adapters.md`)
- Enhancements to existing features update the existing document rather than creating a new file
- Files use kebab-case naming

This prevents documentation sprawl where every card produces a separate file. Multiple cards relating to the same feature contribute to a single, consolidated document.

### PR Creation

When Claude produces commits, the runner pushes the branch and opens a PR with:

- A title in the format `{ISSUE_KEY}: docs -- {card title}`
- A body containing the documentation changes summary and a review checklist
- Base branch set to `GIT_BASE_BRANCH`

The runner posts a comment on the board card linking to the PR.

### No-Op Handling

If Claude determines no documentation changes are needed (zero commits on the branch), the runner:

- Logs a warning
- Posts a "no documentation changes needed" comment on the card
- Does **not** transition the card
- Does **not** open a PR
- Continues to the next card

On subsequent runs, cards with a "no documentation changes needed" comment are skipped automatically.

## Examples

### Typical Pipeline Configuration

Documentation generated after cards reach Done:

```
RUNNERS_ENABLED=refine,architect,code,review,merge,documenter
RUNNER_DOCUMENTER_FROM=10037   # Done
RUNNER_DOCUMENTER_TO=10037     # Done (stays in place)
```

Cards flow: To Do -> Refined -> Architected -> Agent -> QA -> Done -> (documenter generates docs PR).

### Custom Docs Directory

Place generated documentation in a different directory:

```bash
DOCS_DIR=documentation
```

Claude will create and update files under `documentation/features/` instead of the default `docs/features/`.

### Skipping Transition

If `RUNNER_DOCUMENTER_TO` is left empty, the runner opens the docs PR and posts a comment but does not move the card to a new lane:

```bash
RUNNER_DOCUMENTER_FROM=10037
RUNNER_DOCUMENTER_TO=
```
