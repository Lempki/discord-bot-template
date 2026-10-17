"""Moderation commands and the AutoMod escalation.

The commands are /warn, /warnings, /timeout, /untimeout, /kick, /ban, and /purge.
The right-click Warn and Report to moderators belong here too.
When a guild turns escalation on, every message that AutoMod blocks becomes a warning.
"""

import logging
import time
from dataclasses import replace
from datetime import timedelta
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


# Discord's own timeout lengths, in minutes, as its member menu offers them.
TIMEOUT_LENGTHS = [
    app_commands.Choice(name="60 seconds", value=1),
    app_commands.Choice(name="5 minutes", value=5),
    app_commands.Choice(name="10 minutes", value=10),
    app_commands.Choice(name="1 hour", value=60),
    app_commands.Choice(name="1 day", value=24 * 60),
    app_commands.Choice(name="1 week", value=7 * 24 * 60),
]

# Discord deletes messages in bulk only while they are younger than 14 days.
PURGE_MAX_AGE = timedelta(days=14)

# /purge for one member looks through at most this many recent messages for theirs.
PURGE_SCAN_LIMIT = 500

# A member may report one message to the moderators this often, in seconds.
REPORT_PER_SECONDS = 60.0

# A report shows this much of the message, which an embed field holds 1024 characters of.
REPORT_TEXT_LIMIT = 1000


