"""Server event listeners: auto-role and welcome message on member join."""
import discord
from discord.ext import commands
from utils import database
from utils.logging import log


class EventsCog(commands.Cog, name="Events"):
    """Server event listeners and moderation hooks."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = str(member.guild.id)
        settings = await database.get_settings(guild_id)
        if settings is None:
            return

        # Auto-role assignment
        role_name = settings.get("auto_role_name")
        if role_name:
            role = discord.utils.get(member.guild.roles, name=role_name)
            if role:
                try:
                    await member.add_roles(role)
                    log(f"[Events] assigned role '{role_name}' to {member}")
                except discord.Forbidden:
                    log(f"[Events] missing permission to assign role '{role_name}' in {member.guild.name}")
            else:
                log(f"[Events] role '{role_name}' not found in '{member.guild.name}'")

        # Welcome message
        ch_id = settings.get("bot_channel_id")
        if ch_id:
            channel = member.guild.get_channel(ch_id)
            if channel:
                s = self.bot.strings
                if msg := s.member_join_welcome.format(member=member.mention):
                    await channel.send(msg)
                    log(f"[Events] welcomed {member} in #{channel.name}")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"[{self.__class__.__name__}] loaded.")


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
