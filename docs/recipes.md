# Sorta.Fit -- Recipes

Recipes are the individual automation steps that Sorta runs. Each recipe reads cards from a specific board lane, processes them with Claude, and updates the board. The main runner (`core/runner.sh`) executes enabled recipes in sequence on each polling cycle, but any recipe can also be run standalone.

## Overview

| Recipe | Reads From | Writes To | Moves Card | Description |
|--------|-----------|-----------|------------|-------------|
| refine | To Do | Refined | Yes | Generates structured spec from card title |
| code | Agent | QA | Yes | Implements card, creates branch and PR |
| review | QA | QA | No | Reviews PR, posts GitHub review |
| triage | To Do | Refined | Yes | Analyzes bug report, adds triage to description |
| documenter | (configurable) | (configurable) | Yes | Generates/updates feature docs, opens PR |
| release-notes | (manual) | stdout | No | Generates changelog from git history |

---

## refine

**File:** `recipes/refine.sh`
**Prompt:** `prompts/refine.md`

### What It Does

Picks up cards in the To Do lane that have a title but lack a structured specification. For each card, it feeds the title, existing description, and comments to Claude along with access to the codebase. Claude produces a structured spec with acceptance criteria, technical context, testing requirements, and open questions. The spec replaces the card's description, a comment is added noting the refinement, and the card moves to Refined.

### Lane Flow

```
To Do --> [Claude refines] --> Refined
```

### Config Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `MAX_CARDS_REFINE` | `5` | Maximum cards to process per cycle |

### Running Standalone

```bash
bash recipes/refine.sh
```

### Customizing the Prompt

Edit `prompts/refine.md`. The template uses these placeholders:

| Placeholder | Value |
|-------------|-------|
| `{{CARD_KEY}}` | Issue key (e.g., PROJ-42) |
| `{{CARD_TITLE}}` | Card title / summary |
| `{{CARD_DESCRIPTION}}` | Current description text |
| `{{CARD_COMMENTS}}` | All comments on the card |

The output format is defined in the prompt template. Modify the headings and sections to match your team's spec format.

---

## code

**File:** `recipes/code.sh`
**Prompt:** `prompts/code.md`

### What It Does

Picks up cards in the Agent lane. For each card:

1. Creates a feature branch named `claude/{ISSUE_KEY}-{slug}` from `origin/{GIT_BASE_BRANCH}`
2. Creates a git worktree in `.worktrees/{ISSUE_KEY}` (never touches the main working tree)
3. Copies Claude permissions (`.claude/settings.local.json`) into the worktree
4. Installs dependencies (`npm ci` with fallback to `npm install`)
5. Runs Claude Code with the implementation prompt, giving it the card spec, comments (which may include reviewer feedback from a previous attempt), and safety rules
6. If Claude produces commits, creates a PR via `gh pr create`
7. Adds a comment to the card with the PR URL
8. Moves the card to QA
9. Removes the worktree

### Lane Flow

```
Agent --> [worktree + Claude codes] --> branch pushed --> PR created --> QA
```

### Config Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `MAX_CARDS_CODE` | `2` | Maximum cards to implement per cycle |
| `GIT_BASE_BRANCH` | `main` | Base branch for new feature branches |

### Safety Features

- Branches are always prefixed with `claude/` and named after the issue key.
- A protected-branch check prevents accidental work on `main`, `master`, `dev`, or `develop`.
- Work happens in isolated git worktrees, so the main working tree is never modified.
- If Claude produces zero commits, the card is not moved; a comment is added noting the failure.
- No force pushes are ever used.

### Running Standalone

```bash
bash recipes/code.sh
```

### Customizing the Prompt

Edit `prompts/code.md`. The template uses these placeholders:

| Placeholder | Value |
|-------------|-------|
| `{{CARD_KEY}}` | Issue key |
| `{{CARD_TITLE}}` | Card title |
| `{{CARD_DESCRIPTION}}` | Full card description (the refined spec) |
| `{{CARD_COMMENTS}}` | All comments (may include feedback from a prior attempt) |
| `{{BRANCH_NAME}}` | The feature branch name |

---

## review

**File:** `recipes/review.sh`
**Prompt:** `prompts/review.md`

### What It Does

Picks up cards in the QA lane. For each card:

1. Reads the card's comments to find a GitHub PR URL
2. Skips if no PR URL is found or if the card has already been reviewed (checks for "AI Code Review" in comments)
3. Fetches the PR diff via `gh pr diff`
4. Truncates diffs larger than 100,000 characters
5. Runs Claude with the review prompt and the full diff
6. Determines review type from Claude's output: approve, request-changes, or comment
7. Posts the review to GitHub via `gh pr review`
8. Adds a summary comment to the card

The review recipe intentionally does NOT move the card. The card stays in QA for a human to make the final call on whether to merge and move to Done.

### Lane Flow

```
QA --> [Claude reviews PR] --> QA (card stays)
```

### Config Variables

No recipe-specific config variables. The recipe processes up to 10 QA cards per cycle (hardcoded).

### Running Standalone

```bash
bash recipes/review.sh
```

### Customizing the Prompt

Edit `prompts/review.md`. The template uses these placeholders:

| Placeholder | Value |
|-------------|-------|
| `{{CARD_KEY}}` | Issue key |
| `{{PR_URL}}` | Full GitHub PR URL |
| `{{PR_DIFF}}` | The complete diff (may be truncated for large PRs) |

---

## triage

**File:** `recipes/triage.sh`
**Prompt:** `prompts/triage.md`

