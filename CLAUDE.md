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
* `utils/strings.py` holds the core cogs' messages in every language, and `localization.py` adds this bot's own.
* `utils/moderation.py` holds `issue_warning()`, which `/warn` and the AutoMod escalation share.
* `utils/automod.py` manages the AutoMod rules the bot owns, which it finds by `creator_id`. Discord does the filtering, so the bot needs no Message Content intent.

## Template rules

* `.template-manifest.toml` lists the core files that every derived bot keeps identical to this template.
* Change a core file here first. Derived bots then pick it up with `dev-standards template-check --apply`.
* Bot-specific behavior belongs in files outside the manifest, such as `localization.py`, `compose.stack.yml`, and the bot's own cogs.
* `config.py` is generic. A cog reads a discord-api-* service with `bot.config.service("<name>")`, which maps to `DISCORD_API_<NAME>_URL` and `DISCORD_API_<NAME>_SECRET`.

## Messages and languages

* Never hard-code user-facing text in a cog. Add a field to `Strings`, give it text in every language, and send it with `respond()`.
* Pick the language with `self.bot.strings_for(interaction)`. Pass `private=True` for ephemeral admin and moderator replies, which stay on even when `LOCALE=silent`.
* A command that defers must end with `finish(interaction)`, so it never keeps showing "is thinking...".
* A reply sent without `respond()`, such as a file follow-up, must be followed by `mark_replied(interaction)`.
* A command's docstring is its Discord description. Keep it under 100 characters, describe every option, and add the Finnish translation of each text to the command text table.
* Voice goes through `self.bot.voice_presence`, which joins, plays, and leaves idle or empty channels.
* `uv run pytest` fails when a language misses a message or a command translation.