class WarnModal(discord.ui.Modal):
    """Asks for the reason of a warning given from the member's right-click menu."""

    def __init__(
        self, cog: "ModerationCog", member: discord.Member, s: "Strings"
    ) -> None:
        super().__init__(title=s.warn_modal_title[:45] or "Warn")
        self.cog = cog
        self.member = member
        self.reason: discord.ui.TextInput[WarnModal] = discord.ui.TextInput(
            label=s.warn_modal_reason[:45] or "Reason",
            required=False,
            max_length=400,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Warns the member with the reason that the moderator typed."""
        await self.cog.warn_member(interaction, self.member, self.reason.value or None)


class ModerationCog(commands.Cog, name="Moderation"):
    """Member moderation. Each command requires the permission that it acts with."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot
        # When AutoMod last warned each member, as (guild ID, user ID) to a monotonic time.
        self._automod_warned_at: dict[tuple[int, int], float] = {}
        # Right-click menus cannot live in a cog's body, so they are made and added here.
        self._warn_menu = app_commands.ContextMenu(
            name="Warn", callback=self.warn_from_menu
        )
        self._warn_menu.default_permissions = discord.Permissions(kick_members=True)
        self._warn_menu.guild_only = True
        self._report_menu = app_commands.ContextMenu(
            name="Report to moderators", callback=self.report_message
        )
        self._report_menu.guild_only = True

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

    warnings_group = app_commands.Group(
        name="warnings",
        description="See and remove the warnings of members in this server.",
        default_permissions=discord.Permissions(kick_members=True),
        guild_only=True,
        allowed_contexts=app_commands.AppCommandContext(guild=True),
    )

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
        await self.warn_member(interaction, member, reason)

    async def warn_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None,
    ) -> None:
        """Warns a member, for /warn and for the member's right-click menu."""
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

    @warnings_group.command(name="list")
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

    @warnings_group.command(name="remove")
    @app_commands.describe(warning_id="The warning number shown by /warnings list.")
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

    @warnings_group.command(name="clear")
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

    @app_commands.command(name="timeout")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The member to time out.",
        length="How long the timeout lasts.",
        reason="Why the member is timed out. It appears in the audit log.",
    )
    @app_commands.choices(length=TIMEOUT_LENGTHS)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        length: app_commands.Choice[int],
        reason: str | None = None,
    ) -> None:
        """Time out a member, so they cannot write or speak for a while."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if await self._refuse(interaction, s, member):
            return
        until = discord.utils.utcnow() + timedelta(minutes=length.value)
        try:
            await member.timeout(until, reason=reason)
        except discord.HTTPException as error:
            await respond(
                interaction,
                s.timeout_failed,
                ephemeral=True,
                user=member.display_name,
                error=error,
            )
            return
        # A Discord timestamp shows the end in each reader's own language and time zone.
        await respond(
            interaction,
            s.timeout_success,
            ephemeral=True,
            user=member.display_name,
            until=discord.utils.format_dt(until, "f"),
        )
        log.info(
            f"{interaction.user} timed {member} out for {length.value} min: {reason}"
        )

    @app_commands.command(name="untimeout")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="The member whose timeout to lift.")
    async def untimeout(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """Lift a member's timeout."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if not member.is_timed_out():
            await respond(
                interaction, s.untimeout_none, ephemeral=True, user=member.display_name
            )
            return
        if await self._refuse(interaction, s, member):
            return
        try:
            await member.timeout(None)
        except discord.HTTPException as error:
            await respond(
                interaction,
                s.untimeout_failed,
                ephemeral=True,
                user=member.display_name,
                error=error,
            )
            return
        await respond(
            interaction, s.untimeout_success, ephemeral=True, user=member.display_name
        )
        log.info(f"{interaction.user} lifted the timeout of {member}.")

    @app_commands.command(name="purge")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        count="How many messages to delete, from 1 to 100.",
        member="Only delete this member's messages.",
    )
    async def purge(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 100],
        member: discord.Member | None = None,
    ) -> None:
        """Delete recent messages in this channel, optionally only from one member."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        channel = interaction.channel
        if not isinstance(
            channel, discord.TextChannel | discord.Thread | discord.VoiceChannel
        ):
            await respond(interaction, s.purge_none, ephemeral=True)
            return
        matched = 0

        def wanted(message: discord.Message) -> bool:
            nonlocal matched
            if matched >= count or (
                member is not None and message.author.id != member.id
            ):
                return False
            matched += 1
            return True

        # Older messages cannot be deleted in bulk, and deleting them one by one takes long.
        after = discord.utils.utcnow() - PURGE_MAX_AGE + timedelta(minutes=1)
        try:
            deleted = await channel.purge(
                limit=count if member is None else PURGE_SCAN_LIMIT,
                check=wanted,
                after=after,
                reason=f"/purge by {interaction.user}",
            )
        except discord.HTTPException as error:
            await respond(interaction, s.purge_failed, ephemeral=True, error=error)
            return
        if not deleted:
            await respond(interaction, s.purge_none, ephemeral=True)
            return
        await respond(interaction, s.purge_done, ephemeral=True, count=len(deleted))
        log.info(f"{interaction.user} purged {len(deleted)} message(s) in {channel}.")

    async def warn_from_menu(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        """Opens the reason form of a warning, from the member's right-click menu."""
        s = self.bot.strings_for(interaction, private=True)
        title = s.warn_modal_title.format(user=member.display_name)
        modal = WarnModal(self, member, replace(s, warn_modal_title=title))
        await interaction.response.send_modal(modal)

    @app_commands.checks.cooldown(1, REPORT_PER_SECONDS)
    async def report_message(
        self, interaction: discord.Interaction, message: discord.Message
    ) -> None:
        """Sends a message to the moderators' alert channel, from its right-click menu."""
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        settings = await database.get_settings(guild.id)
        channel = (
            guild.get_channel(settings.automod_alert_channel_id)
            if settings.automod_alert_channel_id
            else None
        )
        if not isinstance(channel, discord.abc.Messageable):
            await respond(interaction, s.report_no_channel, ephemeral=True)
            return
        # The alert channel is for moderators, so it gets the report even when LOCALE=silent.
        alert = self.bot.strings_for(guild, private=True)
        text = message.content or alert.report_no_text
        if len(text) > REPORT_TEXT_LIMIT:
            text = text[: REPORT_TEXT_LIMIT - 1] + "…"
        embed = discord.Embed(
            title=alert.report_title,
            description=text,
            url=message.jump_url,
            colour=discord.Colour.orange(),
        )
        # Mentions in an embed ping nobody, and they stay correct when names change.
        embed.add_field(name=alert.report_author, value=message.author.mention)
        embed.add_field(name=alert.report_channel, value=message.channel.mention)
        embed.add_field(name=alert.report_by, value=interaction.user.mention)
        if message.attachments:
            embed.add_field(
                name=alert.report_files,
                value="\n".join(a.url for a in message.attachments[:5]),
                inline=False,
            )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as error:
            log.warning(f"Could not post a report in {guild}: {error}")
            await respond(interaction, s.report_failed, ephemeral=True)
            return
        await respond(interaction, s.report_sent, ephemeral=True)
        log.info(f"A message was reported to the moderators in {guild}.")

    async def cog_load(self) -> None:
        """Adds the right-click menus and logs that the cog is ready."""
        self.bot.tree.add_command(self._warn_menu)
        self.bot.tree.add_command(self._report_menu)
        log.info(f"{self.qualified_name} cog loaded.")

    async def cog_unload(self) -> None:
        """Removes the right-click menus, which the cog added itself."""
        self.bot.tree.remove_command(self._warn_menu.name, type=self._warn_menu.type)
        self.bot.tree.remove_command(
            self._report_menu.name, type=self._report_menu.type
        )


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(ModerationCog(bot))
