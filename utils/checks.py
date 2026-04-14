import discord
from discord import app_commands


def in_bot_channel():
    """Check decorator that restricts commands to the configured BOT_CHANNEL_ID.

    If BOT_CHANNEL_ID is not set, commands are allowed in any channel.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.client.config.BOT_CHANNEL_ID is None:
            return True
        return interaction.channel_id == interaction.client.config.BOT_CHANNEL_ID
    return app_commands.check(predicate)
