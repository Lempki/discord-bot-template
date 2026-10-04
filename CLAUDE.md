# discord-bot-template

A discord.py bot template. Bots such as discord-bot-alijohtaja and discord-bot-morshu are created from it.
The shared conventions live in [dev-standards](https://github.com/Lempki/dev-standards), and its README is the rulebook for code, prose, commits, and engineering guidelines.
Read it before changing code. When the repositories are cloned side by side, the local copy is `../dev-standards/README.md`.

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
* `setup.bat` and `setup.sh` only install uv and then run `scripts/bootstrap.py`, which does every other step. Keep it on the standard library, because it runs before the dependencies exist. It is identical in api-template and discord-bot-template, so change it in both.
* `run.bat` and `run.sh` run `scripts/run.py`, which reuses the helpers in `scripts/bootstrap.py`. The same rules apply to it.
* Change a core file here first. Derived bots then pick it up with `dev-standards template-check --apply`.
* Bot-specific behavior belongs in files outside the manifest, such as `localization.py`, `compose.stack.yml`, and the bot's own cogs.
* `config.py` is generic. A cog reads a api-* service with `bot.config.service("<name>")`, which maps to `API_<NAME>_URL` and `API_<NAME>_SECRET`.

## Messages and languages

* Never hard-code user-facing text in a cog. Add a field to `CoreStrings` in `utils/strings.py` for a core cog, or to `Strings` in `localization.py` for the bot's own cog. Give it text in every language, and send it with `respond()`.
* Pick the language with `self.bot.strings_for(interaction)`. Pass `private=True` for ephemeral replies such as admin and moderator replies, which stay on even when `LOCALE=silent`. Public replies are muted under `LOCALE=silent`, which is the default.
* A command that defers must end with `finish(interaction)`, so it never keeps showing "is thinking...".
* A reply sent without `respond()`, such as a file follow-up, must be followed by `mark_replied(interaction)`.
* A command's docstring is its Discord description. Keep it under 100 characters, describe every option, and add the Finnish translation of each text to `CORE_COMMAND_TEXT` for a core cog or `BOT_COMMAND_TEXT` for the bot's own cog.
* Voice goes through `self.bot.voice_presence`, which joins, plays, and leaves idle or empty channels.
* `uv run pytest` fails when a language misses a message or a command translation.