### What It Does

Picks up cards from the To Do lane that look like bugs (based on issue type or keywords like "bug", "fix", "crash", "error" in the title). For each matching card:

1. Feeds the card title and description to Claude along with codebase access
2. Claude analyzes the bug report, searches for related code, and produces a triage report with severity, likely root cause, affected files, and suggested fix
3. The triage report is appended to the existing description (not replaced)
4. A comment is added noting the triage
5. The card moves to Refined

### Lane Flow

```
To Do --> [filter bugs] --> [Claude triages] --> Refined
```

### Config Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `MAX_CARDS_TRIAGE` | `5` | Maximum cards to check per cycle |

### Running Standalone

```bash
bash recipes/triage.sh
```

### Customizing the Prompt

Edit `prompts/triage.md`. The template uses these placeholders:

| Placeholder | Value |
|-------------|-------|
| `{{CARD_KEY}}` | Issue key |
| `{{CARD_TITLE}}` | Card title |
| `{{CARD_DESCRIPTION}}` | Current description (the bug report) |

---

## documenter

**File:** `recipes/documenter.sh`
**Prompt:** `prompts/documenter.md`

### What It Does

Picks up cards from a configurable lane (default: Done). For each card:

1. Creates a feature branch named `claude/{ISSUE_KEY}-docs-{slug}` from `origin/{GIT_BASE_BRANCH}`
2. Creates a git worktree in `.worktrees/{ISSUE_KEY}` (never touches the main working tree)
3. Copies Claude permissions (`.claude/settings.local.json`) into the worktree
4. Installs dependencies (`npm ci` with fallback to `npm install`)
5. Runs Claude Code with the documentation prompt, giving it the card spec, comments, and the target docs directory
6. Claude reads the card spec and relevant source code, then creates or updates markdown files in `{DOCS_DIR}/features/`
7. If Claude produces commits, pushes the branch and creates a PR via `gh pr create`
8. Adds a comment to the card with the PR URL
9. Transitions the card to the configured lane
10. Removes the worktree

Documentation is organized by **overall feature**, not by individual card. If an existing doc covers the feature, Claude updates it rather than creating a new file. Enhancements to existing features revise the existing document.

### Lane Flow

```
(configurable) --> [worktree + Claude writes docs] --> branch pushed --> PR created --> (configurable)
```

### Config Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `MAX_CARDS_DOCUMENTER` | `5` | Maximum cards to process per cycle |
| `GIT_BASE_BRANCH` | `main` | Base branch for new feature branches |
| `DOCS_DIR` | `docs` | Target directory for generated documentation |
| `DOCS_ORGANIZE_BY` | `feature` | Organization strategy for doc files |

### Safety Features

- Branches are always prefixed with `claude/` and include `-docs-` plus the issue key.
- A protected-branch check prevents accidental work on `main`, `master`, `dev`, or `develop`.
- Work happens in isolated git worktrees, so the main working tree is never modified.
- If Claude produces zero commits, the card is not moved; a comment is added noting no changes were needed.
- No force pushes are ever used.

### Running Standalone

```bash
bash recipes/documenter.sh
```

### Customizing the Prompt

Edit `prompts/documenter.md`. The template uses these placeholders:

| Placeholder | Value |
|-------------|-------|
| `{{CARD_KEY}}` | Issue key |
| `{{CARD_TITLE}}` | Card title |
| `{{CARD_DESCRIPTION}}` | Full card description (the spec) |
| `{{CARD_COMMENTS}}` | All comments on the card |
| `{{BRANCH_NAME}}` | The feature branch name |
| `{{BASE_BRANCH}}` | The base branch name |
| `{{DOCS_DIR}}` | Target docs directory |
| `{{DOCS_ORGANIZE_BY}}` | Organization strategy |

---

## release-notes

**File:** `recipes/release-notes.sh`

### What It Does

A manual-run recipe that generates user-facing release notes from git history. It:

1. Takes a `since` parameter (git tag, date, or commit SHA)
2. Collects all non-merge commits since that reference
3. Sends the commit list to Claude with instructions to group into: New Features, Improvements, Bug Fixes, Breaking Changes
4. Outputs the formatted release notes to stdout (or to a file if a second argument is provided)

This recipe does not interact with the issue board at all. It only uses git history and Claude.

### Lane Flow

Not applicable. This recipe is run manually and does not read or write board lanes.

### Running Standalone

```bash
# Output to terminal
bash recipes/release-notes.sh v1.2.0

# Output to file
bash recipes/release-notes.sh v1.2.0 RELEASE_NOTES.md

# Since a date
bash recipes/release-notes.sh 2026-01-01
```

### Config Variables

No recipe-specific config variables. The recipe only needs a valid `.env` for Claude access.

---

## Adding a New Recipe

To create a custom recipe:

1. Create `recipes/{name}.sh` with the standard shebang and strict mode:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   ```

2. Source the core modules and adapter:
   ```bash
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

   source "$SORTA_ROOT/core/config.sh"
   source "$SORTA_ROOT/core/utils.sh"
   source "$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
   ```

3. Follow the pattern: get cards, render prompt, call Claude, update board.

4. Create a prompt template in `prompts/{name}.md` with `{{PLACEHOLDER}}` syntax.

5. Add the recipe name to `RECIPES_ENABLED` in `.env` to include it in the polling loop, or run it standalone with `bash recipes/{name}.sh`.

For a detailed walkthrough with annotated code, a skeleton template, and a full checklist, see [Writing New Runners](writing-runners.md).
