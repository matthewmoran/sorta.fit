#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo "  Sorta.Fit Runner"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "ERROR: Python 3 is not installed."
  echo "Download from https://python.org"
  exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
  PYTHON_CMD="python"
fi

echo "Starting runner..."
echo ""

exec "$PYTHON_CMD" "$SCRIPT_DIR/run.py" "$@"
