import asyncio
import discord
from discord.ext import commands
from config import Config
from localization import LOCALES, Strings
from utils import database


async def main():
    config = Config()

    await database.init(config.DATABASE_PATH)

    intents = discord.Intents.default()
    intents.members = True

    bot = commands.Bot(
        command_prefix=commands.when_mentioned,
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

    for cog_name in config.COGS_TO_LOAD:
        await bot.load_extension(f"cogs.{cog_name.strip()}")

    try:
        async with bot:
            await bot.start(config.DISCORD_TOKEN)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
