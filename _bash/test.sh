#!/usr/bin/env bash
# Sorta.Fit — Test runner
# Usage: bash test.sh [--unit|--integration]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATS="$SCRIPT_DIR/tests/libs/bats-core/bin/bats"

if [[ ! -f "$BATS" ]]; then
  echo "ERROR: bats-core not found. Run: git submodule update --init --recursive"
  exit 1
fi

echo "================================================"
echo "  Sorta.Fit — Test Suite"
echo "================================================"

case "${1:-all}" in
  --unit)
    echo "  Running: unit tests"
    echo "================================================"
    "$BATS" "$SCRIPT_DIR/tests/unit/"
    ;;
  --integration)
    echo "  Running: integration tests"
    echo "================================================"
    "$BATS" "$SCRIPT_DIR/tests/integration/"
    ;;
  all|"")
    echo "  Running: all tests"
    echo "================================================"
    "$BATS" "$SCRIPT_DIR/tests/unit/" "$SCRIPT_DIR/tests/integration/"
    ;;
  *)
    echo "Usage: bash test.sh [--unit|--integration]"
    exit 1
    ;;
esac
