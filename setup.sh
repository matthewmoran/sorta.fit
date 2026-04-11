#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo "  Sorta.Fit Setup"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
  PYTHON_CMD="python"
fi

if ! command -v "$PYTHON_CMD" &>/dev/null; then
  echo "ERROR: Python 3 is not installed."
  echo "Download from https://python.org"
  exit 1
fi

echo "Starting setup wizard..."
echo "Opening http://localhost:3456 in your browser..."
echo ""
echo "Press Ctrl+C to stop."
echo ""

exec "$PYTHON_CMD" "$SCRIPT_DIR/setup_wizard.py"
