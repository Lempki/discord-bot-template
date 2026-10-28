#!/usr/bin/env bash
# Starts the bot's image as far as Discord's login, as CI's smoke test does.
# Usage: .github/smoke-test.sh <image>
# A build passes even when the bot inside the image cannot start, which this catches.
set -euo pipefail
image=$1
container="smoke-test-$$"

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Discord rejects the dummy token below before the bot loads a cog, so every cog is imported first.
docker run --rm "$image" python -c "import importlib, pkgutil, cogs; [importlib.import_module(f'cogs.{module.name}') for module in pkgutil.iter_modules(cogs.__path__)]"
echo "Every cog imported."

status=0
log=$(docker run --name "$container" -e DISCORD_TOKEN=smoke.test.token "$image" 2>&1) || status=$?
echo "$log"
# bot.py logs this line and exits with 1 when Discord turns the token down.
if [ "$status" -eq 1 ] && grep -q "Discord rejected DISCORD_TOKEN" <<<"$log"; then
    echo "The bot started and reached Discord's login."
    exit 0
fi
echo "::error::The bot did not reach Discord's login."
exit 1
