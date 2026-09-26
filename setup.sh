#!/usr/bin/env bash
# Prepares a local development environment with uv.
# Run it from the repository root. It is safe to run again at any time.
set -e

trap 'echo; echo "ERROR: Setup failed (line $LINENO). Press Enter to close..."; read -r _' ERR

echo "=== $(basename "$(pwd)") setup ==="
echo

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv was not found. Install it from https://docs.astral.sh/uv/ and run this script again."
    read -rp "Press Enter to close..."
    exit 1
fi

# uv creates .venv on first run and installs the locked runtime and development dependencies.
echo "Installing dependencies..."
uv sync

if [ ! -f ".env" ]; then
    cp .env.template .env
    echo "Created .env from .env.template."
    echo "  > Edit .env and set your DISCORD_TOKEN before running the bot."
else
    echo ".env already exists, skipping."
fi

echo
echo "Setup complete!"
echo "  Run the bot : uv run python bot.py"
echo "  Run tests   : uv run pytest"
echo
read -rp "Press Enter to close..."
