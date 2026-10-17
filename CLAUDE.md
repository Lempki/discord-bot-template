# discord-bot-template

A discord.py bot template, which Discord bots are created from.
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
* `utils/heartbeat.py` refreshes `/tmp/bot-healthy` every 30 seconds while the gateway is connected, which the Dockerfile's health check reads. With `HEARTBEAT_URL` set, it also reports to that service every 5 minutes. The URL works like a password, so it never goes into a log.
* `utils/about.py` reads the name, version, and repository link that `/about` shows from `pyproject.toml`.
* `utils/automod.py` manages the AutoMod rules the bot owns, which it finds by `creator_id`. Discord does the filtering, so the bot needs no Message Content intent.

## Template rules

* `.template-manifest.toml` lists the core files that every derived bot keeps identical to this template.
* `setup.bat` and `setup.sh` only install uv and then run `scripts/bootstrap.py`, which does every other step. Keep it on the standard library, because it runs before the dependencies exist. It is identical in api-template and discord-bot-template, so change it in both.
* `run.bat` and `run.sh` run `scripts/run.py`, which reuses the helpers in `scripts/bootstrap.py`. The same rules apply to it.
* Change a core file here first. Derived bots then pick it up with `dev-standards template-check --template ../discord-bot-template --apply`.
* Bot-specific behavior belongs in files outside the manifest, such as `localization.py`, `compose.stack.yml`, and the bot's own cogs.
* `config.py` is generic. A cog reads an api-* service with `bot.config.service("<name>")`, which maps to `API_<NAME>_URL` and `API_<NAME>_SECRET`.

## Messages and languages

* A reply to a command never names the member who ran it, because Discord shows that above the reply.
  Name a member only in a message that is not a reply, such as the music panel, and never ping for it.
* Never hard-code user-facing text in a cog. Add a field to `CoreStrings` in `utils/strings.py` for a core cog, or to `Strings` in `localization.py` for the bot's own cog. Give it text in every language, and send it with `respond()`.
* Pick the language with `self.bot.strings_for(interaction)`. Pass `private=True` for ephemeral replies such as admin and moderator replies, which stay on even when `LOCALE=silent`. Public replies to commands are muted under `LOCALE=silent`, which is the default. A message that someone turned on, such as the music panel or the welcome, also passes `private=True`, so silence never hides it.
* A command that starts work, such as a download or a generation, gets a per-member `app_commands.checks.cooldown`.
  The bot answers a member who is too fast with the private `cooldown` text.
* A command that defers must end with `finish(interaction)`, so it never keeps showing "is thinking...".
* A reply sent without `respond()`, such as a file follow-up, must be followed by `mark_replied(interaction)`.
* A command's docstring is its Discord description. Keep it under 100 characters, describe every option, and add the Finnish translation of each text to `CORE_COMMAND_TEXT` for a core cog or `BOT_COMMAND_TEXT` for the bot's own cog.
* Voice goes through `self.bot.voice_presence`, which joins, plays, and leaves idle or empty channels.
* `uv run pytest` fails when a language misses a message or a command translation.
* Group a feature's commands under one `app_commands.Group` named after the feature, such as `/music pause` or `/warnings list`, so each name says what it acts on.
  Only a feature's main entry point, such as `/play`, stays a top-level command, and no action gets a second name.
* Give every feature a `guide_<cog>` text in every language, which `/help` shows with the feature's commands.
