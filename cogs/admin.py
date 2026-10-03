"""Admin configuration commands for guild administrators.

The /admin automod commands manage Discord's own AutoMod rules through the API.
Discord blocks the messages, so the bot needs no access to message content.
"""

import logging
from collections.abc import Awaitable
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils import automod, database
from utils.checks import guild_of
from utils.moderation import MAX_TIMEOUT_MINUTES
from utils.replies import chunk_lines, finish, respond

if TYPE_CHECKING:
    from bot import BotApp
    from localization import Strings

log = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Per-guild bot configuration. Requires the Manage Server permission."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    admin = app_commands.Group(
        name="admin",
        description="Configure the bot for this server.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
        allowed_contexts=app_commands.AppCommandContext(guild=True),
    )
    automod_group = app_commands.Group(
        name="automod",
        description="Manage the Discord AutoMod rules that this bot owns.",
        parent=admin,
    )

    @admin.command(name="channel")
    @app_commands.describe(
        channel="The channel to allow. Leave it empty to allow every channel."
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Set or clear the only channel where the bot accepts commands."""
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        await database.upsert_settings(
            guild.id, bot_channel_id=channel.id if channel else None
        )
        if channel:
            await respond(
                interaction,
                s.admin_channel_set,
                ephemeral=True,
                channel=channel.mention,
            )
        else:
            await respond(interaction, s.admin_channel_cleared, ephemeral=True)

    @admin.command(name="autorole")
    @app_commands.describe(role="The role to give. Leave it empty to give no role.")
    async def set_autorole(
        self, interaction: discord.Interaction, role: discord.Role | None = None
    ) -> None:
        """Set or clear the role that new members get automatically."""
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        # The ID survives role renames. The legacy name column is always cleared.
        await database.upsert_settings(
            guild.id, auto_role_id=role.id if role else None, auto_role_name=None
        )
        if role:
            await respond(
                interaction, s.admin_autorole_set, ephemeral=True, role=role.mention
            )
        else:
            await respond(interaction, s.admin_autorole_cleared, ephemeral=True)

    @admin.command(name="warnthreshold")
    @app_commands.describe(count="How many warnings trigger the action, from 1 to 20.")
    async def set_threshold(
        self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 20]
    ) -> None:
        """Set how many warnings trigger the warning action."""
        s = self.bot.strings_for(interaction, private=True)
        await database.upsert_settings(guild_of(interaction).id, warn_threshold=count)
        await respond(interaction, s.admin_threshold_set, ephemeral=True, count=count)

    @admin.command(name="warnaction")
    @app_commands.describe(action="What happens at the warning limit.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Kick", value="kick"),
            app_commands.Choice(name="Ban", value="ban"),
            app_commands.Choice(name="Timeout", value="timeout"),
        ]
    )
    async def set_action(
        self, interaction: discord.Interaction, action: app_commands.Choice[str]
    ) -> None:
        """Set what happens when a member reaches the warning limit."""
        s = self.bot.strings_for(interaction, private=True)
        await database.upsert_settings(
            guild_of(interaction).id, warn_action=action.value
        )
        await respond(
            interaction,
            s.admin_action_set,
            ephemeral=True,
            action=_action_name(s, action.value),
        )

    @admin.command(name="warntimeout")
    @app_commands.describe(
        minutes="How long the timeout lasts, from 1 minute to 28 days (40320 minutes)."
    )
    async def set_timeout(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 1, MAX_TIMEOUT_MINUTES],
    ) -> None:
        """Set how long the timeout warning action lasts."""
        s = self.bot.strings_for(interaction, private=True)
        await database.upsert_settings(
            guild_of(interaction).id, warn_timeout_minutes=minutes
        )
        await respond(interaction, s.admin_timeout_set, ephemeral=True, minutes=minutes)

    @admin.command(name="status")
    async def status(self, interaction: discord.Interaction) -> None:
        """Show this server's bot settings."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        settings = await database.get_settings(guild.id)
        channel = (
            f"<#{settings.bot_channel_id}>"
            if settings.bot_channel_id
            else s.status_any_channel
        )
        if settings.auto_role_id:
            autorole = f"<@&{settings.auto_role_id}>"
        else:
            autorole = settings.auto_role_name or s.status_none
        alert = (
            f"<#{settings.automod_alert_channel_id}>"
            if settings.automod_alert_channel_id
            else s.status_none
        )
        escalation = (
            s.escalation_warn
            if settings.automod_escalation == "warn"
            else s.escalation_none
        )
        keywords = presets = s.status_unavailable
        if self.bot.user is not None:
            try:
                state = await automod.fetch_state(guild, self.bot.user.id)
            except discord.HTTPException as error:
                log.info(f"Could not read the AutoMod rules of {guild.id}: {error}")
            else:
                keywords = str(len(state.keywords))
                names = [_preset_name(s, name) for name in state.presets]
                presets = ", ".join(names) or s.status_none
        await respond(
            interaction,
            s.admin_status,
            ephemeral=True,
            channel=channel,
            autorole=autorole,
            threshold=settings.warn_threshold,
            action=_action_name(s, settings.warn_action),
            timeout=settings.warn_timeout_minutes,
            escalation=escalation,
            alert=alert,
            keywords=keywords,
            presets=presets,
        )
        await finish(interaction)

    # --- /admin automod ---

    async def _automod_change[T](
        self, interaction: discord.Interaction, change: Awaitable[T]
    ) -> T | None:
        """Runs one AutoMod API call and explains a refusal to the admin.

        Args:
            interaction: The command, which receives the explanation.
            change: The call to run.

        Returns:
            The call's result, or None after a refusal was reported.
        """
        s = self.bot.strings_for(interaction, private=True)
        try:
            return await change
        except discord.Forbidden:
            await respond(interaction, s.automod_no_permission, ephemeral=True)
        except discord.HTTPException as error:
            log.warning(f"Discord refused an AutoMod change: {error}")
            await respond(interaction, s.automod_failed, ephemeral=True, error=error)
        return None

    @automod_group.command(name="add")
    @app_commands.describe(
        keywords="Words or phrases separated by commas. Use * as a wildcard, as in spam*."
    )
    async def automod_add(
        self, interaction: discord.Interaction, keywords: str
    ) -> None:
        """Add keywords to the bot's AutoMod keyword filter."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        parsed = automod.parse_keywords(keywords)
        too_long = [k for k in parsed if len(k) > automod.KEYWORD_LENGTH]
        if self.bot.user is None or not parsed or too_long:
            await respond(
                interaction,
                s.automod_keywords_invalid,
                ephemeral=True,
                keywords=", ".join(f"`{k}`" for k in too_long) or "-",
                length=automod.KEYWORD_LENGTH,
            )
            await finish(interaction)
            return
        settings = await database.get_settings(guild.id)
        try:
            total = await self._automod_change(
                interaction,
                automod.add_keywords(
                    guild, self.bot.user, parsed, settings.automod_alert_channel_id
                ),
            )
        except automod.KeywordLimitError:
            await respond(
                interaction,
                s.automod_keywords_limit,
                ephemeral=True,
                limit=automod.KEYWORD_LIMIT,
            )
        else:
            if total is not None:
                await respond(
                    interaction,
                    s.automod_keywords_saved,
                    ephemeral=True,
                    count=len(total),
                )
        await finish(interaction)

    @automod_group.command(name="remove")
    @app_commands.describe(keywords="The keywords to remove, separated by commas.")
    async def automod_remove(
        self, interaction: discord.Interaction, keywords: str
    ) -> None:
        """Remove keywords from the bot's AutoMod keyword filter."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        if self.bot.user is not None:
            remaining = await self._automod_change(
                interaction,
                automod.remove_keywords(
                    guild_of(interaction),
                    self.bot.user.id,
                    automod.parse_keywords(keywords),
                ),
            )
            if remaining is not None:
                await respond(
                    interaction,
                    s.automod_keywords_saved,
                    ephemeral=True,
                    count=len(remaining),
                )
        await finish(interaction)

    @automod_group.command(name="list")
    async def automod_list(self, interaction: discord.Interaction) -> None:
        """List the keywords in the bot's AutoMod keyword filter."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        state = None
        if self.bot.user is not None:
            state = await self._automod_change(
                interaction,
                automod.fetch_state(guild_of(interaction), self.bot.user.id),
            )
        if state is not None and not state.keywords:
            await respond(interaction, s.automod_keywords_none, ephemeral=True)
        elif state is not None:
            lines = [s.automod_keywords_header.format(count=len(state.keywords))]
            lines += [f"`{keyword}`" for keyword in state.keywords]
            for message in chunk_lines(lines):
                await respond(interaction, message, ephemeral=True)
        await finish(interaction)

    @automod_group.command(name="preset")
    @app_commands.describe(
        category="The kind of language that Discord's own word list filters.",
        enabled="Whether to filter this category.",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Profanity", value="profanity"),
            app_commands.Choice(name="Sexual content", value="sexual_content"),
            app_commands.Choice(name="Slurs", value="slurs"),
        ]
    )
    async def automod_preset(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        enabled: bool,
    ) -> None:
        """Turn one of Discord's preset word filters on or off."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        if self.bot.user is not None:
            settings = await database.get_settings(guild.id)
            result = await self._automod_change(
                interaction,
                automod.set_preset(
                    guild,
                    self.bot.user,
                    category.value,
                    enabled,
                    settings.automod_alert_channel_id,
                ),
            )
            if result is not None:
                await respond(
                    interaction,
                    s.automod_preset_on if enabled else s.automod_preset_off,
                    ephemeral=True,
                    preset=_preset_name(s, category.value),
                )
        await finish(interaction)

    @automod_group.command(name="alert")
    @app_commands.describe(
        channel="The channel for alerts. Leave it empty to turn alerts off."
    )
    async def automod_alert(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        """Set or clear the channel for AutoMod alerts and warning reports."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        channel_id = channel.id if channel else None
        updated = None
        if self.bot.user is not None:
            updated = await self._automod_change(
                interaction,
                automod.set_alert_channel(guild, self.bot.user.id, channel_id),
            )
        if updated is not None:
            await database.upsert_settings(
                guild.id, automod_alert_channel_id=channel_id
            )
            if channel:
                await respond(
                    interaction,
                    s.automod_alert_set,
                    ephemeral=True,
                    channel=channel.mention,
                )
            else:
                await respond(interaction, s.automod_alert_cleared, ephemeral=True)
        await finish(interaction)

    @automod_group.command(name="escalation")
    @app_commands.describe(
        mode="What happens to a member whose message AutoMod blocks."
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Nothing more", value="none"),
            app_commands.Choice(name="Add a warning", value="warn"),
        ]
    )
    async def automod_escalation(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        """Choose whether messages that AutoMod blocks count as warnings."""
        s = self.bot.strings_for(interaction, private=True)
        await database.upsert_settings(
            guild_of(interaction).id, automod_escalation=mode.value
        )
        text = (
            s.automod_escalation_warn
            if mode.value == "warn"
            else s.automod_escalation_none
        )
        await respond(interaction, text, ephemeral=True)

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")


def _action_name(s: "Strings", action: str) -> str:
    """Returns the localized name of a warning action."""
    return {"ban": s.action_ban, "timeout": s.action_timeout}.get(action, s.action_kick)


def _preset_name(s: "Strings", preset: str) -> str:
    """Returns the localized name of an AutoMod preset category."""
    return {
        "profanity": s.preset_profanity,
        "sexual_content": s.preset_sexual_content,
        "slurs": s.preset_slurs,
    }.get(preset, preset)


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(AdminCog(bot))
