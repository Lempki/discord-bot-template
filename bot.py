"""Entry point. Builds the bot from the environment, loads its cogs, and connects to Discord."""

import asyncio
import logging

import discord
from discord.ext import commands

from config import Config, ConfigError
from localization import LOCALES, Strings
from utils import database

log = logging.getLogger("bot")


class BotApp(commands.Bot):
    """The bot, carrying its configuration and messages for every cog to use.

    Attributes:
        config: The settings read from the environment at startup.
        strings: The messages of the configured locale.
    """

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.config = config
        if config.locale not in LOCALES:
            log.warning(f"Unknown LOCALE '{config.locale}'. Falling back to 'silent'.")
        self.strings: Strings = LOCALES.get(config.locale, LOCALES["silent"])

    async def setup_hook(self) -> None:
        """Opens the database, loads the cogs, and syncs commands once per process.

        on_ready runs again after every reconnect, so one-time work belongs here instead.
        """
        await database.init(self.config.database_path)
        for name in self.config.cogs_to_load:
            await self.load_extension(f"cogs.{name}")

        if self.config.dev_guild_id is not None:
            # A guild sync is instant, which makes it the right choice while developing.
            guild = discord.Object(id=self.config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(f"Synced {len(synced)} command(s) to guild {guild.id}.")
        else:
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} global command(s).")

    async def on_ready(self) -> None:
        """Logs the connected identity. This runs after every reconnect as well."""
        if self.user is not None:
            log.info(f"Logged in as {self.user} (ID: {self.user.id}).")

    async def close(self) -> None:
        """Disconnects from Discord and closes the database."""
        await super().close()
        await database.close()


async def main() -> None:
    """Reads the configuration and runs the bot until it is stopped."""
    discord.utils.setup_logging()
    try:
        config = Config.from_env()
    except ConfigError as error:
        log.critical(str(error))
        raise SystemExit(1) from error

    async with BotApp(config) as bot:
        try:
            await bot.start(config.discord_token)
        except discord.LoginFailure as error:
            log.critical(
                "Discord rejected DISCORD_TOKEN. Copy a fresh token from the portal."
            )
            raise SystemExit(1) from error


if __name__ == "__main__":
    asyncio.run(main())
