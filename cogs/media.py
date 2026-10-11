"""Audio queue for YouTube, SoundCloud, and Spotify through api-media."""

import asyncio
import contextlib
import logging
import random
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from utils import database
from utils.about import IDLE_STATUS, listening_to
from utils.audio import (
    MediaAPIClient,
    is_spotify_collection,
    is_url,
    is_youtube_playlist,
    source_name,
)
from utils.checks import guild_of, in_bot_channel
from utils.replies import chunk_lines, finish, mark_replied, respond

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)

# /queue lists this many waiting tracks and counts the rest, so the reply stays short.
QUEUE_SHOWN = 10

# The volume of a server that never set one, in percent, as the bot played before /volume.
DEFAULT_VOLUME = 50

# Search suggestions while typing in /play.
# Discord waits 3 seconds for them, and a search takes about one, so slow ones are dropped.
SUGGESTION_MIN_LENGTH = 3
SUGGESTION_COUNT = 5
SUGGESTION_TIMEOUT_SECONDS = 2.5
SUGGESTION_CACHE_SIZE = 256

# Discord limits a suggestion's name and value to 100 characters each.
CHOICE_LIMIT = 100

# One member may run /play this many times within the period.
PLAY_RATE, PLAY_PER_SECONDS = 3, 10.0

# One member may run the queue and volume commands this many times within the period.
CONTROL_RATE, CONTROL_PER_SECONDS = 5, 10.0

SEARCH_SOURCES = [
    app_commands.Choice(name="YouTube", value="youtube"),
    app_commands.Choice(name="SoundCloud", value="soundcloud"),
]
SEARCH_SITE_NAMES = {choice.value: choice.name for choice in SEARCH_SOURCES}

LOOP_MODES = [
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="This song", value="track"),
    app_commands.Choice(name="The whole queue", value="queue"),
]

# /previous can go back this many songs.
HISTORY_SIZE = 20

# A song that stopped this close to its end counts as finished, not skipped.
END_TOLERANCE_SECONDS = 3

# The voice channel status shows this before the song's title, and holds 500 characters.
CHANNEL_STATUS_PREFIX = "🎵 "
CHANNEL_STATUS_LIMIT = 500

# An embed's text holds this many characters, so longer lyrics are cut at a line break.
LYRICS_LIMIT = 4096


def escape(text: str) -> str:
    """Shows a title or a member's name as typed, so markdown in it cannot change a message."""
    # discord.py leaves brackets alone, and a bracket in a title could end a link early.
    return discord.utils.escape_markdown(text).replace("[", "\\[").replace("]", "\\]")


def link(text: str, url: str) -> str:
    """Makes text a link to url without the preview card that Discord adds to bare links."""
    return f"[{escape(text)}](<{url}>)"


def clock(seconds: float) -> str:
    """Formats seconds as M:SS, or as H:MM:SS from an hour on."""
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def cut_lyrics(lyrics: str, limit: int = LYRICS_LIMIT) -> str:
    """Shortens lyrics to fit an embed, ending at a whole line with an ellipsis."""
    if len(lyrics) <= limit:
        return lyrics
    cut = lyrics[: limit - 2]
    end = cut.rfind("\n")
    return (cut[:end] if end > 0 else cut).rstrip() + "\n…"


@dataclass(frozen=True)
class Track:
    """One queued request.

    Attributes:
        query: A URL or search text, resolved to a stream only when the track starts.
        requested_by: The display name of the member who queued it.
        channel: Where to announce the track.
            Interaction tokens expire after 15 minutes.
            The player therefore posts to the channel instead of replying to the command.
        title: The title when it is known before the track starts.
        duration: The length in seconds when it is known, which the wait estimate needs.
        source: The site that the request named, such as Spotify, for the now-playing line.
    """

    query: str
    requested_by: str
    channel: discord.abc.Messageable
    title: str | None = None
    duration: int | None = None
    source: str | None = None

    @property
    def label(self) -> str:
        """The title, or the link or search text when the title is not known yet."""
        if self.title:
            return self.title
        # Angle brackets keep Discord from showing a preview for every link in a list.
        return f"<{self.query}>" if is_url(self.query) else self.query

    @property
    def linked_title(self) -> str:
        """The title as a link to the track's page, or the escaped label without a page."""
        if self.title and is_url(self.query):
            return link(self.title, self.query)
        return escape(self.label)


