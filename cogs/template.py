from discord.ext import commands


class TemplateCog(commands.Cog, name="Template"):
    """Template cog showing all discord.py Cog patterns.

    Copy this file and rename the class to add a new feature group.
    Register it by adding its module name to COGS_TO_LOAD in your .env.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Commands ---

    @commands.command(name="ping", aliases=["p"])
    async def ping(self, ctx: commands.Context):
        """Replies with current latency."""
        await ctx.reply(f"Pong! `{round(self.bot.latency * 1000)}ms`")

    # --- Listeners ---

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"[{self.__class__.__name__}] loaded.")

    # --- Per-cog error handler ---

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"Missing required argument: `{error.param.name}`")
        else:
            raise error  # re-raise so the global handler in bot.py still sees it


async def setup(bot: commands.Bot):
    await bot.add_cog(TemplateCog(bot))
