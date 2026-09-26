"""Admin configuration commands for guild administrators."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import database

log = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Per-guild bot configuration. Requires Manage Server permission."""

    def __init__(self, bot: commands.Bot):
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
        channel="The channel to restrict bot commands to, or leave empty to clear."
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        """Set or clear the channel where the bot accepts commands."""
        s = self.bot.strings
        guild_id = interaction.guild_id
        if channel:
            await database.upsert_settings(guild_id, bot_channel_id=channel.id)
            msg = (
                s.admin_channel_set.format(channel=channel.mention)
                or f"Bot channel set to {channel.mention}."
            )
        else:
            await database.upsert_settings(guild_id, bot_channel_id=None)
            msg = s.admin_channel_cleared or "Bot channel restriction removed."
        await interaction.response.send_message(msg, ephemeral=True)

    @admin.command(name="autorole")
    @app_commands.describe(
        role="Role to assign new members automatically, or leave empty to clear."
    )
    async def set_autorole(
        self, interaction: discord.Interaction, role: discord.Role | None = None
    ):
        """Set or clear the role automatically assigned to new members."""
        s = self.bot.strings
        guild_id = interaction.guild_id
        if role:
            # The ID survives role renames. The legacy name column is cleared.
            await database.upsert_settings(
                guild_id, auto_role_id=role.id, auto_role_name=None
            )
            msg = (
                s.admin_autorole_set.format(role=role.name)
                or f"Auto-role set to **{role.name}**."
            )
        else:
            await database.upsert_settings(
                guild_id, auto_role_id=None, auto_role_name=None
            )
            msg = s.admin_autorole_cleared or "Auto-role cleared."
        await interaction.response.send_message(msg, ephemeral=True)

    @admin.command(name="warnthreshold")
    @app_commands.describe(
        count="Number of warnings before automatic action is taken (1–20)."
    )
    async def set_threshold(
        self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 20]
    ):
        """Set how many warnings trigger an automatic kick or ban."""
        s = self.bot.strings
        await database.upsert_settings(interaction.guild_id, warn_threshold=count)
        msg = (
            s.admin_threshold_set.format(count=count)
            or f"Warning threshold set to {count}."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @admin.command(name="warnaction")
    @app_commands.describe(action="Action taken when the warning threshold is reached.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Kick", value="kick"),
            app_commands.Choice(name="Ban", value="ban"),
        ]
    )
    async def set_action(
        self, interaction: discord.Interaction, action: app_commands.Choice[str]
    ):
        """Set whether hitting the warning threshold kicks or bans the member."""
        s = self.bot.strings
        await database.upsert_settings(interaction.guild_id, warn_action=action.value)
        msg = (
            s.admin_action_set.format(action=action.value)
            or f"Warning action set to **{action.value}**."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @admin.command(name="status")
    async def status(self, interaction: discord.Interaction):
        """Show the current bot configuration for this server."""
        s = self.bot.strings
        settings = await database.get_settings(interaction.guild_id)
        channel = (
            f"<#{settings.bot_channel_id}>"
            if settings.bot_channel_id
            else "any channel"
        )
        if settings.auto_role_id:
            autorole = f"<@&{settings.auto_role_id}>"
        else:
            autorole = settings.auto_role_name
        threshold = settings.warn_threshold
        action = settings.warn_action
        msg = s.admin_status.format(
            channel=channel,
            autorole=autorole or "none",
            threshold=threshold,
            action=action,
        ) or (
            f"**Bot settings**\n"
            f"Channel: {channel}\n"
            f"Auto-role: {autorole or 'none'}\n"
            f"Warn threshold: {threshold}\n"
            f"Warn action: {action}"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You need **Manage Server** permission to use this command.",
                    ephemeral=True,
                )
            return
        raise error

    async def cog_load(self) -> None:
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