class GuildPlayer:
    """Plays one guild's queue in order until it is empty or the bot leaves voice."""

    def __init__(self, cog: "MediaCog", guild: discord.Guild) -> None:
        self._cog = cog
        self._guild = guild
        # A deque rather than an asyncio.Queue, so that /queue can list the waiting tracks.
        self.queue: deque[Track] = deque()
        self.now_playing: str | None = None
        # When the current track started and how long it is, for the wait estimate.
        self.started_at: float | None = None
        self.now_playing_duration: int | None = None
        # The playing track with its page and title filled in, for /nowplaying and repeats.
        self.current: Track | None = None
        # The tracks that played, newest last, for /previous.
        self.history: deque[Track] = deque(maxlen=HISTORY_SIZE)
        # off, track, or queue, as /loop sets it.
        self.loop = "off"
        # Set while /previous stops the current track, which then stays out of the history.
        self.going_back = False
        self._task: asyncio.Task[None] | None = None

    @property
    def idle(self) -> bool:
        """Whether nothing plays and nothing waits, so a new track starts at once."""
        busy = self._task is not None and not self._task.done()
        return not busy and self.now_playing is None and not self.queue

    def wait_seconds(self, position: int) -> int | None:
        """Estimates how long until the track at a queue position starts.

        Args:
            position: The place in the queue, where 1 is the track after the current one.

        Returns:
            The seconds, or None when a track ahead has an unknown length.
        """
        total = 0.0
        if self.now_playing is not None:
            if self.now_playing_duration is None or self.started_at is None:
                return None
            played = time.monotonic() - self.started_at
            total += max(0.0, self.now_playing_duration - played)
        for track in list(self.queue)[: position - 1]:
            if track.duration is None:
                return None
            total += track.duration
        return round(total)

    def enqueue(self, tracks: list[Track], *, first: bool = False) -> None:
        """Adds tracks to the queue and starts playing if the player is idle.

        Args:
            tracks: The tracks in the order they should play.
            first: Whether they go before the waiting tracks, right after the current one.
        """
        if first:
            self.queue.extendleft(reversed(tracks))
        else:
            self.queue.extend(tracks)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name=f"media-player-{self._guild.id}"
            )

    def remove(self, position: int) -> Track | None:
        """Takes the track at a queue position out of the queue.

        Returns:
            The removed track, or None when no track has that position.
        """
        if not 1 <= position <= len(self.queue):
            return None
        track = self.queue[position - 1]
        del self.queue[position - 1]
        return track

    def move(self, position: int, to: int) -> Track | None:
        """Moves the track at a queue position to another position.

        A target past the end moves the track to the end.

        Returns:
            The moved track, or None when no track has the first position.
        """
        track = self.remove(position)
        if track is not None:
            self.queue.insert(min(to, len(self.queue) + 1) - 1, track)
        return track

    def shuffle(self) -> int:
        """Puts the waiting tracks in a random order and returns how many there are."""
        tracks = list(self.queue)
        random.shuffle(tracks)
        self.queue = deque(tracks)
        return len(tracks)

    def skip_to(self, position: int) -> Track | None:
        """Drops the waiting tracks before a queue position, so that track plays next.

        Returns:
            The track that plays next, or None when no track has that position.
        """
        if not 1 <= position <= len(self.queue):
            return None
        for _ in range(position - 1):
            self.queue.popleft()
        return self.queue[0]

    def clear(self) -> int:
        """Drops every queued track without touching the current one.

        Returns:
            How many tracks were dropped.
        """
        count = len(self.queue)
        self.queue.clear()
        return count

    def cancel(self) -> None:
        """Stops the player task, used when the cog unloads."""
        self.clear()
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        channel: discord.abc.Connectable | None = None
        try:
            while self.queue:
                track = self.queue.popleft()
                voice_client = self._guild.voice_client
                if (
                    not isinstance(voice_client, discord.VoiceClient)
                    or not voice_client.is_connected()
                ):
                    # The bot left voice, so the rest of the queue has no listener.
                    self.clear()
                    return
                channel = voice_client.channel
                await self._play(track, voice_client)
        finally:
            # The statuses keep the last song between tracks and clear when the music ends.
            await self._cog.show_idle(channel)

    def _after(self, played: Track, finished: bool) -> None:
        """Records a track that stopped and repeats it as /loop asks.

        Args:
            played: The track with its page and title filled in.
            finished: Whether it played to its end rather than being skipped.
        """
        if self.going_back:
            self.going_back = False
        else:
            self.history.append(played)
        if self.loop == "track" and finished:
            self.queue.appendleft(played)
        elif self.loop == "queue":
            self.queue.append(played)

    async def _play(self, track: Track, voice_client: discord.VoiceClient) -> None:
        bot = self._cog.bot
        s = bot.strings_for(self._guild)
        try:
            if is_url(track.query):
                info = await self._cog.client.get_info(url=track.query)
            else:
                info = await self._cog.client.get_info(query=track.query)
            page_url = info["webpage_url"]
        except Exception as error:
            # The service or the source site failed. The queue moves on to the next track.
            log.warning(f"Could not load '{track.query}': {error}")
            if message := s.play_failed.format(
                title=escape(track.label), user=escape(track.requested_by)
            ):
                await track.channel.send(message)
            return
        title = info.get("title") or track.query
        if message := s.now_playing.format(
            title=link(title, page_url),
            source=track.source or source_name(page_url),
            channel=voice_client.channel.name,
            user=escape(track.requested_by),
        ):
            await track.channel.send(message)
        log.info(f"Playing '{title}' in {self._guild}.")
        duration = info.get("duration_seconds") or track.duration
        played = replace(track, query=page_url, title=title, duration=duration)
        self.current = played
        self.now_playing = title
        self.now_playing_duration = duration
        started = time.monotonic()
        self.started_at = started
        await self._cog.show_playing(voice_client.channel, title)
        volume = await self._cog.volume(self._guild.id) / 100
        source = self._cog.client.audio_source(
            page_url, bot.config.ffmpeg_path, volume=volume
        )
        try:
            await bot.voice_presence.play(voice_client, source)
        except Exception as error:
            log.warning(f"Playback of '{title}' failed: {error}")
        finally:
            listened = time.monotonic() - started
            finished = duration is None or listened >= duration - END_TOLERANCE_SECONDS
            self.current = None
            self.now_playing = None
            self.now_playing_duration = None
            self.started_at = None
            self._after(played, finished)


