"""Joins, plays in, and leaves voice channels on behalf of every cog.

The bot stays in a voice channel after playing.
It leaves once no human is left in its channel, or after a period of silence.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from discord.ext import commands

__all__ = ["IDLE_TIMEOUT", "VoicePresence"]

log = logging.getLogger(__name__)

# Seconds of silence before the bot leaves a voice channel.
IDLE_TIMEOUT = 600.0
_CHECK_INTERVAL = 30.0

VoiceChannel = discord.VoiceChannel | discord.StageChannel


class VoicePresence:
    """Tracks voice activity per guild and disconnects idle or abandoned voice clients.

    Args:
        bot: The bot whose voice clients are managed.
        idle_timeout: Seconds of silence before leaving.
    """

    def __init__(self, bot: "commands.Bot", idle_timeout: float = IDLE_TIMEOUT) -> None:
        self._bot = bot
        self._idle_timeout = idle_timeout
        self._last_activity: dict[int, float] = {}
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Starts the idle check and the listener that notices empty channels."""
        self._bot.add_listener(self._on_voice_state_update, "on_voice_state_update")
        self._task = asyncio.create_task(self._idle_loop(), name="voice-idle-check")

    async def stop(self) -> None:
        """Stops the idle check."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def touch(self, guild_id: int) -> None:
        """Marks a guild's voice client as active now."""
        self._last_activity[guild_id] = asyncio.get_running_loop().time()

    async def connect(self, channel: VoiceChannel) -> discord.VoiceClient:
        """Joins a voice channel, or moves there when already connected elsewhere in the guild.

        Returns:
            The guild's voice client.
        """
        voice_client = channel.guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)
        self.touch(channel.guild.id)
        return voice_client

    async def disconnect(self, guild: discord.Guild) -> None:
        """Stops playback and leaves the guild's voice channel, if connected."""
        self._last_activity.pop(guild.id, None)
        voice_client = guild.voice_client
        if isinstance(voice_client, discord.VoiceClient):
            voice_client.stop()
            await voice_client.disconnect()

    async def play(
        self, voice_client: discord.VoiceClient, source: discord.AudioSource
    ) -> None:
        """Plays a source and waits until it finishes, is skipped, or the bot disconnects.

        Raises:
            discord.ClientException: If the voice client is already playing.
            Exception: The error the audio player reported, if playback failed.
        """
        loop = asyncio.get_running_loop()
        finished = asyncio.Event()
        error: Exception | None = None

        def after(exc: Exception | None) -> None:
            # The audio player calls this from its own thread.
            nonlocal error
            error = exc
            loop.call_soon_threadsafe(finished.set)

        guild_id = voice_client.guild.id
        voice_client.play(source, after=after)
        self.touch(guild_id)
        await finished.wait()
        self.touch(guild_id)
        if error is not None:
            raise error

    async def _idle_loop(self) -> None:
        while True:
            await asyncio.sleep(_CHECK_INTERVAL)
            now = asyncio.get_running_loop().time()
            for voice_client in list(self._bot.voice_clients):
                if not isinstance(voice_client, discord.VoiceClient):
                    continue
                guild = voice_client.guild
                if voice_client.is_playing():
                    self.touch(guild.id)
                    continue
                last = self._last_activity.setdefault(guild.id, now)
                if now - last >= self._idle_timeout:
                    log.info(
                        f"Leaving voice in {guild} after {self._idle_timeout:.0f}s of silence."
                    )
                    await self.disconnect(guild)

    async def _on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or before.channel is None or before.channel == after.channel:
            return
        voice_client = member.guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            return
        channel = voice_client.channel
        if channel == before.channel and not any(not m.bot for m in channel.members):
            log.info(f"Leaving voice in {member.guild} because no one is left.")
            await self.disconnect(member.guild)
