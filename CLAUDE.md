# discord-bot-template

A discord.py bot template. Bots such as discord-bot-alijohtaja and discord-bot-morshu are created from it.
The shared conventions live in [discord-dev-standards](https://github.com/Lempki/discord-dev-standards), and its README is the rulebook for code, prose, and commits.

## Commands

* `uv sync` installs the locked dependencies into `.venv`.
* `uv run python bot.py` starts the bot. It reads its settings from `.env`.
* `uv run pytest` runs the tests.
* `uvx pre-commit run --all-files` runs every lint and format hook.

## Layout

* `bot.py` is the entry point. It loads the cogs named in `COGS_TO_LOAD`.
* `cogs/` holds one feature group per module.
* `utils/` holds shared helpers such as the database module and command checks.
* `localization.py` holds every user-facing message.

## Template rules

* `.template-manifest.toml` lists the core files that every derived bot keeps identical to this template.
* Change a core file here first. Derived bots then pick it up with `dev-standards template-check --apply`.
* Bot-specific behavior belongs in files outside the manifest, such as `config.py`, `localization.py`, and the bot's own cogs.
