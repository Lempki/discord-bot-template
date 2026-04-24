import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Required — raises KeyError immediately on startup if missing
    DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]

    # Optional with defaults
    FFMPEG_PATH: str | None = os.getenv("FFMPEG_PATH") or None  # None = use system PATH

    # Comma-separated list of cog module names to load (e.g. "template,voice,media")
    COGS_TO_LOAD: list[str] = os.getenv("COGS_TO_LOAD", "template").split(",")

    # Path to the SQLite database file for per-guild settings and moderation data.
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "bot.db")

    # Locale to use for bot messages. Built-in values: "silent", "en".
    # Add more in localization.py. Default is "silent" (bot sends no messages).
    LOCALE: str = os.getenv("LOCALE", "silent")

    # discord-api-media service. Required when the media cog is loaded.
    DISCORD_API_MEDIA_URL: str | None = os.getenv("DISCORD_API_MEDIA_URL") or None
    DISCORD_API_MEDIA_SECRET: str | None = os.getenv("DISCORD_API_MEDIA_SECRET") or None
