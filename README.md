# discord-bot-template

This is a clean and modular Python Discord bot template built with [discord.py](https://discordpy.readthedocs.io/). This repository is designed to be used as a starting point for custom bot projects. It provides a structured foundation that can be adapted to a wide range of use cases.

## Features

* The template uses a cog-based architecture. Each feature group is implemented as an isolated and reloadable module.
* All configuration is handled through environment variables. No tokens or IDs are hardcoded in the source code.
* FFmpeg is resolved automatically from the system PATH or from a configurable environment variable.
* Per-guild audio queue support is included. This ensures safe operation across multiple servers.
* Local development is supported through a `.env` file using `python-dotenv`.
* Git LFS is configured for managing large audio, image, and video assets.
* A `Strings` dataclass defines all user-facing messages as named format strings. The bot is silent by default and messages are enabled by setting a locale in the environment.
* The `/help` command displays all loaded commands grouped by cog in an ephemeral embed. The output reflects whichever cogs are active at runtime with no additional configuration.
* Setup scripts for Windows and Unix are included. Running `setup.bat` or `setup.sh` handles virtual environment creation, dependency installation, and initial `.env` configuration in a single step.

## Prerequisites

* You must have Python version 3.10 or newer installed on your system.
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

* You must install [Git LFS](https://git-lfs.com/) if you plan to version control audio or image assets.

## Privileged intents

The bot requires one privileged intent. Enable it in your application's **Bot** page in the [Discord Developer Portal](https://discord.com/developers/applications) under **Privileged Gateway Intents** before starting the bot.

| Intent | Portal label | Required for |
|---|---|---|
| `members` | Server Members Intent | `on_member_join` events and reliable member object caching. |

For now, the **Presence Intent** and **Message Content Intent** are not used by this template and do not need to be enabled.

## Bot permissions

Use the **OAuth2 → URL Generator** in the Developer Portal to build the invite URL. Select both `bot` and `applications.commands` as the OAuth2 scopes, then select the required permissions from the list that appears below the scope selector.

The **Requires OAuth2 Code Grant** toggle in the Bot page is not applicable to standard bot invites and should remain disabled.

| Permission | Required for |
|---|---|
| View Channels | Reading messages and channel state. |
| Send Messages | Responding to commands. |
| Read Message History | Reply functionality. |
| Connect | Joining voice channels. |
| Speak | Playing audio in voice channels. |

## Setup

You can use the included setup script to prepare the project in a single step.

On Windows, run the following command:

```
setup.bat
```

On macOS or Linux, run the following commands:

```
chmod +x setup.sh
./setup.sh
```

The script creates a `.venv` virtual environment if one does not already exist. It installs all dependencies and copies `.env.template` to `.env` on the first run. You must edit `.env` and set your `DISCORD_TOKEN` before starting the bot.

If you prefer to perform the setup manually, follow these steps:

```bash
git clone https://github.com/Lempki/discord-bot-template.git my-bot
cd my-bot
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.template .env
# Edit .env and set DISCORD_TOKEN and other values as needed.
python bot.py
```

### Docker

Alternatively, you can run the bot as a Docker container.

1. Copy `.env.template` to `.env` and set `DISCORD_TOKEN`.
2. Build and start the container:

   ```
   docker-compose up -d
   ```

The container automatically restarts unless explicitly stopped.

## Configuration

All configuration is read from environment variables or from a `.env` file located in the project root directory.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | The Discord bot token used to authenticate with the API. |
| `FFMPEG_PATH` | No | system PATH | The absolute path to the FFmpeg binary. Leave this empty to use the system PATH. |
| `COGS_TO_LOAD` | No | `template` | A comma-separated list of cog module names to load at startup. Set to `help,template,voice,media` for the full feature set. |
| `LOCALE` | No | `silent` | The language used for bot messages. Built-in values are `en` and `silent`. When set to `silent`, the bot sends no messages. New locales can be added in `localization.py`. |
| `DISCORD_API_MEDIA_URL` | No* | — | Base URL of the [discord-api-media](https://github.com/Lempki/discord-api-media) service. Required when the `media` cog is loaded. |
| `DISCORD_API_MEDIA_SECRET` | No* | — | Bearer token for discord-api-media. Must match `DISCORD_API_SECRET` in that service. Required when the `media` cog is loaded. |

\* Required if the `media` cog is included in `COGS_TO_LOAD`.

## Project structure

```
discord-bot-template/
├── bot.py              # Entry point.
├── config.py           # Environment variable reader. Extend this file to add new configuration keys.
├── localization.py     # Strings dataclass and locale presets. Define new languages here.
├── cogs/
│   ├── help.py         # /help command. Lists all loaded commands grouped by cog.
│   ├── template.py     # Template cog. Use this as a starting point for new features.
│   ├── voice.py        # Voice-related commands such as join, leave, and skip.
│   └── media.py        # Audio queue with YouTube and Spotify support.
├── utils/
│   ├── audio.py        # MediaAPIClient, URL helpers, and local file playback utility.
│   ├── checks.py       # Custom command checks such as in_bot_channel().
│   └── logging.py      # Timestamped console logging helper.
├── assets/
│   ├── audio/          # Local Git LFS-managed audio files.
│   ├── images/         # Local Git LFS-managed image files.
│   └── videos/         # Local Git LFS-managed video files.
├── .env.template       # Template for environment variables.
├── setup.bat           # Windows setup script.
├── setup.sh            # macOS and Linux setup script.
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── requirements.txt
```

## Adding a new cog

1. Copy `cogs/template.py` to a new file such as `cogs/my_feature.py`.
2. Rename the class and implement your commands or event listeners.
3. Add the module name to the `COGS_TO_LOAD` variable in your `.env` file.

## Localization

All user-facing messages are defined in `localization.py` as a `Strings` dataclass. Every field defaults to an empty string, which means the bot sends no messages unless a locale is configured.

Setting `LOCALE=en` in `.env` activates the built-in English preset. To add a new language, create a `Strings(...)` instance with your translated strings and register it in the `LOCALES` dictionary at the bottom of the file. No changes to cog code are required.

## Related services

The following services work alongside bots built from this template and handle functionality that is managed centrally rather than bundled in each bot repository.

| Service | Description |
|---|---|
| [discord-api-media](https://github.com/Lempki/discord-api-media) | Resolves YouTube, SoundCloud, and Spotify track metadata and stream URLs. Supports Spotify tracks, albums, and playlists. |
| [discord-api-scraper](https://github.com/Lempki/discord-api-scraper) | Scrapes structured data from external websites using configurable CSS or XPath selectors. |
| [discord-api-scheduler](https://github.com/Lempki/discord-api-scheduler) | Schedules persistent reminders that survive bot restarts and are delivered via Discord webhooks. |
| [discord-api-morshu](https://github.com/Lempki/discord-api-morshu) | Generates Morshu TTS audio and video from text. |

## Forking this template

Use the GitHub template button to create a new repository based on this project.

The template includes generic English-language cogs that can be modified or replaced. A typical customization workflow includes the following steps:

* Add new bot-specific cogs in the `cogs/` directory.
* Extend the `Config` class in `config.py` to support additional environment variables.
* Add locale strings to `localization.py` and set `LOCALE` in your `.env` file.
* Add audio files to `assets/audio/`, images to `assets/images/`, and videos to `assets/videos/`. Git LFS will manage these automatically based on file extension.
* Send images and videos to Discord as `discord.File` attachments. `audio.py` and `play_file()` are audio-only and are not used for other asset types.
* Replace or remove `cogs/template.py` once it is no longer needed.

A forked repository does not maintain a git link to this template. To pull in future updates selectively, add this repository as a named remote and cherry-pick the commits you want.

```bash
git remote add template https://github.com/Lempki/discord-bot-template.git
git fetch template
git cherry-pick <commit-hash>
```
