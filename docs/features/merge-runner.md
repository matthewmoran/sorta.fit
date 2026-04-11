# Merge Runner

## Overview

The merge runner automatically merges approved pull requests and transitions cards to Done. It closes the gap between the review step (where PRs get approved) and the final Done state — previously, approved PRs sat unmerged until a human acted.

This runner is purely mechanical: it does not invoke Claude. It checks PR approval status via the GitHub CLI, merges using the configured strategy, and optionally opens a promotion PR to a release branch.

## Usage

### Running Standalone

```bash
bash runners/merge.sh
```

### Adding to the Polling Loop

Add `merge` to `RUNNERS_ENABLED` in `.env`:

```bash
RUNNERS_ENABLED=refine,code,review,merge
```

### Lane Flow

```
QA --> [checks PR approved] --> gh pr merge --> Done
```

Cards in the source lane (`RUNNER_MERGE_FROM`) are checked for an approved PR. If approved, the PR is merged and the card transitions to `RUNNER_MERGE_TO`.

### Config Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RUNNER_MERGE_FROM` | (empty) | Status ID of the lane to read cards from |
| `RUNNER_MERGE_TO` | (empty) | Status ID to transition cards to after merge. If empty, card stays in place |
| `MAX_CARDS_MERGE` | `10` | Maximum cards to process per polling cycle |
| `MERGE_STRATEGY` | `merge` | How to merge PRs: `merge`, `squash`, or `rebase` |
| `GIT_RELEASE_BRANCH` | (empty) | If set, opens a promotion PR from `GIT_BASE_BRANCH` to this branch after each merge |

## How It Works

For each card in the source lane, the runner:

1. **Extracts PR URL** from card comments using the same pattern as the review and bounce runners
2. **Skips** cards with no PR URL (logged as info, not an error)
3. **Checks approval status** via `gh pr view --json reviewDecision`. Falls back to checking the latest individual review if the top-level field is empty
4. **Skips** cards whose PR is not approved
5. **Merges** the PR using `gh pr merge` with the configured `MERGE_STRATEGY` (`--merge`, `--squash`, or `--rebase`)
6. **On success**: adds a board comment with the merge timestamp, PR URL, and merge method, then transitions the card
7. **On failure**: adds an error comment to the card and does not transition

### Dependency Chain Retargeting


1. Retrieves the merged PR's head branch name
2. Searches for open PRs targeting that branch
3. Retargets each child PR to `GIT_BASE_BRANCH` via `gh pr edit --base`
4. Posts a board comment on the child card noting the retarget
5. Logs a `dep_chain_retargeted` event

Retarget failures are non-fatal — they are logged as warnings but do not prevent the parent card from completing.

### Promotion PRs

When `GIT_RELEASE_BRANCH` is set and differs from `GIT_BASE_BRANCH`, the runner checks for an existing open PR from `GIT_BASE_BRANCH` to `GIT_RELEASE_BRANCH` after each successful feature merge. If none exists, it creates one automatically. This supports workflows where merged features accumulate on a development branch before being promoted to a release branch.

## Examples

### Typical pipeline (refine through merge)

```
To Do --> refine --> Refined --> Agent --> code --> QA --> review --> merge --> Done
```

### Squash merges with a release branch

Set these in `.env`:

```bash
MERGE_STRATEGY=squash
GIT_RELEASE_BRANCH=release
GIT_BASE_BRANCH=dev
```

After each feature PR is squash-merged into `dev`, the runner opens (or reuses) a promotion PR from `dev` to `release`.

### Merge-only (no card transition)

Leave `RUNNER_MERGE_TO` empty to merge PRs without moving cards:

```bash
RUNNER_MERGE_FROM=10036
RUNNER_MERGE_TO=
```

The PR is merged and a comment is added, but the card stays in its current lane.
