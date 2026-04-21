import discord
from discord import app_commands


def in_bot_channel():
    """Check decorator for per-guild channel restrictions.

    Currently a no-op — all channels are permitted. Intended to be
    replaced with a per-guild database lookup once server admin commands
    are implemented.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        return True
    return app_commands.check(predicate)
