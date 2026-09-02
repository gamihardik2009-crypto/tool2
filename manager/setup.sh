#!/usr/bin/env bash
# Portable self-setup for the manager tool. Run this once on the machine where
# you will control the VPS. It creates a local .venv and installs dependencies.
# This deliberately does NOT `playwright install` any bundled browser: the tool
# attaches to your real Chrome/Edge via CDP, so no automation browser is needed.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [ ! -d ".venv" ]; then
  echo "Creating local virtualenv (.venv)..."
  "$PY" -m venv .venv
fi

echo "Installing dependencies into .venv..."
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -e .

echo
echo "Setup complete. Run the manager with:"
echo "    ./.venv/bin/python -m telegram_x_manager --help"
echo "    ./.venv/bin/telegram-x-manager tui"
echo "    (or run: ./.venv/bin/telegram-x-manager)"
