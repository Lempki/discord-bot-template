from collections import defaultdict
import discord
from discord import app_commands
from discord.ext import commands


class HelpCog(commands.Cog, name="Help"):
    """Lists all loaded commands grouped by cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help")
    async def help_command(self, interaction: discord.Interaction):
        """Show available commands."""
        s = self.bot.strings
        embed = discord.Embed(colour=discord.Colour.blurple())

        if title := s.help_title:
            embed.title = title

        groups: dict[str, list[app_commands.Command]] = defaultdict(list)
        for cmd in self.bot.tree.get_commands():
            cog = getattr(cmd, "binding", None)
            if cog is not None:
                groups[cog.qualified_name].append(cmd)

        for cog_name in sorted(groups):
            cmds = sorted(groups[cog_name], key=lambda c: c.name)
            lines = [f"`/{c.name}` — {c.description}" for c in cmds]
            embed.add_field(name=cog_name, value="\n".join(lines), inline=False)

        if footer := s.help_footer:
            embed.set_footer(text=footer)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
