# discord-bot-template

This is a clean and modular Python Discord bot template built with [discord.py](https://discordpy.readthedocs.io/). This repository is designed to be used as a starting point for custom bot projects. It provides a structured foundation that can be adapted to a wide range of use cases.

## Features

* The template uses a cog-based architecture. Each feature group is implemented as an isolated and reloadable module.
* All configuration is handled through environment variables. No tokens or IDs are hardcoded in the source code.
* FFmpeg is resolved automatically from the system PATH or from a configurable environment variable.
* Per-guild audio queue support is included. This ensures safe operation across multiple servers.
* Local development is supported through a `.env` file using `python-dotenv`.
* Audio, image, and video assets are stored as regular files that Git marks as binary.
* A `Strings` dataclass defines all user-facing messages as named format strings, in English and Finnish. Replies follow each user's Discord language, and `LOCALE` picks the fallback language. The default, `LOCALE=silent`, mutes public replies but still sends private ones such as `/help` and admin replies.
* Moderation builds on Discord's own AutoMod. `/admin automod` manages keyword and preset rules, and blocked messages can count as warnings.
* The `/help` command lists the loaded commands that the user may run, grouped by cog, in an ephemeral embed. The output reflects whichever cogs are active at runtime with no additional configuration.
* Dependencies are managed with [uv](https://docs.astral.sh/uv/) and pinned in `uv.lock`, so every machine and container installs the same versions.
* Setup scripts for Windows and Unix are included. Running `setup.bat` or `setup.sh` installs the dependencies and creates the initial `.env` file in a single step.
* Tests, linting, and formatting run in CI on every push through the shared [dev-standards](https://github.com/Lempki/dev-standards) workflow.

## Prerequisites

* You must have Python 3.12 installed on your system.
* You must install [uv](https://docs.astral.sh/uv/). On Windows, run `winget install --id astral-sh.uv`. On macOS or Linux, follow the uv installation guide.
* You must install [FFmpeg](https://ffmpeg.org/) and ensure that it is available in your system PATH. You may alternatively define a custom path using the `FFMPEG_PATH` environment variable.

  * On Windows, install FFmpeg with the following command:

    ```
    winget install ffmpeg
    ```

  * On macOS, install FFmpeg with the following command:

    ```
    brew install ffmpeg
    ```

  * On Debian or Ubuntu, install FFmpeg with the following command:

    ```
    sudo apt install ffmpeg
    ```

## Privileged intents

The bot requires one privileged intent. Enable it in your application's **Bot** page in the [Discord Developer Portal](https://discord.com/developers/applications) under **Privileged Gateway Intents** before starting the bot.

| Intent | Portal label | Required for |
|---|---|---|
| `members` | Server Members Intent | `on_member_join` events, auto-role assignment, and reliable member object caching. |

The **Presence Intent** and the **Message Content Intent** are not used and should stay disabled.
AutoMod reads messages on Discord's side, so the bot never needs message content.
The bot also uses the Auto Moderation Execution intent, which is not privileged and needs no portal setting.

## Bot permissions

Use the **OAuth2 → URL Generator** in the Developer Portal to build the invite URL. Select both `bot` and `applications.commands` as the OAuth2 scopes, then select the required permissions from the list that appears below the scope selector.

The **Requires OAuth2 Code Grant** toggle in the Bot page is not applicable to standard bot invites and should remain disabled.

| Permission | Required for |
|---|---|
| View Channels | Reading channel state. |
| Send Messages | Posting the welcome message, media track updates, and AutoMod reports. |
| Connect | Joining voice channels. |
| Speak | Playing audio in voice channels. |
| Manage Roles | Auto-role assignment on member join. |
| Kick Members | `/kick` and the `kick` warning action. |
| Ban Members | `/ban` and the `ban` warning action. |
| Moderate Members | The `timeout` warning action. |
| Manage Server | Managing AutoMod rules and receiving AutoMod executions. |

None of the core cogs send files. Add **Attach Files** if one of your own cogs does.

## Moderation and AutoMod

Discord's own AutoMod does the filtering, so blocked messages never reach the channel.
The bot manages its rules through the API and never reads message content.

* `/admin automod add` and `/admin automod remove` edit the bot's keyword rule. Keywords are separated by commas, and `*` works as a wildcard.
* `/admin automod list` shows the keywords, up to Discord's limit of 1000.
* `/admin automod preset` turns Discord's word lists for profanity, sexual content, and slurs on or off.
* `/admin automod alert` sets the channel where AutoMod posts alerts and the bot posts warning reports.
* `/admin automod escalation` decides whether each blocked message also adds a warning. A member gets at most one AutoMod warning in 10 seconds.
* `/admin warnaction` and `/admin warnthreshold` decide what happens at the warning limit: a kick, a ban, or a timeout. `/admin warntimeout` sets the timeout length.

The bot only changes rules it created itself.
Rules made in **Server Settings > AutoMod** stay untouched, but their blocked messages also count as warnings when escalation is on.
An admin can also add a timeout or an allow list to the bot's rules there, and the bot keeps them.

Two features need no bot code.
Discord's audit log already records every kick, ban, and timeout with the reason the bot passes.
**Server Settings > Integrations** lets admins choose which roles may use each command.

## Setup

The setup script prepares the project in a single run, and it is safe to run again at any time.

On Windows, double-click `setup.bat` or run it from a terminal:

```
setup.bat
```

On macOS or Linux, run the following commands:

```
chmod +x setup.sh
./setup.sh
```

The script asks before it installs or starts anything, and it does the following:

1. It installs [uv](https://docs.astral.sh/uv/) when uv is missing. uv also provides Python 3.12 when the machine lacks it.
2. It offers to install Docker, and the tools that the Docker image includes for running outside Docker, such as FFmpeg. It uses winget on Windows, Homebrew on macOS, and the system package manager on Linux. On Windows it also turns on WSL, which Docker Desktop needs, and says when Windows needs a restart or virtualization is turned off in the firmware.
3. It runs `uv sync`, which installs the locked dependencies into `.venv`.
4. It copies `.env.template` to `.env` on the first run and asks for the bot token, which it reads without showing it.
5. It prepares `compose.stack.yml`. It fills each API secret that the stack needs and reuses the service's own `API_SECRET` when that service is already set up. When an api-* repository that the stack builds is missing, it looks for a downloaded release of it, also inside the extra folder that Windows' Extract All creates, and moves it into place. Otherwise it clones the repository. It then starts Docker Desktop when it is not running, and offers to start the bot and its services in Docker.

A step that fails says what went wrong, why it matters, and what to do next, and the summary at the end lists it again.
The steps live in `scripts/bootstrap.py`, which needs only the Python standard library.

If you prefer to perform the setup manually, follow these steps:

```bash
git clone https://github.com/Lempki/discord-bot-template.git my-bot
cd my-bot
uv sync
cp .env.template .env
# Edit .env and set DISCORD_TOKEN and other values as needed.
uv run python bot.py
```

### Running

After setup has run once, the run script starts the bot.
Double-click `run.bat` on Windows, or run `./run.sh` on macOS and Linux.
It builds and starts the bot and the api-* services in `compose.stack.yml` in Docker in the background.
It then waits until every service is ready and shows their status.
The containers then start again whenever Docker starts.

The script also takes an action, such as `run.bat stop` on Windows or `./run.sh stop` elsewhere:

| Action | What it does |
|---|---|
| `start` | Builds and starts everything in Docker and waits until it is ready. It is the default. |
| `stop` | Stops the containers. They stay stopped until the next start. |
| `status` | Shows whether each container runs and is healthy. |
| `logs` | Follows the logs. Press Ctrl+C to stop following. |
| `update` | Pulls the latest code, rebuilds on fresh base images, and restarts. |
| `local` | Runs the project in the terminal without Docker. Press Ctrl+C to stop it. |

When a service crashes right after it starts, the script shows the end of its log and stops it, so it does not restart over and over.
The `update` action needs a Git clone. In a downloaded release, it explains how to replace the files by hand instead.

The `update` action also pulls the api-* repositories that the stack builds.
The `local` action runs only the bot, which reaches its services at the URLs in `.env`.

### Development

Run the tests with `uv run pytest`.
Run every lint and format check with `uvx pre-commit run --all-files`, or install the hooks once with `uvx pre-commit install` so they run on each commit.
The coding, prose, and commit conventions are documented in [dev-standards](https://github.com/Lempki/dev-standards).

### Docker

Alternatively, you can run the bot as a Docker container.

1. Copy `.env.template` to `.env` and set `DISCORD_TOKEN`.
2. Build and start the container:

   ```
   docker compose up -d --build
   ```

The container restarts automatically unless you stop it.
The database lives on the `bot-data` volume, so settings and warnings survive rebuilds and `docker compose down`.
Only `docker compose down -v` deletes it.

To run the bot together with the api-* services it uses, clone those repositories next to this one and use the stack file instead:

```
docker compose -f compose.stack.yml up -d --build
```

The stack builds each service from its sibling folder and connects them on a private network.
It passes `API_MEDIA_SECRET` from this repository's `.env` to the media service, so the two always agree.

## Configuration

All configuration is read from environment variables or from a `.env` file located in the project root directory.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | None | The Discord bot token used to authenticate with the API. |
| `COGS_TO_LOAD` | No | `help` | A comma-separated list of cog module names to load at startup. Set it to `help,template,voice,media,admin,moderation,events` for the full feature set. |
| `LOCALE` | No | `silent` | The fallback language for users whose Discord language the bot does not speak. Built-in values are `en` and `fi`. `silent` mutes public replies. Private replies, such as `/help`, admin and moderator replies, and error messages, are still sent because only the person who ran the command sees them. |
| `DATABASE_PATH` | No | `data/bot.db` | The SQLite file for per-guild settings and moderation data. The directory is created if needed. The Docker image uses `/app/data/bot.db`. |
| `FFMPEG_PATH` | No | `ffmpeg` | The FFmpeg executable. Leave it unset to use FFmpeg from the system PATH. |
| `DEV_GUILD_ID` | No | None | A server ID for development. Commands sync to that server instantly instead of globally. |
| `API_<NAME>_URL` | No | None | The base URL of a api-* service, for example `API_MEDIA_URL`. |
| `API_<NAME>_SECRET` | No | None | The bearer token of that service. It must match `API_SECRET` in the service's own configuration. |

A cog that needs a service asks for it by name. If the URL or the secret is missing, the bot stops at startup with an error that names both variables.
The `media` cog needs `API_MEDIA_URL` and `API_MEDIA_SECRET`.

Commands are synced to Discord once each time the bot starts.
With `DEV_GUILD_ID` set, they appear in that server immediately.
Commands synced globally earlier stay visible there as well, so a development server may show each command twice until the global ones are removed.

## Project structure

```
discord-bot-template/
├── bot.py                  # Entry point.
├── config.py               # Reads settings and api-* service URLs from the environment.
├── localization.py         # This bot's own messages and translations, layered on the core ones.
├── cogs/
│   ├── help.py             # /help command. Lists the loaded commands the user may run, grouped by cog.
│   ├── template.py         # Template cog. Use this as a starting point for new features.
│   ├── voice.py            # /join, /leave, and /skip. The bot leaves on its own when alone or idle.
│   ├── media.py            # Per-server audio queue with YouTube, SoundCloud, and Spotify support.
│   ├── admin.py            # /admin command group, including /admin automod.
│   ├── moderation.py       # /warn, /warnings, /clearwarning, /clearwarnings, /kick, /ban, and AutoMod escalation.
│   └── events.py           # on_member_join: auto-role assignment and welcome message.
├── utils/
│   ├── audio.py            # MediaAPIClient, URL helpers, and audio sources for files, bytes, and streams.
│   ├── automod.py          # Creates and edits the AutoMod rules that the bot owns.
│   ├── checks.py           # Command checks such as in_bot_channel(), and guild_of().
│   ├── database.py         # Versioned SQLite schema, per-guild settings, and warnings.
│   ├── i18n.py             # Picks each user's language and translates command descriptions.
│   ├── moderation.py       # issue_warning(), shared by /warn and AutoMod escalation.
│   ├── replies.py          # respond() and finish(), which never leave a command "thinking".
│   ├── strings.py          # Every core message and command translation, in English and Finnish.
│   └── voice.py            # Joins, plays in, and leaves voice channels for every cog.
├── assets/
│   ├── audio/              # Audio files.
│   ├── images/             # Image files.
│   └── videos/             # Video files.
├── tests/                  # Pytest suite. Runs in CI on every push.
├── .env.template           # Template for environment variables.
├── .template-manifest.toml # Core files that derived bots keep identical to this template.
├── pyproject.toml          # Project metadata and dependencies.
├── uv.lock                 # Locked dependency versions.
├── ruff.toml               # Lint and format settings on top of the shared baseline.
├── setup.bat               # Windows setup script.
├── setup.sh                # macOS and Linux setup script.
├── scripts/bootstrap.py    # The steps that both setup scripts run.
├── scripts/run.py          # The actions that both run scripts take.
├── run.bat                 # Windows run script.
├── run.sh                  # macOS and Linux run script.
├── Dockerfile
├── docker-compose.yml      # Runs the bot alone, with its database on a volume.
├── compose.stack.yml       # Runs the bot together with the api-* services it uses.
└── .dockerignore
```

## Adding a new cog

1. Copy `cogs/template.py` to a new file such as `cogs/my_feature.py`.
2. Rename the class and implement your commands or event listeners.
3. Add the module name to the `COGS_TO_LOAD` variable in your `.env` file.

## Localization

Replies follow the Discord language of the user who ran the command.
A user whose language the bot does not speak gets the `LOCALE` language, and English after that.
With the default `LOCALE=silent`, public replies stay muted for everyone, so set `LOCALE` to turn them on.
Messages without an interaction, such as the join welcome, use the server's preferred language.

Command descriptions, option descriptions, and choice names are localized natively, so each user's Discord client shows them in their own language.
Command and option names always stay English, so everyone types the same commands.

The core cogs' messages and command translations live in `utils/strings.py`, in English and Finnish.
A bot adds its own messages in `localization.py`, and it may override any core text to give itself a personality.
To add a language, add its Discord locale code, such as `de` or `sv-SE`, to `BOT_TEXT` and `BOT_COMMAND_TEXT` in `localization.py`.
The core texts exist only in English and Finnish, so a new language also needs every core message in `BOT_TEXT` and every core command text in `BOT_COMMAND_TEXT`.

The tests list every message or command text a language is missing, and they fail on command texts longer than Discord's 100-character limit.

## Related services

The following services work alongside bots built from this template and handle functionality that is managed centrally rather than bundled in each bot repository.

| Service | Description |
|---|---|
| [api-media](https://github.com/Lempki/api-media) | Resolves YouTube, SoundCloud, and Spotify track metadata and stream URLs. Supports Spotify tracks, albums, and playlists. |
| [api-scraper](https://github.com/Lempki/api-scraper) | Scrapes structured data from external websites using configurable CSS or XPath selectors. |
| [api-scheduler](https://github.com/Lempki/api-scheduler) | Schedules persistent reminders that survive bot restarts and are delivered via Discord webhooks. |
| [api-morshu](https://github.com/Lempki/api-morshu) | Generates Morshu TTS audio and video from text. |

## Forking this template

Use the GitHub template button to create a new repository based on this project.

The template includes generic English-language cogs that can be modified or replaced. A typical customization workflow includes the following steps:

* Add new bot-specific cogs in the `cogs/` directory.
* Connect a new api-* service by setting `API_<NAME>_URL` and `API_<NAME>_SECRET`, then read it in a cog with `bot.config.service("<name>")`. No change to `config.py` is needed.
* Add the bot's own messages to `Strings` and `BOT_TEXT` in `localization.py`, and set the fallback `LOCALE` in your `.env` file.
* Add audio files to `assets/audio/`, images to `assets/images/`, and videos to `assets/videos/`. Keep each file under 1 MB, because a pre-commit hook rejects larger ones.
* Send images and videos to Discord as `discord.File` attachments. `audio.py` and `play_file()` are audio-only and are not used for other asset types.
* Replace or remove `cogs/template.py` once it is no longer needed.

A forked repository does not maintain a git link to this template.
Instead, `.template-manifest.toml` lists the core files that every bot keeps identical to the template.
With both repositories cloned side by side, run this from the bot's directory to see which core files have drifted:

```bash
uvx --from git+https://github.com/Lempki/dev-standards@v0.2.1 dev-standards template-check --template ../discord-bot-template --diff
```

Add `--apply` to copy the template's version over every drifted file, then review the result with `git diff` before committing.
Keep bot-specific changes in files outside the manifest, such as `localization.py`, `compose.stack.yml`, and the bot's own cogs.

## License

This project is licensed under the [MIT License](LICENSE).
You may use, change, and share it, as long as every copy keeps the copyright notice and the license text.
