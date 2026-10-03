"""Server event listeners: auto-role and welcome message on member join."""

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from utils import database

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)


class EventsCog(commands.Cog, name="Events"):
    """Server event listeners and moderation hooks."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    async def _auto_role(
        self, member: discord.Member, settings: database.GuildSettings
    ) -> discord.Role | None:
        """Finds the configured auto-role, upgrading a legacy name to an ID on first use."""
        guild = member.guild
        if settings.auto_role_id is not None:
            role = guild.get_role(settings.auto_role_id)
            if role is None:
                log.warning(
                    f"Auto-role {settings.auto_role_id} no longer exists in {guild}."
                )
            return role
        if settings.auto_role_name is None:
            return None
        role = discord.utils.get(guild.roles, name=settings.auto_role_name)
        if role is None:
            log.warning(
                f"Auto-role '{settings.auto_role_name}' was not found in {guild}."
            )
            return None
        # Settings from before roles were stored by ID only have a name. Store the ID from now on.
        await database.upsert_settings(
            guild.id, auto_role_id=role.id, auto_role_name=None
        )
        return role

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Assigns the auto-role and posts the welcome message, if either is configured."""
        settings = await database.get_settings(member.guild.id)

        role = await self._auto_role(member, settings)
        if role is not None:
            try:
                await member.add_roles(role)
                log.info(f"Assigned role '{role.name}' to {member}.")
            except discord.Forbidden:
                log.warning(
                    f"Missing permission to assign role '{role.name}' in {member.guild}."
                )

        if settings.bot_channel_id is None:
            return
        channel = member.guild.get_channel(settings.bot_channel_id)
        # There is no interaction on a member join, so the guild's preferred language is used.
        strings = self.bot.strings_for(member.guild)
        if isinstance(channel, discord.TextChannel) and (
            msg := strings.member_join_welcome.format(member=member.mention)
        ):
            await channel.send(msg)
            log.info(f"Welcomed {member} in #{channel.name}.")

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(EventsCog(bot))
