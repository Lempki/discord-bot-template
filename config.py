"""Reads the bot's settings from the environment and the optional .env file."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

__all__ = ["Config", "ConfigError", "ServiceConfig"]

_SERVICE_URL = re.compile(r"^API_([A-Z0-9_]+)_URL$")


class ConfigError(Exception):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True)
class ServiceConfig:
    """Connection settings for one api-* service.

    Attributes:
        url: The service's base URL, such as http://localhost:8001.
        secret: The bearer token the service expects.
    """

    url: str
    secret: str


# A server's music queue holds this many waiting songs unless MAX_QUEUE_LENGTH says otherwise.
# A Spotify playlist is added almost at once, so without a limit one command could queue thousands.
DEFAULT_MAX_QUEUE_LENGTH = 500


@dataclass(frozen=True)
class Config:
    """All bot settings, read once at startup.

    Attributes:
        discord_token: The bot token from the Developer Portal.
        cogs_to_load: Module names under cogs/ to load, in order.
        database_path: The SQLite file for per-guild settings and moderation data.
        locale: The key of the locale in localization.LOCALES.
        ffmpeg_path: The FFmpeg executable, either a name on PATH or an absolute path.
        dev_guild_id: A guild that receives commands instantly, or None for global sync.
        services: The api-* services found in the environment, keyed by name.
        heartbeat_url: The URL of a heartbeat service that hears from the bot while it is online.
        max_queue_length: How many songs may wait in a server's music queue.
    """

    discord_token: str
    cogs_to_load: tuple[str, ...] = ("help",)
    database_path: Path = Path("data/bot.db")
    locale: str = "silent"
    ffmpeg_path: str = "ffmpeg"
    dev_guild_id: int | None = None
    services: Mapping[str, ServiceConfig] = field(default_factory=dict)
    heartbeat_url: str | None = None
    max_queue_length: int = DEFAULT_MAX_QUEUE_LENGTH

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Config":
        """Builds the configuration from environment variables.

        Args:
            environ: The variables to read. Defaults to os.environ after loading .env.

        Returns:
            The parsed configuration.

        Raises:
            ConfigError: If DISCORD_TOKEN is missing or a value is malformed.
        """
        if environ is None:
            load_dotenv()
            environ = os.environ

        token = environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise ConfigError(
                "DISCORD_TOKEN is not set. Add it to .env or the environment."
            )

        cogs = tuple(
            name.strip()
            for name in environ.get("COGS_TO_LOAD", "help").split(",")
            if name.strip()
        )

        dev_guild = environ.get("DEV_GUILD_ID", "").strip()
        if dev_guild and not dev_guild.isdigit():
            raise ConfigError("DEV_GUILD_ID must be a numeric server ID.")

        heartbeat = environ.get("HEARTBEAT_URL", "").strip()
        if heartbeat and not heartbeat.startswith(("https://", "http://")):
            raise ConfigError("HEARTBEAT_URL must start with https:// or http://.")

        queue_limit = environ.get("MAX_QUEUE_LENGTH", "").strip()
        if queue_limit and (not queue_limit.isdigit() or int(queue_limit) < 1):
            raise ConfigError("MAX_QUEUE_LENGTH must be a whole number of at least 1.")

        return cls(
            discord_token=token,
            cogs_to_load=cogs,
            database_path=Path(environ.get("DATABASE_PATH") or "data/bot.db"),
            locale=environ.get("LOCALE", "").strip() or "silent",
            ffmpeg_path=environ.get("FFMPEG_PATH", "").strip() or "ffmpeg",
            dev_guild_id=int(dev_guild) if dev_guild else None,
            services=_read_services(environ),
            heartbeat_url=heartbeat or None,
            max_queue_length=int(queue_limit)
            if queue_limit
            else DEFAULT_MAX_QUEUE_LENGTH,
        )

    def service(self, name: str) -> ServiceConfig:
        """Returns the settings of one api-* service.

        Args:
            name: The service name, such as "media" for API_MEDIA_URL.

        Returns:
            The service's URL and secret.

        Raises:
            ConfigError: If the service's URL or secret is not configured.
        """
        try:
            return self.services[name.lower()]
        except KeyError:
            prefix = f"API_{name.upper()}"
            raise ConfigError(
                f"{prefix}_URL and {prefix}_SECRET must both be set."
            ) from None


def _read_services(environ: Mapping[str, str]) -> dict[str, ServiceConfig]:
    """Pairs every API_<NAME>_URL with its API_<NAME>_SECRET."""
    services: dict[str, ServiceConfig] = {}
    for key, url in environ.items():
        match = _SERVICE_URL.match(key)
        if not match or not url.strip():
            continue
        name = match.group(1)
        secret = environ.get(f"API_{name}_SECRET", "").strip()
        if secret:
            services[name.lower()] = ServiceConfig(url=url.strip(), secret=secret)
    return services
