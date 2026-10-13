"""The /info commands, which show facts about the server, a member, or an avatar."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import guild_of

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)

# A member's card lists this many roles, highest first, and counts the rest.
ROLES_SHOWN = 15

# An avatar shows at this size in pixels, the largest that Discord's apps show in full.
AVATAR_SIZE = 1024


def when(moment: datetime) -> str:
    """Shows a date as a Discord timestamp and how long ago it was, in each reader's language."""
    return f"{discord.utils.format_dt(moment, 'D')} ({discord.utils.format_dt(moment, 'R')})"


class InfoCog(commands.Cog, name="Info"):
    """Facts about the server and its members, from what Discord already gives the bot."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    info = app_commands.Group(
        name="info",
        description="Show facts about this server or one of its members.",
        guild_only=True,
        allowed_contexts=app_commands.AppCommandContext(guild=True),
    )

    @info.command(name="server")
    async def server(self, interaction: discord.Interaction) -> None:
        """Show this server's age, size, and boosts, only to you."""
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        embed = discord.Embed(title=guild.name, colour=discord.Colour.blurple())
        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name=s.info_created, value=when(guild.created_at), inline=False)
        if guild.owner_id:
            embed.add_field(name=s.info_owner, value=f"<@{guild.owner_id}>")
        embed.add_field(name=s.info_members, value=str(guild.member_count or "?"))
        embed.add_field(
            name=s.info_channels,
            value=s.info_channel_counts.format(
                text=len(guild.text_channels), voice=len(guild.voice_channels)
            ),
        )
        # Every server has the @everyone role, which is no role that anyone picked.
        embed.add_field(name=s.info_roles, value=str(len(guild.roles) - 1))
        embed.add_field(
            name=s.info_boosts,
            value=s.info_boost_level.format(
                level=guild.premium_tier, count=guild.premium_subscription_count
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @info.command(name="member")
    @app_commands.describe(
        member="The member to show. Leave it empty to show yourself."
    )
    async def member(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        """Show when a member joined and which roles they have, only to you."""
        s = self.bot.strings_for(interaction, private=True)
        target = member or interaction.user
        embed = discord.Embed(
            title=target.display_name,
            description=target.mention,
            colour=target.colour if target.colour.value else discord.Colour.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name=s.info_account_created, value=when(target.created_at))
        if isinstance(target, discord.Member):
            if target.joined_at is not None:
                embed.add_field(name=s.info_joined, value=when(target.joined_at))
            if target.premium_since is not None:
                embed.add_field(name=s.info_boosting, value=when(target.premium_since))
            # Highest first, and without @everyone, which every member has.
            roles = [role for role in reversed(target.roles) if not role.is_default()]
            if roles:
                shown = " ".join(role.mention for role in roles[:ROLES_SHOWN])
                if len(roles) > ROLES_SHOWN:
                    shown += " " + s.info_more.format(count=len(roles) - ROLES_SHOWN)
                embed.add_field(name=s.info_roles, value=shown, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @info.command(name="avatar")
    @app_commands.describe(
        member="The member to show. Leave it empty to show yourself."
    )
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        """Show a member's avatar in full size, only to you."""
        s = self.bot.strings_for(interaction, private=True)
        target = member or interaction.user
        image = target.display_avatar.with_size(AVATAR_SIZE)
        embed = discord.Embed(
            title=s.info_avatar_title.format(user=target.display_name),
            url=image.url,
            colour=discord.Colour.blurple(),
        )
        embed.set_image(url=image.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(InfoCog(bot))
