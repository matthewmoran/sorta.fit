# Architect Runner

The architect runner sits between `refine` and `code` in the pipeline. It picks up refined cards, analyzes the current codebase, and appends an implementation plan to the card description — giving the `code` runner a more actionable, codebase-aware spec to work from.

```
[Refined] --architect--> [Architected] --you--> [Agent] --code--> [QA]
```

## Overview

When a card reaches the architect's pickup lane, the runner:

1. Fetches the card's title, description, and comments
2. Renders the `prompts/architect.md` template with the card data
3. Passes the prompt to Claude Code CLI, which reads the codebase and produces a structured implementation plan
4. **Appends** the plan to the existing card description (the refined spec is preserved, not replaced)
5. Posts a comment indicating the card was architected
6. Transitions the card to the configured target lane

The architecture plan Claude produces includes:

- **Relevant Files** — file paths and why they matter for this card
- **Patterns to Follow** — existing codebase patterns the implementation should match
- **Implementation Steps** — concrete, ordered steps with file paths
- **Technology & Approach** — technology choices consistent with the codebase
- **Open Questions** — ambiguities the implementer should decide (omitted if none)

## Usage

### Running Standalone

```bash
bash runners/architect.sh
```

### In the Polling Loop

Add `architect` to `RUNNERS_ENABLED` in `.env`:

```bash
RUNNERS_ENABLED=refine,architect,code,review
```

The loop runs runners in the order listed. Place `architect` after `refine` and before `code` so cards flow through naturally.

## Configuration

All configuration is set in `.env`. Defaults are defined in `core/config.sh`.

| Variable | Purpose | Default |
|---|---|---|
| `RUNNER_ARCHITECT_FROM` | Status ID of the lane to pick up cards from | (empty) |
| `RUNNER_ARCHITECT_TO` | Status ID to transition cards to after architecting | (empty — no transition) |
| `MAX_CARDS_ARCHITECT` | Maximum cards to process per polling cycle | `5` |

### Finding Status IDs

Status IDs are board-specific. Use the setup wizard (`bash setup.sh`) to discover them, or call `board_discover` directly:

```bash
bash -c "source core/config.sh && source adapters/jira.sh && board_discover"
```

### Setup Wizard

The setup wizard UI includes the architect runner in its runner configuration panel. Lane routing fields (`RUNNER_ARCHITECT_FROM`, `RUNNER_ARCHITECT_TO`, `MAX_CARDS_ARCHITECT`) are exposed in the wizard and saved to `.env` when you complete setup.

## Examples

### Typical Pipeline Configuration

A human-gated workflow where you review the architecture plan before moving cards to the Agent lane:

```
RUNNERS_ENABLED=refine,architect,code,review,bounce,merge
RUNNER_REFINE_FROM=10000      # To Do
RUNNER_REFINE_TO=10070        # Refined
RUNNER_ARCHITECT_FROM=10070   # Refined
RUNNER_ARCHITECT_TO=10080     # Architected
RUNNER_CODE_FROM=10090        # Agent
RUNNER_CODE_TO=10050          # QA
```

Cards flow: To Do -> Refined -> Architected -> (you review) -> Agent -> QA.

### Fully Autonomous Configuration

Skip the human review gate between architect and code:

```
RUNNER_ARCHITECT_FROM=10070   # Refined
RUNNER_ARCHITECT_TO=10090     # Agent (skip Architected, go straight to code)
```

### Card Description After Architecting

The architect runner appends its output below the existing refined description, separated by a horizontal rule:

```markdown
## Summary
(original refined spec content...)

---
## Architecture Plan (Sorta)
## Relevant Files
- src/api/handler.ts — main request handler, needs new endpoint
- src/db/queries.ts — existing query patterns to follow

## Patterns to Follow
- REST handlers in src/api/ follow the controller pattern in handler.ts

## Implementation Steps
1. Add new query function in src/db/queries.ts
2. Create handler in src/api/handler.ts following existing pattern
3. Register route in src/api/routes.ts

## Technology & Approach
- Use existing Express middleware chain
- Follow the repository pattern already in src/db/
```

### Skipping Transition

If `RUNNER_ARCHITECT_TO` is left empty, the runner updates the card description and posts a comment but does not move the card to a new lane. This is useful if you want to architect cards in place without changing their board status.
