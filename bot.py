import asyncio
import discord
from discord.ext import commands
from config import Config
from localization import LOCALES, Strings


async def main():
    config = Config()

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True

    bot = commands.Bot(
        command_prefix=config.COMMAND_PREFIX,
        intents=intents,
        help_command=None,
    )
    bot.config = config   # cogs access shared config via self.bot.config
    bot.strings: Strings = LOCALES.get(config.LOCALE, LOCALES["silent"])

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        raise error

    for cog_name in config.COGS_TO_LOAD:
        await bot.load_extension(f"cogs.{cog_name.strip()}")

    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
