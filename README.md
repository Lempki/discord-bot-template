# discord-bot-template

A clean, modular Python Discord bot template using [discord.py](https://discordpy.readthedocs.io/) and the Cog system. Built to be forked and customized for specific bot projects.

## Features

- Cog-based architecture — each feature group is an isolated, reloadable module
- All configuration via environment variables (no hardcoded tokens or IDs)
- FFmpeg resolved from system PATH or a configurable env var
- Per-guild audio queue (multi-server safe)
- `.env` support for local development via `python-dotenv`
- Git LFS configured for audio and image assets

## Prerequisites

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) on your system PATH (or set `FFMPEG_PATH` in `.env`)
  ```
  winget install ffmpeg        # Windows
  brew install ffmpeg           # macOS
  sudo apt install ffmpeg       # Debian/Ubuntu
  ```
- [Git LFS](https://git-lfs.com/) (if you plan to commit audio/image assets)

## Setup

```bash
git clone https://github.com/Lempki/discord-bot-template.git my-bot
cd my-bot
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DISCORD_TOKEN (and any other values you need)
python bot.py
```

## Configuration

All settings are read from environment variables (or a `.env` file in the project root).

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Your bot's Discord token |
| `COMMAND_PREFIX` | No | `!` | Prefix for bot commands |
| `FFMPEG_PATH` | No | system PATH | Absolute path to FFmpeg binary |
| `COGS_TO_LOAD` | No | `example` | Comma-separated list of cog modules to load |
| `BOT_CHANNEL_ID` | No | — | Restrict commands to this text channel ID |
| `AUTO_ROLE_NAME` | No | — | Role name to assign on member join |

## Project structure

```
discord-bot-template/
├── bot.py              # Entry point
├── config.py           # Env var reader — edit to add new config keys
├── cogs/
│   ├── example.py      # Reference cog — copy to create new features
│   ├── voice.py        # join / leave / skip
│   └── youtube.py      # YouTube audio queue
├── utils/
│   ├── audio.py        # YouTubeDLSource, play_file helper
│   ├── checks.py       # in_bot_channel() check decorator
│   └── logging.py      # Timestamped console log helper
├── assets/
│   └── audio/          # Place .ogg / .mp3 files here (tracked by Git LFS)
├── .env.example        # Copy to .env and fill in values
└── requirements.txt
```

## Adding a new cog

1. Copy `cogs/example.py` to `cogs/my_feature.py`
2. Rename the class and add your commands/listeners
3. Add `my_feature` to `COGS_TO_LOAD` in your `.env`

## Forking this template

Use GitHub's **"Use this template"** button to create a new independent repository.  
The template ships with generic English-language cogs. Your fork can:
- Add bot-specific cogs to `cogs/`
- Extend `Config` in `config.py` with additional env vars
- Add audio files to `assets/audio/` (Git LFS handles them automatically)
- Replace or delete `cogs/example.py`
