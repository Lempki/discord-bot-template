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

    # A feature's commands share a group, so their names say what they belong to: /example hello.
    # The description shows in Discord's command list. Translate it like a command's docstring.
    example = app_commands.Group(
        name="example", description="Try the example commands of the template cog."
    )

    # The docstring becomes the command description shown in Discord. Keep it under 100 characters.
    # Translate it by adding the exact English text to BOT_COMMAND_TEXT in localization.py.
    @example.command(name="hello")
    async def hello(self, interaction: discord.Interaction) -> None:
        """Say hello, to show how a command of a new feature works."""
        # strings_for picks the user's language. Every message lives in the locale tables.
        s = self.bot.strings_for(interaction)
        await respond(interaction, s.example_hello, ephemeral=True)

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(TemplateCog(bot))
