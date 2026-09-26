"""Voice channel commands: join, leave, and skip."""

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import guild_of, in_bot_channel
from utils.replies import finish, respond

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)


class VoiceCog(commands.Cog, name="Voice"):
    """Voice channel management. The bot leaves on its own once it is alone or idle."""

    def __init__(self, bot: "BotApp") -> None:
        self.bot = bot

    @app_commands.command(name="join")
    @app_commands.guild_only()
    @in_bot_channel()
    async def join(self, interaction: discord.Interaction) -> None:
        """Join your voice channel."""
        # A voice handshake can take longer than the 3 seconds Discord allows for a reply.
        await interaction.response.defer()
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or member.voice is None
            or member.voice.channel is None
        ):
            await respond(interaction, s.not_in_voice, user=member.display_name)
            await finish(interaction)
            return
        target = member.voice.channel
        current = guild.voice_client
        if isinstance(current, discord.VoiceClient) and current.channel == target:
            await respond(interaction, s.already_same_channel, user=member.display_name)
        else:
            moved = isinstance(current, discord.VoiceClient)
            await self.bot.voice_presence.connect(target)
            await respond(
                interaction,
                s.moved_voice if moved else s.joined_voice,
                channel=target.name,
            )
        await finish(interaction)

    @app_commands.command(name="leave")
    @app_commands.guild_only()
    @in_bot_channel()
    async def leave(self, interaction: discord.Interaction) -> None:
        """Leave the voice channel and stop playing."""
        await interaction.response.defer()
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            await respond(interaction, s.bot_not_in_voice)
        else:
            channel = voice_client.channel
            await self.bot.voice_presence.disconnect(guild)
            await respond(interaction, s.left_voice, channel=channel.name)
        await finish(interaction)

    @app_commands.command(name="skip")
    @app_commands.guild_only()
    @in_bot_channel()
    async def skip(self, interaction: discord.Interaction) -> None:
        """Skip the audio that is playing now."""
        s = self.bot.strings_for(interaction)
        voice_client = guild_of(interaction).voice_client
        if isinstance(voice_client, discord.VoiceClient) and voice_client.is_playing():
            # Stopping ends the current source, and the media queue moves on to the next track.
            voice_client.stop()
            await respond(interaction, s.skipped)
        else:
            await respond(interaction, s.nothing_playing)
        await finish(interaction)

    async def cog_load(self) -> None:
        log.info(f"{self.qualified_name} cog loaded.")


async def setup(bot: "BotApp") -> None:
    await bot.add_cog(VoiceCog(bot))
