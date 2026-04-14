import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Required — raises KeyError immediately on startup if missing
    DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]

    # Optional with defaults
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "/")
    FFMPEG_PATH: str | None = os.getenv("FFMPEG_PATH") or None  # None = use system PATH

    # Comma-separated list of cog module names to load (e.g. "example,voice,youtube")
    COGS_TO_LOAD: list[str] = os.getenv("COGS_TO_LOAD", "example").split(",")

    # Optional server-specific settings
    BOT_CHANNEL_ID: int | None = (
        int(os.environ["BOT_CHANNEL_ID"]) if os.getenv("BOT_CHANNEL_ID") else None
    )
    AUTO_ROLE_NAME: str | None = os.getenv("AUTO_ROLE_NAME") or None

    # Locale to use for bot messages. Built-in values: "silent", "en".
    # Add more in localization.py. Default is "silent" (bot sends no messages).
    LOCALE: str = os.getenv("LOCALE", "silent")
