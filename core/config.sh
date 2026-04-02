#!/usr/bin/env bash
# Sorta.Fit — Configuration loader
# Sources .env and validates required variables

set -euo pipefail

SORTA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load .env
if [[ -f "$SORTA_ROOT/.env" ]]; then
  set -a
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    value="${value%\"}"
    value="${value#\"}"
    export "$key=$value"
  done < "$SORTA_ROOT/.env"
  set +a
fi

# Required vars
: "${BOARD_ADAPTER:?BOARD_ADAPTER not set (jira, linear, github-issues)}"

# Validate adapter name (prevent path traversal in sourced files)
case "$BOARD_ADAPTER" in
  jira|linear|github-issues) ;;
  *) echo "ERROR: Unknown adapter: $BOARD_ADAPTER"; exit 1 ;;
esac

# Validate board domain (prevent injection into URLs)
if [[ ! "$BOARD_DOMAIN" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$ ]]; then
  echo "ERROR: Invalid BOARD_DOMAIN: $BOARD_DOMAIN"
  exit 1
fi
: "${BOARD_DOMAIN:?BOARD_DOMAIN not set}"
: "${BOARD_API_TOKEN:?BOARD_API_TOKEN not set}"
: "${BOARD_PROJECT_KEY:?BOARD_PROJECT_KEY not set}"

# Optional with defaults
export GIT_BASE_BRANCH="${GIT_BASE_BRANCH:-main}"
export POLL_INTERVAL="${POLL_INTERVAL:-3600}"
export MAX_CARDS_REFINE="${MAX_CARDS_REFINE:-5}"
export MAX_CARDS_ARCHITECT="${MAX_CARDS_ARCHITECT:-5}"
export MAX_CARDS_CODE="${MAX_CARDS_CODE:-2}"
export MAX_CARDS_REVIEW="${MAX_CARDS_REVIEW:-10}"
export MAX_CARDS_TRIAGE="${MAX_CARDS_TRIAGE:-5}"
export MAX_CARDS_BOUNCE="${MAX_CARDS_BOUNCE:-10}"
export MAX_CARDS_MERGE="${MAX_CARDS_MERGE:-10}"
export RUNNERS_ENABLED="${RUNNERS_ENABLED:-refine,code}"

# Adapter-specific
export BOARD_EMAIL="${BOARD_EMAIL:-}"

# Runner lane routing — where each runner reads from and transitions to
# FROM = status ID on the board (used in JQL queries)
# TO = status ID to transition to (looks up TRANSITION_TO_<id> in adapter config, empty = don't move)
export RUNNER_REFINE_FROM="${RUNNER_REFINE_FROM:-}"
export RUNNER_REFINE_TO="${RUNNER_REFINE_TO:-}"
export RUNNER_REFINE_FILTER_TYPE="${RUNNER_REFINE_FILTER_TYPE:-}"

export RUNNER_ARCHITECT_FROM="${RUNNER_ARCHITECT_FROM:-}"
export RUNNER_ARCHITECT_TO="${RUNNER_ARCHITECT_TO:-}"

export RUNNER_CODE_FROM="${RUNNER_CODE_FROM:-}"
export RUNNER_CODE_TO="${RUNNER_CODE_TO:-}"

export RUNNER_REVIEW_FROM="${RUNNER_REVIEW_FROM:-}"
export RUNNER_REVIEW_TO="${RUNNER_REVIEW_TO:-}"

export RUNNER_TRIAGE_FROM="${RUNNER_TRIAGE_FROM:-}"
export RUNNER_TRIAGE_TO="${RUNNER_TRIAGE_TO:-}"
export RUNNER_TRIAGE_FILTER_TYPE="${RUNNER_TRIAGE_FILTER_TYPE:-Bug}"

export RUNNER_BOUNCE_FROM="${RUNNER_BOUNCE_FROM:-}"
export RUNNER_BOUNCE_TO="${RUNNER_BOUNCE_TO:-}"
export MAX_BOUNCES="${MAX_BOUNCES:-3}"
export RUNNER_BOUNCE_ESCALATE="${RUNNER_BOUNCE_ESCALATE:-}"

export RUNNER_MERGE_FROM="${RUNNER_MERGE_FROM:-}"
export RUNNER_MERGE_TO="${RUNNER_MERGE_TO:-}"
export MERGE_STRATEGY="${MERGE_STRATEGY:-merge}"
export GIT_RELEASE_BRANCH="${GIT_RELEASE_BRANCH:-}"

# Load adapter config
ADAPTER_CONFIG="$SORTA_ROOT/adapters/${BOARD_ADAPTER}.config.sh"
if [[ -f "$ADAPTER_CONFIG" ]]; then
  source "$ADAPTER_CONFIG"
else
  echo "WARNING: Adapter config not found: $ADAPTER_CONFIG"
  echo "Run the setup wizard or copy from ${ADAPTER_CONFIG}.example"
fi
