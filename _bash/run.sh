#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo "  Sorta.Fit Runner"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v node &>/dev/null; then
  echo "ERROR: Node.js is not installed."
  echo "Download from https://nodejs.org"
  exit 1
fi

if ! command -v git &>/dev/null; then
  echo "ERROR: Git is not installed."
  echo "Download from https://git-scm.com/downloads"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "ERROR: .env not found. Run the setup wizard first:"
  echo "  bash setup.sh"
  exit 1
fi

echo "Starting runner..."
echo ""

exec bash "$SCRIPT_DIR/core/loop.sh"
