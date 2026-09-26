"""Moderation commands: warn, warnings, clearwarning, clearwarnings, kick, ban."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import database

log = logging.getLogger(__name__)


class ModerationCog(commands.Cog, name="Moderation"):
    """Member moderation. Requires Kick Members permission."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _say(
        self, interaction: discord.Interaction, template: str, **kwargs
    ) -> bool:
        if not (msg := template.format(**kwargs) if kwargs else template):
            return False
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return True

    @app_commands.guild_only()
    @app_commands.command(name="warn")
    @app_commands.describe(member="Member to warn.", reason="Reason for the warning.")
    @app_commands.default_permissions(kick_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ):
        """Issue a warning to a member. Kicks or bans at the configured threshold."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings
        guild_id = interaction.guild_id

        await database.add_warning(guild_id, member.id, interaction.user.id, reason)
        count = await database.count_warnings(guild_id, member.id)
        settings = await database.get_settings(guild_id)
        threshold = settings.warn_threshold
        action = settings.warn_action

        await self._say(
            interaction,
            s.warn_issued,
            user=member.display_name,
            count=count,
            threshold=threshold,
        )
        log.info(f"{interaction.user} warned {member} ({count}/{threshold}): {reason}")

        if count >= threshold:
            await self._say(
                interaction,
                s.warn_threshold_reached,
                user=member.display_name,
                action=action,
            )
            try:
                if action == "ban":
                    await member.ban(
                        reason=f"Warning threshold reached ({count} warnings)"
                    )
                else:
                    await member.kick(
                        reason=f"Warning threshold reached ({count} warnings)"
                    )
                log.info(f"{action}ed {member} after reaching the warning threshold")
            except discord.Forbidden as e:
                await self._say(
                    interaction,
                    s.warn_action_failed,
                    user=member.display_name,
                    action=action,
                    error=str(e),
                )
                log.warning(f"Failed to {action} {member}: {e}")

    @app_commands.guild_only()
    @app_commands.command(name="warnings")
    @app_commands.describe(member="Member whose warnings to view.")
    @app_commands.default_permissions(kick_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        """List all warnings for a member."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings
        rows = await database.get_warnings(interaction.guild_id, member.id)
        if not rows:
            await self._say(interaction, s.warnings_none, user=member.display_name)
            return
        header = (
            s.warnings_list_header.format(user=member.display_name, count=len(rows))
            or f"**Warnings for {member.display_name}** ({len(rows)} total)"
        )
        lines = [header]
        for r in rows:
            date = r.created_at.date().isoformat()
            entry = (
                s.warnings_list_entry.format(id=r.id, reason=r.reason or "—", date=date)
                or f"`#{r.id}` — {r.reason or '—'} _({date})_"
            )
            lines.append(entry)
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="clearwarning")
    @app_commands.describe(warning_id="ID of the specific warning to remove.")
    @app_commands.default_permissions(kick_members=True)
    async def clearwarning(self, interaction: discord.Interaction, warning_id: int):
        """Remove a single warning by its ID."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings
        # Scoped to this guild, so a moderator cannot delete another server's warnings.
        deleted = await database.delete_warning(interaction.guild_id, warning_id)
        if deleted:
            await self._say(interaction, s.warning_removed, id=warning_id)
        else:
            await self._say(interaction, s.warning_not_found, id=warning_id)

    @app_commands.guild_only()
    @app_commands.command(name="clearwarnings")
    @app_commands.describe(member="Member whose warnings to clear.")
    @app_commands.default_permissions(kick_members=True)
    async def clearwarnings(
        self, interaction: discord.Interaction, member: discord.Member
    ):
        """Clear all warnings for a member."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings
        count = await database.delete_all_warnings(interaction.guild_id, member.id)
        await self._say(
            interaction, s.warnings_cleared, user=member.display_name, count=count
        )
        log.info(f"{interaction.user} cleared {count} warning(s) for {member}")

    @app_commands.guild_only()
    @app_commands.command(name="kick")
    @app_commands.describe(member="Member to kick.", reason="Reason for the kick.")
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ):
        """Kick a member from the server."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings
        try:
            await member.kick(reason=reason)
            await self._say(interaction, s.kick_success, user=member.display_name)
            log.info(f"{interaction.user} kicked {member}: {reason}")
        except discord.Forbidden as e:
            await self._say(
                interaction,
                s.mod_action_failed,
                user=member.display_name,
                action="kick",
                error=str(e),
            )

    @app_commands.guild_only()
    @app_commands.command(name="ban")
    @app_commands.describe(member="Member to ban.", reason="Reason for the ban.")
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ):
        """Permanently ban a member from the server."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings
        try:
            await member.ban(reason=reason)
            await self._say(interaction, s.ban_success, user=member.display_name)
            log.info(f"{interaction.user} banned {member}: {reason}")
        except discord.Forbidden as e:
            await self._say(
                interaction,
                s.mod_action_failed,
                user=member.display_name,
                action="ban",
                error=str(e),
            )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You need **Kick Members** permission to use this command.",
                    ephemeral=True,
                )
            return
        raise error

    async def cog_load(self) -> None:
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
