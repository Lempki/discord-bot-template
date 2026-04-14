import discord
from discord import app_commands
from discord.ext import commands


class TemplateCog(commands.Cog, name="Template"):
    """Template cog showing discord.py Application Command patterns.

    Copy this file and rename the class to add a new feature group.
    Register it by adding its module name to COGS_TO_LOAD in your .env.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Commands ---

    @app_commands.command(name="ping")
    async def ping(self, interaction: discord.Interaction):
        """Replies with current latency."""
        await interaction.response.send_message(f"Pong! `{round(self.bot.latency * 1000)}ms`")

    # --- Listeners ---

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"[{self.__class__.__name__}] loaded.")

    # --- Per-cog error handler ---

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "This command can only be used in the designated bot channel.",
                    ephemeral=True,
                )
            return
        raise error  # re-raise so the global handler in bot.py still sees it


async def setup(bot: commands.Bot):
    await bot.add_cog(TemplateCog(bot))
