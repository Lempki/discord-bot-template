"""Moderation commands: warn, warnings, clearwarning, clearwarnings, kick, ban."""

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils import database
from utils.checks import guild_of
from utils.replies import respond

if TYPE_CHECKING:
    from bot import BotApp
    from localization import Strings

log = logging.getLogger(__name__)

# Discord rejects messages longer than 2000 characters.
MESSAGE_LIMIT = 2000


def blocked_reason(
    s: "Strings", actor: discord.Member, target: discord.Member, me: discord.Member
) -> str | None:
    """Explains why actor may not moderate target, or returns None when they may.

    Discord only checks the bot's own permissions and role position.
    The moderator's position has to be checked here.
    Otherwise anyone with Kick Members could remove an admin.

    Args:
        s: The messages to explain the refusal with.
        actor: The member who ran the command.
        target: The member to be moderated.
        me: The bot's own member object in the guild.
    """
    guild = target.guild
    if target == actor:
        return s.mod_target_self
    if target == guild.owner or target.id == me.id:
        return s.mod_target_protected.format(user=target.display_name)
    if actor != guild.owner and target.top_role >= actor.top_role:
        return s.mod_target_higher.format(user=target.display_name)
    if target.top_role >= me.top_role:
        return s.mod_bot_too_low.format(user=target.display_name)
    return None


def chunk_lines(lines: Iterable[str], limit: int = MESSAGE_LIMIT) -> list[str]:
    """Joins lines into as few messages as possible, each within the character limit."""
    messages: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            messages.append(current)
            candidate = line
        current = candidate[:limit]
    if current:
        messages.append(current)
    return messages


class ModerationCog(commands.Cog, name="Moderation"):
    """Member moderation. Requires the Kick Members or Ban Members permission."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    async def _refuse(
        self, interaction: discord.Interaction, s: "Strings", target: discord.Member
    ) -> bool:
        """Replies with the reason and returns True when the target may not be moderated."""
        guild = guild_of(interaction)
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            return True
        reason = blocked_reason(s, actor, target, guild.me)
        if reason is None:
            return False
        await respond(interaction, reason, ephemeral=True)
        return True

    @app_commands.command(name="warn")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(
        member="The member to warn.", reason="Why the member is warned."
    )
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Warn a member. Reaching the warning limit kicks or bans them."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if await self._refuse(interaction, s, member):
            return
        guild = guild_of(interaction)

        await database.add_warning(guild.id, member.id, interaction.user.id, reason)
        count = await database.count_warnings(guild.id, member.id)
        settings = await database.get_settings(guild.id)
        threshold = settings.warn_threshold
        await respond(
            interaction,
            s.warn_issued,
            ephemeral=True,
            user=member.display_name,
            count=count,
            threshold=threshold,
        )
        log.info(f"{interaction.user} warned {member} ({count}/{threshold}): {reason}")
        if count < threshold:
            return

        audit_reason = f"Warning threshold reached ({count} warnings)"
        try:
            if settings.warn_action == "ban":
                await respond(
                    interaction,
                    s.warn_threshold_ban,
                    ephemeral=True,
                    user=member.display_name,
                )
                await member.ban(reason=audit_reason)
            else:
                await respond(
                    interaction,
                    s.warn_threshold_kick,
                    ephemeral=True,
                    user=member.display_name,
                )
                await member.kick(reason=audit_reason)
            log.info(
                f"Applied {settings.warn_action} to {member} at the warning threshold."
            )
        except discord.HTTPException as error:
            failed = s.ban_failed if settings.warn_action == "ban" else s.kick_failed
            await respond(
                interaction,
                failed,
                ephemeral=True,
                user=member.display_name,
                error=error,
            )
            log.warning(f"Could not {settings.warn_action} {member}: {error}")

    @app_commands.command(name="warnings")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="The member whose warnings to list.")
    async def warnings(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """List a member's warnings in this server."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        rows = await database.get_warnings(guild_of(interaction).id, member.id)
        if not rows:
            await respond(
                interaction, s.warnings_none, ephemeral=True, user=member.display_name
            )
            return
        lines = [
            s.warnings_list_header.format(user=member.display_name, count=len(rows))
        ]
        lines += [
            s.warnings_list_entry.format(
                id=row.id,
                reason=row.reason or s.warnings_no_reason,
                date=row.created_at.date().isoformat(),
            )
            for row in rows
        ]
        for message in chunk_lines(lines):
            await respond(interaction, message, ephemeral=True)

    @app_commands.command(name="clearwarning")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(warning_id="The warning number shown by /warnings.")
    async def clearwarning(
        self, interaction: discord.Interaction, warning_id: int
    ) -> None:
        """Remove one warning by its number."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        # Scoped to this guild, so a moderator cannot delete another server's warnings.
        if await database.delete_warning(guild_of(interaction).id, warning_id):
            await respond(interaction, s.warning_removed, ephemeral=True, id=warning_id)
        else:
            await respond(
                interaction, s.warning_not_found, ephemeral=True, id=warning_id
            )

    @app_commands.command(name="clearwarnings")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="The member whose warnings to remove.")
    async def clearwarnings(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """Remove every warning of a member in this server."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        count = await database.delete_all_warnings(guild_of(interaction).id, member.id)
        await respond(
            interaction,
            s.warnings_cleared,
            ephemeral=True,
            user=member.display_name,
            count=count,
        )
        log.info(f"{interaction.user} cleared {count} warning(s) for {member}.")

    @app_commands.command(name="kick")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(
        member="The member to kick.",
        reason="Why the member is kicked. It appears in the audit log.",
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Kick a member from this server."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if await self._refuse(interaction, s, member):
            return
        try:
            await member.kick(reason=reason)
        except discord.HTTPException as error:
            await respond(
                interaction,
                s.kick_failed,
                ephemeral=True,
                user=member.display_name,
                error=error,
            )
            return
        await respond(
            interaction, s.kick_success, ephemeral=True, user=member.display_name
        )
        log.info(f"{interaction.user} kicked {member}: {reason}")

    @app_commands.command(name="ban")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(
        member="The member to ban.",
        reason="Why the member is banned. It appears in the audit log.",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        """Ban a member from this server."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if await self._refuse(interaction, s, member):
            return
        try:
            await member.ban(reason=reason)
        except discord.HTTPException as error:
            await respond(
                interaction,
                s.ban_failed,
                ephemeral=True,
                user=member.display_name,
                error=error,
            )
            return
        await respond(
            interaction, s.ban_success, ephemeral=True, user=member.display_name
        )
        log.info(f"{interaction.user} banned {member}: {reason}")

    async def cog_load(self) -> None:
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    await bot.add_cog(ModerationCog(bot))
