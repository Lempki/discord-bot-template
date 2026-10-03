"""Template cog showing the patterns every cog in this bot follows.

Copy this file and rename the class to add a new feature group.
Register it by adding its module name to COGS_TO_LOAD in your .env.
"""

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.replies import respond

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)


class TemplateCog(commands.Cog, name="Template"):
    """An example feature group with one command."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    # The docstring becomes the command description shown in Discord. Keep it under 100 characters.
    # Translate it by adding the exact English text to COMMAND_TEXT in localization.py.
    @app_commands.command(name="ping")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Show how long the bot takes to reach Discord."""
        # strings_for picks the user's language. Every message lives in the locale tables.
        s = self.bot.strings_for(interaction)
        await respond(
            interaction,
            s.ping_reply,
            ephemeral=True,
            latency=round(self.bot.latency * 1000),
        )

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(TemplateCog(bot))
