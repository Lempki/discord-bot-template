"""Admin configuration commands for guild administrators."""

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils import database
from utils.checks import guild_of
from utils.replies import respond

if TYPE_CHECKING:
    from bot import BotApp

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
        name = s.action_ban if action.value == "ban" else s.action_kick
        await respond(interaction, s.admin_action_set, ephemeral=True, action=name)

    @admin.command(name="status")
    async def status(self, interaction: discord.Interaction) -> None:
        """Show this server's bot settings."""
        s = self.bot.strings_for(interaction, private=True)
        settings = await database.get_settings(guild_of(interaction).id)
        channel = (
            f"<#{settings.bot_channel_id}>"
            if settings.bot_channel_id
            else s.status_any_channel
        )
        if settings.auto_role_id:
            autorole = f"<@&{settings.auto_role_id}>"
        else:
            autorole = settings.auto_role_name or s.status_none
        action = s.action_ban if settings.warn_action == "ban" else s.action_kick
        await respond(
            interaction,
            s.admin_status,
            ephemeral=True,
            channel=channel,
            autorole=autorole,
            threshold=settings.warn_threshold,
            action=action,
        )

    async def cog_load(self) -> None:
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    await bot.add_cog(AdminCog(bot))
