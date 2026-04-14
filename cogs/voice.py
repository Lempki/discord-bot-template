import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import in_bot_channel


class VoiceCog(commands.Cog, name="Voice"):
    """Voice channel management: join, leave, skip."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _say(self, interaction: discord.Interaction, template: str, **kwargs) -> None:
        if not (msg := template.format(**kwargs)):
            return
        if interaction.response.is_done():
            await interaction.followup.send(msg)
        else:
            await interaction.response.send_message(msg)

    @app_commands.command(name="join")
    @in_bot_channel()
    async def join(self, interaction: discord.Interaction):
        """Join the voice channel you are currently in."""
        s = self.bot.strings
        if interaction.user.voice is None:
            await self._say(interaction, s.not_in_voice, user=interaction.user)
            return
        target = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if vc:
            await vc.move_to(target)
            await self._say(interaction, s.moved_voice, channel=target)
        else:
            await target.connect()
            await self._say(interaction, s.joined_voice, channel=target)

    @app_commands.command(name="leave")
    @in_bot_channel()
    async def leave(self, interaction: discord.Interaction):
        """Leave the current voice channel and stop audio."""
        s = self.bot.strings
        vc = interaction.guild.voice_client
        if vc is None:
            await self._say(interaction, s.bot_not_in_voice)
            return
        channel = vc.channel
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await self._say(interaction, s.left_voice, channel=channel)

    @app_commands.command(name="skip")
    @in_bot_channel()
    async def skip(self, interaction: discord.Interaction):
        """Skip the currently playing audio."""
        s = self.bot.strings
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await self._say(interaction, s.skipped)
        else:
            await self._say(interaction, s.nothing_to_skip)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "This command can only be used in the designated bot channel.",
                    ephemeral=True,
                )
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
