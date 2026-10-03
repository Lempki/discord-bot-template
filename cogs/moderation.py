"""Moderation commands and the AutoMod escalation.

The commands are warn, warnings, clearwarning, clearwarnings, kick, and ban.
When a guild turns escalation on, every message that AutoMod blocks becomes a warning.
"""

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils import database
from utils.checks import guild_of
from utils.moderation import WarningOutcome, issue_warning
from utils.replies import chunk_lines, respond

if TYPE_CHECKING:
    from bot import BotApp
    from localization import Strings

log = logging.getLogger(__name__)

# One message can trip several rules, and a burst of messages can trip one rule many times.
# AutoMod warns a member at most once in this many seconds.
AUTOMOD_WARN_COOLDOWN = 10.0


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


def outcome_messages(s: "Strings", outcome: WarningOutcome, user: str) -> list[str]:
    """Returns the announcement and any failure for a warning that reached the threshold.

    Args:
        s: The messages to use.
        outcome: What issue_warning did.
        user: The warned member's display name.

    Returns:
        No messages below the threshold. Otherwise the announcement, then any failure.
    """
    if outcome.action is None:
        return []
    announce, failed = {
        "ban": (s.warn_threshold_ban, s.ban_failed),
        "timeout": (s.warn_threshold_timeout, s.timeout_failed),
    }.get(outcome.action, (s.warn_threshold_kick, s.kick_failed))
    values = {"user": user, "minutes": outcome.timeout_minutes, "error": outcome.error}
    messages = [announce.format(**values)]
    if outcome.error is not None:
        messages.append(failed.format(**values))
    return [message for message in messages if message]


class ModerationCog(commands.Cog, name="Moderation"):
    """Member moderation. Requires the Kick Members or Ban Members permission."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot
        # When AutoMod last warned each member, as (guild ID, user ID) to a monotonic time.
        self._automod_warned_at: dict[tuple[int, int], float] = {}

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
        """Warn a member. At the warning limit they are kicked, banned, or timed out."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if await self._refuse(interaction, s, member):
            return
        outcome = await issue_warning(member, interaction.user.id, reason)
        await respond(
            interaction,
            s.warn_issued,
            ephemeral=True,
            user=member.display_name,
            count=outcome.count,
            threshold=outcome.threshold,
        )
        for message in outcome_messages(s, outcome, member.display_name):
            await respond(interaction, message, ephemeral=True)

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

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        """Turns a message that AutoMod blocked into a warning, when the guild asks for it.

        Every rule counts, including rules made in Server Settings.
        Only the block action counts, so the alert action of the same rule adds nothing.
        """
        if execution.action.type is not discord.AutoModRuleActionType.block_message:
            return
        settings = await database.get_settings(execution.guild_id)
        if settings.automod_escalation != "warn" or self.bot.user is None:
            return
        now = time.monotonic()
        # Expired entries are dropped, so the map only holds members warned in the last seconds.
        self._automod_warned_at = {
            key: warned_at
            for key, warned_at in self._automod_warned_at.items()
            if now - warned_at < AUTOMOD_WARN_COOLDOWN
        }
        key = (execution.guild_id, execution.user_id)
        if key in self._automod_warned_at:
            return
        self._automod_warned_at[key] = now

        guild = execution.guild
        member = execution.member
        if member is None:
            try:
                member = await guild.fetch_member(execution.user_id)
            except discord.HTTPException:
                log.info(f"AutoMod user {execution.user_id} is no longer a member.")
                return
        if member.bot:
            return

        reason = "AutoMod"
        if execution.matched_keyword:
            reason = f"AutoMod: {execution.matched_keyword}"
        outcome = await issue_warning(member, self.bot.user.id, reason)
        await self._report_automod(
            guild, settings.automod_alert_channel_id, member, outcome
        )

    async def _report_automod(
        self,
        guild: discord.Guild,
        channel_id: int | None,
        member: discord.Member,
        outcome: WarningOutcome,
    ) -> None:
        """Reports an AutoMod warning in the alert channel, when the guild has one."""
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            return
        # The alert channel is for moderators, so it gets the report even when LOCALE=silent.
        s = self.bot.strings_for(guild, private=True)
        lines = [
            s.automod_warned.format(
                user=member.display_name,
                count=outcome.count,
                threshold=outcome.threshold,
            ),
            *outcome_messages(s, outcome, member.display_name),
        ]
        text = "\n".join(line for line in lines if line)
        if not text:
            return
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as error:
            log.warning(f"Could not report an AutoMod warning in {channel_id}: {error}")

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(ModerationCog(bot))
