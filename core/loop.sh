#!/usr/bin/env bash
# Sorta.Fit — Main polling loop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SORTA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_FILE="$SORTA_ROOT/.automation.lock"

# Source config and utils
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

# Load adapter
ADAPTER_FILE="$SORTA_ROOT/adapters/${BOARD_ADAPTER}.sh"
if [[ ! -f "$ADAPTER_FILE" ]]; then
  log_error "Adapter not found: $ADAPTER_FILE"
  exit 1
fi
source "$ADAPTER_FILE"

# Cleanup on exit
cleanup() {
  lock_release "$LOCK_FILE"
  log_info "Loop stopped."
}
trap cleanup EXIT INT TERM

# Parse enabled runners
IFS=',' read -ra RUNNER_LIST <<< "$RUNNERS_ENABLED"

echo "================================================"
echo "  Sorta.Fit"
echo "================================================"
echo "  Adapter:  $BOARD_ADAPTER"
echo "  Project:  $BOARD_PROJECT_KEY"
echo "  Runners:  $RUNNERS_ENABLED"
echo "  Interval: $((POLL_INTERVAL / 60)) minutes"
echo "  Base branch: $GIT_BASE_BRANCH"
echo "================================================"
echo ""

# Preflight
preflight_check || exit 1

run_cycle() {
  if is_rate_limited; then
    return
  fi

  if ! lock_acquire "$LOCK_FILE"; then
    return
  fi

  log_info "Cycle starting at $(date)"

  local step=1
  local total=${#RUNNER_LIST[@]}

  for runner in "${RUNNER_LIST[@]}"; do
    runner=$(echo "$runner" | xargs) # trim whitespace
    local runner_file="$SORTA_ROOT/runners/${runner}.sh"

    if [[ ! -f "$runner_file" ]]; then
      log_warn "[$step/$total] Runner not found: $runner (skipping)"
    else
      log_step "[$step/$total] Running: $runner"
      bash "$runner_file" 2>&1 || log_warn "Runner '$runner' encountered an error"
    fi

    step=$((step + 1))
  done

  log_info "Cycle complete at $(date). Next run in $((POLL_INTERVAL / 60)) minutes."
  lock_release "$LOCK_FILE"
}

# Run immediately
run_cycle

# Then loop
while true; do
  sleep "$POLL_INTERVAL"
  run_cycle
done
