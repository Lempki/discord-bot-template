from discord.ext import commands


def in_bot_channel():
    """Check decorator that restricts commands to the configured BOT_CHANNEL_ID.

    If BOT_CHANNEL_ID is not set, commands are allowed in any channel.
    """
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.bot.config.BOT_CHANNEL_ID is None:
            return True
        return ctx.channel.id == ctx.bot.config.BOT_CHANNEL_ID
    return commands.check(predicate)
