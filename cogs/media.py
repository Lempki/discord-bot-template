"""Audio queue for YouTube, SoundCloud, and Spotify through api-media."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.audio import (
    MediaAPIClient,
    is_spotify_collection,
    is_url,
    is_youtube_playlist,
    stream_source,
)
from utils.checks import guild_of, in_bot_channel
from utils.replies import finish, respond

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Track:
    """One queued request.

    Attributes:
        query: A URL or search text, resolved to a stream only when the track starts.
        requested_by: The display name of the member who queued it.
        channel: Where to announce the track.
            Interaction tokens expire after 15 minutes.
            The player therefore posts to the channel instead of replying to the command.
    """

    query: str
    requested_by: str
    channel: discord.abc.Messageable


class GuildPlayer:
    """Plays one guild's queue in order until it is empty or the bot leaves voice."""

    def __init__(self, cog: "MediaCog", guild: discord.Guild) -> None:
        self._cog = cog
        self._guild = guild
        self.queue: asyncio.Queue[Track] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def enqueue(self, tracks: list[Track]) -> None:
        """Adds tracks to the queue and starts playing if the player is idle."""
        for track in tracks:
            self.queue.put_nowait(track)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name=f"media-player-{self._guild.id}"
            )

    def clear(self) -> None:
        """Drops every queued track without touching the current one."""
        while not self.queue.empty():
            self.queue.get_nowait()

    def cancel(self) -> None:
        """Stops the player task, used when the cog unloads."""
        self.clear()
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        while not self.queue.empty():
            track = self.queue.get_nowait()
            voice_client = self._guild.voice_client
            if (
                not isinstance(voice_client, discord.VoiceClient)
                or not voice_client.is_connected()
            ):
                # The bot left voice, so the rest of the queue has no listener.
                self.clear()
                return
            await self._play(track, voice_client)

    async def _play(self, track: Track, voice_client: discord.VoiceClient) -> None:
        bot = self._cog.bot
        s = bot.strings_for(self._guild)
        try:
            if is_url(track.query):
                info = await self._cog.client.get_info(url=track.query)
            else:
                info = await self._cog.client.get_info(query=track.query)
            stream_url = info["stream_url"]
        except Exception as error:
            # The service or the source site failed. The queue moves on to the next track.
            log.warning(f"Could not load '{track.query}': {error}")
            if message := s.load_error.format(user=track.requested_by):
                await track.channel.send(message)
            return
        title = info.get("title") or track.query
        if message := s.now_playing.format(
            title=title, channel=voice_client.channel.name
        ):
            await track.channel.send(message)
        log.info(f"Playing '{title}' in {self._guild}.")
        try:
            await bot.voice_presence.play(
                voice_client, stream_source(stream_url, bot.config.ffmpeg_path)
            )
        except Exception as error:
            log.warning(f"Playback of '{title}' failed: {error}")


class MediaCog(commands.Cog, name="Media"):
    """Audio queue supporting YouTube, SoundCloud, and Spotify, with one queue per guild."""

    def __init__(self, bot: "BotApp") -> None:
        # Raises ConfigError with the missing variable names, which stops the cog from loading.
        service = bot.config.service("media")
        self.bot = bot
        self.client = MediaAPIClient(base_url=service.url, secret=service.secret)
        self._players: dict[int, GuildPlayer] = {}

    def player(self, guild: discord.Guild) -> GuildPlayer:
        """Returns the guild's player, creating it on first use."""
        if guild.id not in self._players:
            self._players[guild.id] = GuildPlayer(self, guild)
        return self._players[guild.id]

    async def _expand(self, query: str) -> list[str]:
        """Turns a playlist or album URL into its track URLs, and anything else into itself."""
        if is_spotify_collection(query) or is_youtube_playlist(query):
            tracks = await self.client.get_playlist(query)
            return [t["webpage_url"] for t in tracks if t.get("webpage_url")]
        return [query]

    @app_commands.command(name="play")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.describe(
        url="A YouTube, SoundCloud, or Spotify link, or text to search for."
    )
    async def play(self, interaction: discord.Interaction, url: str) -> None:
        """Play a link or search result, or add it to the queue."""
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
        if interaction.channel is None or not isinstance(
            interaction.channel, discord.abc.Messageable
        ):
            await finish(interaction)
            return

        try:
            queries = await self._expand(url)
        except Exception as error:
            log.warning(f"Could not expand '{url}': {error}")
            await respond(interaction, s.load_error, user=member.display_name)
            await finish(interaction)
            return

        await self.bot.voice_presence.connect(member.voice.channel)
        tracks = [Track(q, member.display_name, interaction.channel) for q in queries]
        if len(tracks) > 1:
            await respond(
                interaction, s.queued_many, count=len(tracks), user=member.display_name
            )
        else:
            await respond(interaction, s.queued_one, user=member.display_name)
        log.info(f"Queued {len(tracks)} track(s) from {member} in {guild}.")
        self.player(guild).enqueue(tracks)
        await finish(interaction)

    @app_commands.command(name="stop")
    @app_commands.guild_only()
    @in_bot_channel()
    async def stop(self, interaction: discord.Interaction) -> None:
        """Stop playing and clear the queue."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            await respond(interaction, s.nothing_playing)
        else:
            self.player(guild).clear()
            voice_client.stop()
            await respond(interaction, s.stopped)
        await finish(interaction)

    @app_commands.command(name="pause")
    @app_commands.guild_only()
    @in_bot_channel()
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pause or resume the audio that is playing now."""
        s = self.bot.strings_for(interaction)
        voice_client = guild_of(interaction).voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            await respond(interaction, s.nothing_playing)
        elif voice_client.is_paused():
            voice_client.resume()
            await respond(interaction, s.resumed)
        else:
            voice_client.pause()
            await respond(interaction, s.paused)
        await finish(interaction)

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")

    async def cog_unload(self) -> None:
        """Stops every player and closes the media API client."""
        for player in self._players.values():
            player.cancel()
        with contextlib.suppress(Exception):
            await self.client.aclose()


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(MediaCog(bot))
