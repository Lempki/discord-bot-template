#!/usr/bin/env bash
set -e

trap 'echo; echo "ERROR: Setup failed (line $LINENO). Press Enter to close..."; read -r _' ERR

echo "=== discord-bot-template setup ==="
echo

# Create virtual environment if it doesn't already exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists, skipping creation."
fi

# Upgrade pip
echo "Upgrading pip..."
.venv/bin/python -m pip install --upgrade pip --quiet

# Install requirements
echo "Installing requirements..."
.venv/bin/python -m pip install -r requirements.txt

# Copy .env.example to .env if .env doesn't exist yet
if [ ! -f ".env" ]; then
    cp .env.template .env
    echo "Created .env from .env.example"
    echo "  > Edit .env and set your DISCORD_TOKEN before running the bot."
else
    echo ".env already exists, skipping."
fi

echo
echo "Setup complete!"
echo "  Activate venv : source .venv/bin/activate"
echo "  Run the bot   : .venv/bin/python bot.py"
echo
read -rp "Press Enter to close..."