class MediaCog(commands.Cog, name="Media"):
    """Audio queue supporting YouTube, SoundCloud, and Spotify, with one queue per guild."""

    def __init__(self, bot: "BotApp") -> None:
        # Raises ConfigError with the missing variable names, which stops the cog from loading.
        service = bot.config.service("media")
        self.bot = bot
        self.client = MediaAPIClient(base_url=service.url, secret=service.secret)
        self._players: dict[int, GuildPlayer] = {}
        # Typing repeats the same searches, such as after a deleted letter.
        self._suggestions: OrderedDict[
            tuple[str, str], list[app_commands.Choice[str]]
        ] = OrderedDict()
        self._status = IDLE_STATUS
        # Servers that refused the voice channel status, which are not asked again.
        self._status_refused: set[int] = set()

    def player(self, guild: discord.Guild) -> GuildPlayer:
        """Returns the guild's player, creating it on first use."""
        if guild.id not in self._players:
            self._players[guild.id] = GuildPlayer(self, guild)
        return self._players[guild.id]

    async def volume(self, guild_id: int) -> int:
        """Returns a guild's music volume in percent, or the default when it cannot be read."""
        try:
            settings = await database.get_settings(guild_id)
        except Exception as error:
            log.warning(f"Could not read the volume of guild {guild_id}: {error}")
            return DEFAULT_VOLUME
        return settings.music_volume

    async def _resolve(self, query: str, source: str) -> list[dict[str, Any]]:
        """Looks up the tracks that a link or search text stands for.

        A playlist or album gives its tracks.
        Anything else gives the one track that it resolves to, such as a search's first result.
        Queueing that track's own page URL makes the player play exactly the track it named.

        Args:
            query: A link, or words to search for.
            source: The site that a search looks on, youtube or soundcloud.

        Returns:
            The tracks' api-media fields, at least webpage_url, in playing order.
        """
        if is_spotify_collection(query) or is_youtube_playlist(query):
            tracks = await self.client.get_playlist(query)
            return [t for t in tracks if t.get("webpage_url")]
        if is_url(query):
            info = await self.client.get_info(url=query)
        else:
            info = await self.client.get_info(query=query, source=source)
        return [info]

    @app_commands.command(name="play")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(PLAY_RATE, PLAY_PER_SECONDS)
    @app_commands.rename(play_next="next")
    @app_commands.describe(
        query="A YouTube, SoundCloud, or Spotify link, or words to search for.",
        source="Where a search looks. A link plays from its own site.",
        play_next="Put the track first in the queue, so it plays after the current one.",
    )
    @app_commands.choices(source=SEARCH_SOURCES)
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        source: app_commands.Choice[str] | None = None,
        play_next: bool = False,
    ) -> None:
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

        site = source.value if source is not None else "youtube"
        try:
            found = await self._resolve(query, site)
        except Exception as error:
            log.warning(f"Could not load '{query}': {error}")
            found = []
        if not found:
            await respond(interaction, s.load_error, user=member.display_name)
            await finish(interaction)
            return

        await self.bot.voice_presence.connect(member.voice.channel)
        named = source_name(query) if is_url(query) else SEARCH_SITE_NAMES[site]
        tracks = [
            Track(
                info["webpage_url"],
                member.display_name,
                interaction.channel,
                info.get("title") or None,
                info.get("duration_seconds"),
                named,
            )
            for info in found
        ]
        player = self.player(guild)
        idle = player.idle
        position = 1 if play_next else len(player.queue) + 1
        wait = player.wait_seconds(position)
        player.enqueue(tracks, first=play_next)
        log.info(f"Queued {len(tracks)} track(s) from {member} in {guild}.")

        values: dict[str, Any] = {
            "user": member.display_name,
            "source": named,
            "position": position,
            "count": len(tracks),
            "title": tracks[0].linked_title,
        }
        if len(tracks) > 1:
            template = s.queued_many
            # A playlist reply links its source to the playlist that the member gave.
            values["source"] = link(named, query)
        elif idle:
            template = s.queued_now
        elif wait is not None:
            template = s.queued_one_wait
            values["minutes"] = max(1, round(wait / 60))
        else:
            template = s.queued_one
        await respond(interaction, template, **values)
        await finish(interaction)

    @play.autocomplete("query")
    async def suggest(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Suggests search results while the member types, from the chosen source."""
        text = current.strip()
        if len(text) < SUGGESTION_MIN_LENGTH or is_url(text):
            return []
        chosen = getattr(interaction.namespace, "source", None)
        site = str(getattr(chosen, "value", chosen) or "youtube")
        return await self._suggestions_for(text, site)

    async def _suggestions_for(
        self, text: str, site: str
    ) -> list[app_commands.Choice[str]]:
        key = (site, text.lower())
        if key in self._suggestions:
            self._suggestions.move_to_end(key)
            return self._suggestions[key]
        try:
            results = await asyncio.wait_for(
                self.client.search(text, site, SUGGESTION_COUNT),
                timeout=SUGGESTION_TIMEOUT_SECONDS,
            )
        except Exception as error:
            # The member can still play the words as typed, so a failure only costs suggestions.
            log.info(f"No suggestions for '{text}': {error!r}")
            return []
        choices = [
            app_commands.Choice(
                name=suggestion_name(result), value=result["webpage_url"]
            )
            for result in results
            if len(result.get("webpage_url", "")) <= CHOICE_LIMIT
        ]
        self._suggestions[key] = choices
        while len(self._suggestions) > SUGGESTION_CACHE_SIZE:
            self._suggestions.popitem(last=False)
        return choices

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

    @app_commands.command(name="queue")
    @app_commands.guild_only()
    @in_bot_channel()
    async def show_queue(self, interaction: discord.Interaction) -> None:
        """Show the song playing now and the songs in the queue."""
        s = self.bot.strings_for(interaction)
        player = self._players.get(guild_of(interaction).id)
        if player is None or (player.now_playing is None and not player.queue):
            await respond(interaction, s.queue_empty)
            await finish(interaction)
            return

        lines: list[str] = []
        if player.now_playing:
            lines.append(s.queue_now_playing.format(title=player.now_playing))
        waiting = list(player.queue)
        if waiting:
            lines.append(s.queue_next)
            for position, track in enumerate(waiting[:QUEUE_SHOWN], start=1):
                lines.append(
                    s.queue_line.format(
                        position=position, title=track.label, user=track.requested_by
                    )
                )
            if len(waiting) > QUEUE_SHOWN:
                lines.append(s.queue_more.format(count=len(waiting) - QUEUE_SHOWN))
        # The silent locale has no text for these lines, which leaves nothing to send.
        lines = [line for line in lines if line]
        for message in chunk_lines(lines):
            # Titles may contain braces, which respond() would read as placeholders.
            await respond(interaction, message.replace("{", "{{").replace("}", "}}"))
        await finish(interaction)

    async def _queue_reply(
        self, interaction: discord.Interaction, template: str, **values: Any
    ) -> None:
        await respond(interaction, template, **values)
        await finish(interaction)

    @app_commands.command(name="remove")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(position="The track's number in /queue.")
    async def remove(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
        """Remove a track from the queue."""
        s = self.bot.strings_for(interaction)
        track = self.player(guild_of(interaction)).remove(position)
        if track is None:
            await self._queue_reply(interaction, s.queue_no_position, position=position)
        else:
            await self._queue_reply(
                interaction, s.queue_removed, title=track.linked_title
            )

    @app_commands.command(name="move")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(
        position="The track's number in /queue.", to="The track's new number."
    )
    async def move(
        self,
        interaction: discord.Interaction,
        position: app_commands.Range[int, 1],
        to: app_commands.Range[int, 1],
    ) -> None:
        """Move a track to another place in the queue."""
        s = self.bot.strings_for(interaction)
        player = self.player(guild_of(interaction))
        track = player.move(position, to)
        if track is None:
            await self._queue_reply(interaction, s.queue_no_position, position=position)
        else:
            await self._queue_reply(
                interaction,
                s.queue_moved,
                title=track.linked_title,
                position=player.queue.index(track) + 1,
            )

    @app_commands.command(name="shuffle")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    async def shuffle(self, interaction: discord.Interaction) -> None:
        """Shuffle the tracks waiting in the queue."""
        s = self.bot.strings_for(interaction)
        count = self.player(guild_of(interaction)).shuffle()
        template = s.queue_shuffled if count else s.queue_nothing_waiting
        await self._queue_reply(interaction, template, count=count)

    @app_commands.command(name="clear")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    async def clear(self, interaction: discord.Interaction) -> None:
        """Remove every waiting track. The current track keeps playing."""
        s = self.bot.strings_for(interaction)
        count = self.player(guild_of(interaction)).clear()
        template = s.queue_cleared if count else s.queue_nothing_waiting
        await self._queue_reply(interaction, template, count=count)

    @app_commands.command(name="skipto")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(position="The track's number in /queue.")
    async def skip_to(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
        """Skip to a track in the queue, dropping the tracks before it."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        track = self.player(guild).skip_to(position)
        if track is None:
            await self._queue_reply(interaction, s.queue_no_position, position=position)
            return
        voice_client = guild.voice_client
        if isinstance(voice_client, discord.VoiceClient) and (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            # Stopping the current track makes the player start the next one.
            voice_client.stop()
        await self._queue_reply(
            interaction, s.queue_skipping_to, title=track.linked_title
        )

    @app_commands.command(name="volume")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(
        percent="The new volume. Leave it out to see the current one."
    )
    async def set_volume(
        self,
        interaction: discord.Interaction,
        percent: app_commands.Range[int, 0, 100] | None = None,
    ) -> None:
        """Show or change the music volume, from 0 to 100 percent."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        if percent is None:
            await self._queue_reply(
                interaction, s.volume_now, volume=await self.volume(guild.id)
            )
            return
        await database.upsert_settings(guild.id, music_volume=percent)
        voice_client = guild.voice_client
        if isinstance(voice_client, discord.VoiceClient) and isinstance(
            voice_client.source, discord.PCMVolumeTransformer
        ):
            # The playing track changes at once, and the next tracks read the stored volume.
            voice_client.source.volume = percent / 100
        await self._queue_reply(interaction, s.volume_set, volume=percent)

    @app_commands.command(name="previous")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    async def previous(self, interaction: discord.Interaction) -> None:
        """Go back to the song that played before."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        player = self.player(guild)
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not (
            voice_client.is_connected()
        ):
            await self._queue_reply(interaction, s.bot_not_in_voice)
            return
        if not player.history:
            await self._queue_reply(interaction, s.previous_none)
            return
        earlier = player.history.pop()
        if player.current is not None and (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            # The current song comes back after the earlier one, from its start.
            player.queue.appendleft(player.current)
            player.queue.appendleft(earlier)
            player.going_back = True
            voice_client.stop()
        else:
            player.enqueue([earlier], first=True)
        await self._queue_reply(
            interaction, s.previous_playing, title=earlier.linked_title
        )

    @app_commands.command(name="loop")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(mode="What to repeat.")
    @app_commands.choices(mode=LOOP_MODES)
    async def loop(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        """Repeat the current song or the whole queue."""
        s = self.bot.strings_for(interaction)
        self.player(guild_of(interaction)).loop = mode.value
        template = {"off": s.loop_off, "track": s.loop_track, "queue": s.loop_queue}
        await self._queue_reply(interaction, template[mode.value])

    @app_commands.command(name="nowplaying")
    @app_commands.guild_only()
    async def now_playing(self, interaction: discord.Interaction) -> None:
        """Show the playing song and its link, only to you."""
        s = self.bot.strings_for(interaction, private=True)
        player = self._players.get(guild_of(interaction).id)
        track = player.current if player is not None else None
        if player is None or track is None or player.started_at is None:
            await respond(interaction, s.nothing_playing, ephemeral=True)
            return
        elapsed = time.monotonic() - player.started_at
        values: dict[str, Any] = {
            "title": track.linked_title,
            "source": track.source or source_name(track.query),
            "user": escape(track.requested_by),
            "elapsed": clock(elapsed),
        }
        if track.duration:
            template = s.nowplaying_text
            values["elapsed"] = clock(min(elapsed, track.duration))
            values["duration"] = clock(track.duration)
        else:
            template = s.nowplaying_open
        await respond(interaction, template, ephemeral=True, **values)

    @app_commands.command(name="lyrics")
    @app_commands.guild_only()
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(song="A song to look up. Leave it out for the playing song.")
    async def lyrics(
        self, interaction: discord.Interaction, song: str | None = None
    ) -> None:
        """Show the lyrics of the playing song, or of a song you name."""
        await interaction.response.defer(ephemeral=True)
        s = self.bot.strings_for(interaction, private=True)
        player = self._players.get(guild_of(interaction).id)
        title, duration = song, None
        if title is None and player is not None and player.current is not None:
            title, duration = player.current.title, player.current.duration
        if not title:
            await respond(interaction, s.lyrics_nothing, ephemeral=True)
            await finish(interaction)
            return
        try:
            found = await self.client.get_lyrics(title, duration)
        except httpx.HTTPStatusError as error:
            missing = error.response.status_code == 404
            template = s.lyrics_none if missing else s.lyrics_unavailable
            await respond(interaction, template, ephemeral=True, title=escape(title))
            await finish(interaction)
            return
        except httpx.HTTPError as error:
            log.warning(f"Could not look up lyrics for '{title}': {error!r}")
            await respond(interaction, s.lyrics_unavailable, ephemeral=True)
            await finish(interaction)
            return
        embed = discord.Embed(
            title=f"{found['track']} – {found['artist']}"[:256],
            description=cut_lyrics(found["lyrics"]),
        )
        if s.lyrics_footer:
            embed.set_footer(text=s.lyrics_footer)
        await interaction.followup.send(embed=embed, ephemeral=True)
        mark_replied(interaction)

    async def cog_load(self) -> None:
        """Logs that the cog is ready."""
        log.info(f"{self.qualified_name} cog loaded.")

    async def cog_unload(self) -> None:
        """Stops every player, restores the bot's status, and closes the media API client."""
        for player in self._players.values():
            player.cancel()
        with contextlib.suppress(Exception):
            await self._set_bot_status(IDLE_STATUS)
        with contextlib.suppress(Exception):
            await self.client.aclose()

    async def show_playing(self, channel: discord.abc.Connectable, title: str) -> None:
        """Shows a song that starts in its voice channel's status and in the bot's status."""
        await self._set_channel_status(channel, f"{CHANNEL_STATUS_PREFIX}{title}")
        await self._refresh_bot_status()

    async def show_idle(self, channel: discord.abc.Connectable | None) -> None:
        """Clears the voice channel's status and the bot's status when the music ends."""
        if channel is not None:
            await self._set_channel_status(channel, None)
        await self._refresh_bot_status()

    async def _refresh_bot_status(self) -> None:
        """Shows the song while exactly one server plays, because the status is the same in all."""
        playing = [p.now_playing for p in self._players.values() if p.now_playing]
        await self._set_bot_status(playing[0] if len(playing) == 1 else IDLE_STATUS)

    async def _set_bot_status(self, name: str) -> None:
        if name == self._status:
            return
        self._status = name
        try:
            await self.bot.change_presence(activity=listening_to(name))
        except Exception as error:
            log.warning(f"Could not change the bot's status: {error!r}")

    async def _set_channel_status(
        self, channel: discord.abc.Connectable, status: str | None
    ) -> None:
        """Sets the text under a voice channel's name, or clears it with None.

        It needs the Set Voice Channel Status permission, which a server may not grant.
        A server that refuses is not asked again until the bot restarts.
        """
        if not isinstance(channel, discord.VoiceChannel):
            return
        if channel.guild.id in self._status_refused:
            return
        text = status[:CHANNEL_STATUS_LIMIT] if status else None
        try:
            await channel.edit(status=text)
        except discord.Forbidden:
            self._status_refused.add(channel.guild.id)
            log.info(
                f"{channel.guild} does not let the bot set voice channel statuses."
            )
        except discord.HTTPException as error:
            log.warning(f"Could not set the status of {channel}: {error}")


def suggestion_name(result: dict[str, Any]) -> str:
    """Names a search result in the suggestion list, with its length when it is known."""
    title = str(result.get("title") or result.get("webpage_url", ""))
    duration = result.get("duration_formatted")
    suffix = f" ({duration})" if duration else ""
    room = CHOICE_LIMIT - len(suffix)
    if len(title) > room:
        title = title[: room - 1] + "…"
    return title + suffix


async def setup(bot: "BotApp") -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(MediaCog(bot))
