#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo "  Sorta.Fit Setup"
echo "================================================"
echo ""

# Check Node.js
if ! command -v node &>/dev/null; then
  echo "ERROR: Node.js is not installed."
  echo "Download from https://nodejs.org"
  exit 1
fi

# Check Git
if ! command -v git &>/dev/null; then
  echo "ERROR: Git is not installed."
  echo "Download from https://git-scm.com/downloads"
  exit 1
fi

echo "Dependencies found."
echo ""

# Install npm dependencies if needed
if [[ -f "package.json" ]] && [[ ! -d "node_modules" ]]; then
  echo "Installing dependencies..."
  npm install
  echo ""
fi

# Launch setup server
echo "Starting setup wizard..."
echo "Opening http://localhost:3456 in your browser..."
echo ""
echo "Press Ctrl+C to stop."
echo ""

node setup/server.js
