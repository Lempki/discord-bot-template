import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import in_bot_channel


class VoiceCog(commands.Cog, name="Voice"):
    """Voice channel management: join, leave, skip."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _say(self, interaction: discord.Interaction, template: str, **kwargs) -> bool:
        """Format and send *template*. Returns True if a message was sent."""
        if not (msg := template.format(**kwargs)):
            return False
        if interaction.response.is_done():
            await interaction.followup.send(msg)
        else:
            await interaction.response.send_message(msg)
        return True

    @app_commands.command(name="join")
    @in_bot_channel()
    async def join(self, interaction: discord.Interaction):
        """Join the voice channel you are currently in."""
        await interaction.response.defer()
        s = self.bot.strings
        if interaction.user.voice is None:
            if not await self._say(interaction, s.not_in_voice, user=interaction.user):
                await interaction.delete_original_response()
            return
        target = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if vc:
            if vc.channel == target:
                if not await self._say(interaction, s.already_same_channel, user=interaction.user):
                    await interaction.delete_original_response()
                return
            await vc.move_to(target)
            if not await self._say(interaction, s.moved_voice, channel=target):
                await interaction.delete_original_response()
        else:
            await target.connect()
            if not await self._say(interaction, s.joined_voice, channel=target):
                await interaction.delete_original_response()

    @app_commands.command(name="leave")
    @in_bot_channel()
    async def leave(self, interaction: discord.Interaction):
        """Leave the current voice channel and stop audio."""
        await interaction.response.defer()
        s = self.bot.strings
        vc = interaction.guild.voice_client
        if vc is None:
            if not await self._say(interaction, s.bot_not_in_voice, user=interaction.user):
                await interaction.delete_original_response()
            return
        channel = vc.channel
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        if not await self._say(interaction, s.left_voice, channel=channel):
            await interaction.delete_original_response()

    @app_commands.command(name="skip")
    @in_bot_channel()
    async def skip(self, interaction: discord.Interaction):
        """Skip the currently playing audio."""
        await interaction.response.defer()
        s = self.bot.strings
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            if not await self._say(interaction, s.skipped):
                await interaction.delete_original_response()
        else:
            if not await self._say(interaction, s.nothing_to_skip):
                await interaction.delete_original_response()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                if msg := self.bot.strings.bot_channel_only:
                    await interaction.response.send_message(msg, ephemeral=True)
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
