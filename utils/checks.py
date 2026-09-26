"""Reusable application command checks."""

from collections.abc import Callable
from typing import Any

import discord
from discord import app_commands

from utils import database

__all__ = ["guild_of", "in_bot_channel"]


def guild_of(interaction: discord.Interaction) -> discord.Guild:
    """Returns the guild an interaction happened in.

    Guild-only commands never run outside a guild.
    This only fails for a command that is missing the guild_only decorator.

    Raises:
        app_commands.NoPrivateMessage: If the interaction happened outside a guild.
    """
    if interaction.guild is None:
        raise app_commands.NoPrivateMessage()
    return interaction.guild


def in_bot_channel() -> Callable[[Any], Any]:
    """Restricts a command to the guild's configured bot channel.

    The check passes when no channel is configured, and outside guilds.
    Guild admins configure the channel with /admin channel.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            return True
        settings = await database.get_settings(interaction.guild_id)
        if settings.bot_channel_id is None:
            return True
        return interaction.channel_id == settings.bot_channel_id

    return app_commands.check(predicate)
