#!/usr/bin/env bash
# Runner: Generate release notes from merged PRs
# Usage: bash runners/release-notes.sh <since> [output-file]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SORTA_ROOT/core/config.sh"
source "$SORTA_ROOT/core/utils.sh"

SINCE="${1:-}"
OUTPUT_FILE="${2:-}"

if [[ -z "$SINCE" ]]; then
  echo "Usage: bash recipes/release-notes.sh <since> [output-file]"
  echo "  since: git tag, date (YYYY-MM-DD), or commit SHA"
  exit 1
fi

GH_CMD=$(find_gh)

log_info "Generating release notes since: $SINCE"

# Get commit log
GIT_LOG=$(git -C "$TARGET_REPO" log "$SINCE..HEAD" --pretty=format:"%H|%s" --no-merges 2>/dev/null || true)

if [[ -z "$GIT_LOG" ]]; then
  log_warn "No commits found since $SINCE"
  exit 0
fi

# Build context for Claude
COMMIT_LIST=""
while IFS='|' read -r sha subject; do
  [[ -z "$sha" ]] && continue
  COMMIT_LIST="${COMMIT_LIST}
- ${sha:0:8}: $subject"
done <<< "$GIT_LOG"

PROMPT="Generate user-friendly release notes from these commits. Group into: New Features, Improvements, Bug Fixes, Breaking Changes. Omit empty sections. Write for end users, not developers. Be concise.

## Commits since $SINCE
$COMMIT_LIST

Output the release notes in markdown format."

PROMPT_FILE=$(mktemp)
RESULT_FILE=$(mktemp)
printf '%s' "$PROMPT" > "$PROMPT_FILE"
run_claude "$PROMPT_FILE" "$RESULT_FILE" "" "${RUNNER_RELEASE_NOTES_AGENT:-$CLAUDE_AGENT}"
claude_rc=$?
rm -f "$PROMPT_FILE"
if [[ "$claude_rc" -ne 0 ]]; then
  log_error "Claude failed to generate release notes"
  rm -f "$RESULT_FILE"
  exit 1
fi

NOTES=$(cat "$RESULT_FILE")
rm -f "$RESULT_FILE"

echo "$NOTES"

if [[ -n "$OUTPUT_FILE" ]]; then
  echo "$NOTES" > "$OUTPUT_FILE"
  log_info "Written to $OUTPUT_FILE"
fi
