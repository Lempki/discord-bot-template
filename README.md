# discord-bot-template

A clean and modular Python Discord bot template built with [discord.py](https://discordpy.readthedocs.io/) and the Cog system. This repository is designed to be forked and extended for custom bot projects. It provides a structured foundation that can be adapted to a wide range of use cases.

## Features

- Cog-based architecture. Each feature group is implemented as an isolated and reloadable module.
- Configuration is handled entirely through environment variables. No tokens or IDs are hardcoded in the source code.
- FFmpeg is resolved automatically from the system PATH or from a configurable environment variable.
- Per-guild audio queue support. This ensures safe operation across multiple servers.
- `.env` support for local development using `python-dotenv`.
- Git LFS is configured for managing large audio and image assets.
- A `Strings` dataclass defines all user-facing messages as named format strings. The bot is silent by default and messages are enabled by setting a locale in the environment.
- Setup scripts for Windows and Unix are included. Running `setup.bat` or `setup.sh` handles virtual environment creation, dependency installation, and initial `.env` configuration in a single step.

## Prerequisites

- Python 3.10 or newer.
- [FFmpeg](https://ffmpeg.org/) installed and available in your system PATH. You can also define a custom path using the `FFMPEG_PATH` environment variable.

  ```
  winget install ffmpeg        # Windows
  brew install ffmpeg          # macOS
  sudo apt install ffmpeg      # Debian/Ubuntu
  ```

- [Git LFS](https://git-lfs.com/) if you plan to version control audio or image assets.

## Setup

Run the included setup script to prepare the project in a single step.

**Windows:**
```
setup.bat
```

**macOS / Linux:**
```
chmod +x setup.sh && ./setup.sh
```

The script creates a `.venv` virtual environment if one does not already exist, installs all dependencies, and copies `.env.example` to `.env` on the first run. Edit `.env` and set your `DISCORD_TOKEN` before starting the bot.

If you prefer to set up manually:

```bash
git clone https://github.com/Lempki/discord-bot-template.git my-bot
cd my-bot
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DISCORD_TOKEN and other values as needed
python bot.py
```

## Configuration

All configuration is read from environment variables or from a `.env` file located in the project root directory.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | The Discord bot token. |
| `COMMAND_PREFIX` | No | `!` | The prefix used for bot commands. |
| `FFMPEG_PATH` | No | system PATH | Absolute path to the FFmpeg binary. |
| `COGS_TO_LOAD` | No | `example` | Comma-separated list of cog modules to load. |
| `BOT_CHANNEL_ID` | No | — | Restricts command usage to a specific text channel ID. |
| `AUTO_ROLE_NAME` | No | — | Name of the role assigned when a member joins. |
| `LOCALE` | No | `silent` | Language for bot messages. Built-in values are `en` and `silent`. Add new locales in `localization.py`. |

## Project structure

```
discord-bot-template/
├── bot.py              # Entry point
├── config.py           # Environment variable reader. Extend this file to add new configuration keys.
├── localization.py     # Strings dataclass and locale presets. Define new languages here.
├── cogs/
│   ├── example.py      # Reference cog. Use this as a starting point for new features.
│   ├── voice.py        # Voice-related commands such as join, leave, and skip.
│   └── youtube.py      # YouTube audio queue with playlist support.
├── utils/
│   ├── audio.py        # Audio helpers including YouTubeDLSource and playback utilities.
│   ├── checks.py       # Custom command checks such as in_bot_channel().
│   └── logging.py      # Timestamped console logging helper.
├── assets/
│   └── audio/          # Directory for .ogg and .mp3 files. Managed via Git LFS.
├── .env.example        # Template for environment variables.
├── setup.bat           # Windows setup script.
├── setup.sh            # macOS and Linux setup script.
└── requirements.txt
```

## Adding a new cog

1. Copy `cogs/example.py` to a new file such as `cogs/my_feature.py`.
2. Rename the class and implement your commands or event listeners.
3. Add the module name to the `COGS_TO_LOAD` variable in your `.env` file.

## Localization

All user-facing messages are defined in `localization.py` as a `Strings` dataclass. Every field defaults to an empty string, which means the bot sends no messages unless a locale is configured.

Setting `LOCALE=en` in `.env` activates the built-in English preset. To add a new language, create a `Strings(...)` instance with your translated strings and register it in the `LOCALES` dictionary at the bottom of the file. No changes to cog code are required.

## Forking this template

Use GitHub's "Use this template" button to create a new repository based on this project.

The template includes generic English-language cogs that can be modified or replaced. A typical customization workflow includes the following steps:

- Add new bot-specific cogs in the `cogs/` directory.
- Extend the `Config` class in `config.py` to support additional environment variables.
- Add locale strings to `localization.py` and set `LOCALE` in your `.env` file.
- Add audio files to `assets/audio/`. Git LFS will manage these automatically.
- Replace or remove `cogs/example.py` once it is no longer needed.

A forked repository does not maintain a git link to this template. To pull in future updates selectively, add this repository as a named remote and cherry-pick the commits you want.

```bash
git remote add template https://github.com/Lempki/discord-bot-template.git
git fetch template
git cherry-pick <commit-hash>
```
