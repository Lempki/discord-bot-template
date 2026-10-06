"""Entry point. Builds the bot from the environment, loads its cogs, and connects to Discord."""

import asyncio
import contextlib
import logging
import signal
import sys

import discord
from discord import app_commands
from discord.ext import commands

from config import Config, ConfigError
from localization import COMMAND_TEXT, LOCALES, Strings
from utils import database
from utils.i18n import SILENT, LocaleTranslator, pick_locale
from utils.replies import finish, respond
from utils.voice import VoicePresence

log = logging.getLogger("bot")


class LogFormatter(logging.Formatter):
    """Formats records as "[time] [LEVEL] logger: message", separated by single spaces."""

    def __init__(self) -> None:
        super().__init__(
            "[{asctime}] [{levelname}] {name}: {message}", "%Y-%m-%d %H:%M:%S", "{"
        )


class BotApp(commands.Bot):
    """The bot, carrying its configuration, languages, and voice presence for every cog to use.

    Attributes:
        config: The settings read from the environment at startup.
        voice_presence: Joins, plays in, and leaves voice channels for every cog.
    """

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True
        # Not privileged. It delivers AutoMod executions for the warning escalation.
        intents.auto_moderation_execution = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.config = config
        self.voice_presence = VoicePresence(self)
        self.tree.on_error = self._on_command_error
        self._guild_commands_checked = False
        if config.locale not in LOCALES:
            log.warning(f"Unknown LOCALE '{config.locale}'. Falling back to English.")

    def strings_for(
        self,
        where: discord.Interaction | discord.Guild | None = None,
        *,
        private: bool = False,
    ) -> Strings:
        """Returns the messages in the best language for a user or a guild.

        Args:
            where: An interaction uses the user's language. A guild uses its preferred language.
            private: Whether the reply is ephemeral.
                Private replies are sent even when LOCALE=silent.
                Only the moderator or admin who ran the command sees them.

        Returns:
            The matching Strings. The silent locale when LOCALE=silent and the reply is public.
        """
        if self.config.locale == SILENT and not private:
            return LOCALES[SILENT]
        code: str | None = None
        if isinstance(where, discord.Interaction):
            code = where.locale.value
        elif isinstance(where, discord.Guild):
            code = where.preferred_locale.value
        return pick_locale(LOCALES, code, self.config.locale)

    async def _on_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Answers every failed command, so none is left showing "is thinking..."."""
        s = self.strings_for(interaction, private=True)
        if isinstance(error, app_commands.CheckFailure):
            text = s.bot_channel_only
        elif isinstance(error, app_commands.CommandNotFound):
            # Discord can still offer a command from a cog that this run did not load.
            log.info(f"Answered /{error.name}, which this run does not have.")
            text = s.command_unavailable
        else:
            name = (
                interaction.command.qualified_name if interaction.command else "unknown"
            )
            log.error(f"Command /{name} failed.", exc_info=error)
            text = s.command_failed
        try:
            if not await respond(interaction, text, ephemeral=True):
                await finish(interaction)
        except discord.HTTPException:
            log.warning("Could not report the failure to the user.")

    async def setup_hook(self) -> None:
        """Opens the database, loads the cogs, and syncs commands once per process.

        on_ready runs again after every reconnect, so one-time work belongs here instead.
        """
        await database.init(self.config.database_path)
        self.voice_presence.start()
        await self.tree.set_translator(LocaleTranslator(COMMAND_TEXT))
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
        # The servers are only known once the bot is connected, so this cannot run in setup_hook.
        if self.config.dev_guild_id is None and not self._guild_commands_checked:
            self._guild_commands_checked = True
            await self.remove_guild_commands()

    async def remove_guild_commands(self) -> None:
        """Removes the commands that a development run registered in a single server.

        A run with DEV_GUILD_ID registers its commands in that server only, and they stay there.
        Without DEV_GUILD_ID every command is global, so a command in one server is a leftover.
        Discord would offer it next to the global commands, and it would fail.
        """
        for guild in self.guilds:
            try:
                leftovers = await self.tree.fetch_commands(guild=guild)
                if not leftovers:
                    continue
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
            except discord.HTTPException as error:
                log.warning(
                    f"Could not check the commands registered in {guild}: {error}"
                )
                continue
            log.info(f"Removed {len(leftovers)} leftover command(s) from {guild}.")

    async def close(self) -> None:
        """Leaves voice, disconnects from Discord, and closes the database."""
        await self.voice_presence.stop()
        await super().close()
        await database.close()


async def main() -> None:
    """Reads the configuration and runs the bot until it is stopped."""
    discord.utils.setup_logging(formatter=LogFormatter())
    try:
        config = Config.from_env()
    except ConfigError as error:
        log.critical(str(error))
        raise SystemExit(1) from error

    try:
        async with BotApp(config) as bot:
            if sys.platform != "win32":
                # docker stop sends SIGTERM.
                # Closing the bot lets it leave voice and close the database.
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(
                    signal.SIGTERM, lambda: asyncio.create_task(bot.close())
                )
            try:
                await bot.start(config.discord_token)
            except discord.LoginFailure as error:
                log.critical(
                    "Discord rejected DISCORD_TOKEN. Copy a fresh token from the portal."
                )
                raise SystemExit(1) from error
    finally:
        # Runs after a normal close, Ctrl+C, and SIGTERM alike.
        # By then the bot and the database are closed.
        log.info("Shut down.")


if __name__ == "__main__":
    # Ctrl+C cancels the bot, and the async with block above still closes it cleanly.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
