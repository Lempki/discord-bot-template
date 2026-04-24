import discord
from discord import app_commands
from utils import database


def in_bot_channel():
    """Restrict commands to the guild's configured bot channel.

    Passes if no channel is configured for the guild (unrestricted).
    Guild admins configure the channel with /admin channel.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        settings = await database.get_settings(str(interaction.guild_id))
        if settings is None or settings.get("bot_channel_id") is None:
            return True
        return interaction.channel_id == settings["bot_channel_id"]
    return app_commands.check(predicate)
