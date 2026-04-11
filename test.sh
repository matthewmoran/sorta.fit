#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_CMD="python"
if command -v python3 &>/dev/null && python3 --version &>/dev/null; then
  PYTHON_CMD="python3"
fi

if [[ "${1:-}" == "--unit" ]]; then
  "$PYTHON_CMD" -m pytest "$SCRIPT_DIR/tests/unit/" -v "$@"
elif [[ "${1:-}" == "--integration" ]]; then
  "$PYTHON_CMD" -m pytest "$SCRIPT_DIR/tests/integration/" -v "$@"
else
  "$PYTHON_CMD" -m pytest "$SCRIPT_DIR/tests/" -v "$@"
fi
