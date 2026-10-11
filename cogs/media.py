"""Audio queue for YouTube, SoundCloud, and Spotify through api-media."""

import asyncio
import contextlib
import logging
import random
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from math import ceil
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
from utils.replies import finish, mark_replied, respond
from utils.strings import CoreStrings

if TYPE_CHECKING:
    from bot import BotApp

log = logging.getLogger(__name__)

# /queue shows this many waiting tracks on each page.
QUEUE_PAGE_SIZE = 10

# The page buttons of /queue work this long, in seconds, within the 15 minutes of a reply.
QUEUE_VIEW_TIMEOUT = 600

# The panel lists this many waiting tracks and counts the rest.
PANEL_NEXT_SHOWN = 3

# A title in a list is cut to this many characters, so a page stays within an embed's limit.
LIST_TITLE_LIMIT = 80

# A link longer than this is left out of a list, for the same reason.
LIST_URL_LIMIT = 200

# An embed's title holds 256 characters.
EMBED_TITLE_LIMIT = 256

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

# The panel's repeat button steps through the modes in this order, as music apps do.
NEXT_LOOP_MODE = {"off": "queue", "queue": "track", "track": "off"}

# The panel's buttons that only show something to the presser, so anyone may press them.
PRIVATE_PANEL_BUTTONS = {"media:queue", "media:lyrics"}

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


def shorten(text: str, limit: int) -> str:
    """Cuts text to a length, ending with an ellipsis when it was longer."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
        source: The site that the request named, such as Spotify, for the panel.
        thumbnail: The track's picture, which the panel shows when it is known.
        artist: The performers, when the site knows the track as music, such as on Spotify.
        song: The song's name without the artist, known together with the artist.
        album: The album that the song is on.
        collection: The playlist or album that the track was queued from, by name.
        collection_url: That playlist's or album's link.
    """

    query: str
    requested_by: str
    channel: discord.abc.Messageable
    title: str | None = None
    duration: int | None = None
    source: str | None = None
    thumbnail: str | None = None
    artist: str | None = None
    song: str | None = None
    album: str | None = None
    collection: str | None = None
    collection_url: str | None = None

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

    @property
    def list_line(self) -> str:
        """The shortened title as a link, with its length, for the lists in an embed."""
        title = escape(shorten(self.label, LIST_TITLE_LIMIT))
        if is_url(self.query) and len(self.query) <= LIST_URL_LIMIT:
            # An embed shows no preview cards, so the link needs no angle brackets.
            title = f"[{title}]({self.query})"
        return f"{title} `{clock(self.duration)}`" if self.duration else title


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
        # When the playing track was paused, so its progress stands still until it resumes.
        self.paused_at: float | None = None
        # The message that shows the playing track with its buttons.
        # The lock keeps two updates from posting two panels.
        self.panel: discord.Message | None = None
        self.panel_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    @property
    def idle(self) -> bool:
        """Whether nothing plays and nothing waits, so a new track starts at once."""
        busy = self._task is not None and not self._task.done()
        return not busy and self.now_playing is None and not self.queue

    def elapsed(self) -> float:
        """How many seconds of the current track have played, leaving out its pauses."""
        if self.started_at is None:
            return 0.0
        now = self.paused_at if self.paused_at is not None else time.monotonic()
        return max(0.0, now - self.started_at)

    def toggle_pause(self, voice_client: discord.VoiceClient) -> bool:
        """Pauses the playing track, or resumes a paused one.

        Returns:
            Whether the track is paused now.
        """
        if voice_client.is_paused():
            voice_client.resume()
            if self.paused_at is not None and self.started_at is not None:
                # The track resumes where it stopped, so its start moves by the pause.
                self.started_at += time.monotonic() - self.paused_at
            self.paused_at = None
            return False
        voice_client.pause()
        self.paused_at = time.monotonic()
        return True

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
            total += max(0.0, self.now_playing_duration - self.elapsed())
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
            # The statuses and the panel keep the last song between tracks.
            # They change when the music ends.
            await self._cog.end_panel(self)
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
        log.info(f"Playing '{title}' in {self._guild}.")
        duration = info.get("duration_seconds") or track.duration
        played = replace(
            track,
            query=page_url,
            title=title,
            duration=duration,
            source=track.source or source_name(page_url),
            thumbnail=info.get("thumbnail_url") or track.thumbnail,
            artist=info.get("artist") or track.artist,
            song=info.get("track") or track.song,
            album=info.get("album") or track.album,
        )
        self.current = played
        self.now_playing = title
        self.now_playing_duration = duration
        self.started_at = time.monotonic()
        self.paused_at = None
        await self._cog.show_playing(voice_client.channel, title)
        await self._cog.refresh_panel(self._guild, new_track=True)
        volume = await self._cog.volume(self._guild.id) / 100
        source = self._cog.client.audio_source(
            page_url, bot.config.ffmpeg_path, volume=volume
        )
        try:
            await bot.voice_presence.play(voice_client, source)
        except Exception as error:
            log.warning(f"Playback of '{title}' failed: {error}")
        finally:
            listened = self.elapsed()
            finished = duration is None or listened >= duration - END_TOLERANCE_SECONDS
            self.current = None
            self.now_playing = None
            self.now_playing_duration = None
            self.started_at = None
            self.paused_at = None
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
        # The panel buttons' cooldown of each member, as the commands have.
        self._button_cooldowns: dict[int, app_commands.Cooldown] = {}
        # Handles the buttons of every panel, including those posted before a restart.
        self._panel_buttons = PanelView(self)

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

    async def _resolve(
        self, query: str, source: str
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Looks up the tracks that a link or search text stands for.

        A playlist or album gives its tracks.
        Anything else gives the one track that it resolves to, such as a search's first result.
        Queueing that track's own page URL makes the player play exactly the track it named.

        Args:
            query: A link, or words to search for.
            source: The site that a search looks on, youtube or soundcloud.

        Returns:
            The playlist's or album's name, or None for a single track.
            Then the tracks' api-media fields, at least webpage_url, in playing order.
        """
        if is_spotify_collection(query) or is_youtube_playlist(query):
            name, tracks = await self.client.get_playlist(query)
            return name, [t for t in tracks if t.get("webpage_url")]
        if is_url(query):
            info = await self.client.get_info(url=query)
        else:
            info = await self.client.get_info(query=query, source=source)
        return None, [info]

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
        collection: str | None = None
        try:
            collection, found = await self._resolve(query, site)
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
                info.get("thumbnail_url"),
                info.get("artist"),
                info.get("track"),
                info.get("album"),
                collection,
                query if collection else None,
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
            "more": len(tracks) - 1,
            "title": tracks[0].linked_title,
        }
        if len(tracks) > 1:
            # The first track of a playlist starts at once when nothing played.
            template = s.queued_many_now if idle else s.queued_many
            # A playlist reply links to the playlist that the member gave, by its name if known.
            if collection:
                values["source"] = s.collection_on.format(
                    collection=link(collection, query), source=named
                )
            else:
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
        if not idle:
            # The panel's list of the next tracks changed.
            await self.refresh_panel(guild)

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
        guild = guild_of(interaction)
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            await respond(interaction, s.nothing_playing)
            await finish(interaction)
            return
        paused = self.player(guild).toggle_pause(voice_client)
        await respond(interaction, s.paused if paused else s.resumed)
        await finish(interaction)
        await self.refresh_panel(guild)

    @app_commands.command(name="queue")
    @app_commands.guild_only()
    async def show_queue(self, interaction: discord.Interaction) -> None:
        """Show the playing song and the queue, only to you."""
        await self.send_queue(interaction)

    async def send_queue(self, interaction: discord.Interaction) -> None:
        """Shows the queue privately, a page at a time, for /queue and the panel."""
        s = self.bot.strings_for(interaction, private=True)
        player = self._players.get(guild_of(interaction).id)
        if player is None or (player.current is None and not player.queue):
            await respond(interaction, s.queue_empty, ephemeral=True)
            return
        view = QueueView(self, player, s, interaction)
        embed = view.page_embed()
        if view.pages > 1:
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )
        else:
            view.stop()
            await interaction.response.send_message(embed=embed, ephemeral=True)
        mark_replied(interaction)

    def queue_embed(
        self, player: "GuildPlayer", s: CoreStrings, page: int
    ) -> tuple[discord.Embed, int]:
        """Builds one page of the queue.

        Args:
            player: The guild's player.
            s: The texts in the reader's language.
            page: The page to show, from 0. A page past the end shows the last one.

        Returns:
            The embed and the number of pages.
        """
        waiting = list(player.queue)
        pages = max(1, ceil(len(waiting) / QUEUE_PAGE_SIZE))
        page = min(max(page, 0), pages - 1)
        lines: list[str] = []
        if player.current is not None:
            lines.append(s.queue_now_playing.format(title=player.current.list_line))
        if waiting:
            lines.append(s.queue_next)
            first = page * QUEUE_PAGE_SIZE
            for position, track in enumerate(
                waiting[first : first + QUEUE_PAGE_SIZE], start=first + 1
            ):
                lines.append(
                    s.queue_line.format(
                        position=position,
                        title=track.list_line,
                        user=escape(track.requested_by),
                    )
                )
        else:
            lines.append(s.queue_nothing_waiting)
        embed = discord.Embed(title=s.queue_title, description="\n".join(lines))
        if waiting:
            length = sum(track.duration or 0 for track in waiting)
            embed.set_footer(
                text=s.queue_footer.format(
                    page=page + 1,
                    pages=pages,
                    count=len(waiting),
                    length=clock(length),
                )
            )
        return embed, pages

    async def _queue_reply(
        self, interaction: discord.Interaction, template: str, **values: Any
    ) -> None:
        await respond(interaction, template, **values)
        await finish(interaction)
        # A change to the queue or the volume shows on the panel.
        if interaction.guild is not None:
            await self.refresh_panel(interaction.guild)

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
        earlier = self.go_back(player, voice_client)
        if earlier is None:
            await self._queue_reply(interaction, s.previous_none)
        else:
            await self._queue_reply(
                interaction, s.previous_playing, title=earlier.linked_title
            )

    def go_back(
        self, player: GuildPlayer, voice_client: discord.VoiceClient
    ) -> Track | None:
        """Plays the song before, for /previous and the panel.

        Returns:
            The song that plays now, or None when no song played before.
        """
        if not player.history:
            return None
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
        return earlier

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
        elapsed = player.elapsed()
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
        await self.send_lyrics(interaction, song)

    async def send_lyrics(
        self, interaction: discord.Interaction, song: str | None
    ) -> None:
        """Shows lyrics privately, for /lyrics and the panel."""
        # Thinking makes a button press answer with a new private message.
        await interaction.response.defer(ephemeral=True, thinking=True)
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
        """Starts listening to the panel buttons and logs that the cog is ready."""
        self.bot.add_view(self._panel_buttons)
        log.info(f"{self.qualified_name} cog loaded.")

    async def cog_unload(self) -> None:
        """Stops every player, restores the bot's status, and closes the media API client."""
        self._panel_buttons.stop()
        for player in self._players.values():
            player.cancel()
        with contextlib.suppress(Exception):
            await self._set_bot_status(IDLE_STATUS)
        with contextlib.suppress(Exception):
            await self.client.aclose()

    def panel_embed(
        self,
        player: GuildPlayer,
        track: Track,
        s: CoreStrings,
        *,
        state: str,
        volume: int = DEFAULT_VOLUME,
    ) -> discord.Embed:
        """Builds the panel's card for a track.

        Args:
            player: The guild's player, for the progress, the next tracks, and the repeat mode.
            track: The track with its page and title filled in.
            s: The texts in the server's language.
            state: playing, paused, or ended. An ended panel shows only the last track.
            volume: The server's volume in percent.
        """
        heading = {
            "playing": s.panel_playing,
            "paused": s.panel_paused,
            "ended": s.panel_ended,
        }[state]
        # With the artist known, the title names only the song, and the artist gets a line.
        named_song = bool(track.song and track.artist)
        embed = discord.Embed(
            title=shorten(track.song if named_song else track.label, EMBED_TITLE_LIMIT),
            url=track.query if is_url(track.query) else None,
        )
        embed.set_author(name=heading)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        lines: list[str] = []
        credits: list[str] = []
        if named_song and track.artist:
            credits.append(f"**{escape(track.artist)}**")
        if track.album and track.album != track.collection:
            # A track queued from its own album names the album in the line below.
            credits.append(f"*{escape(track.album)}*")
        if credits:
            lines.append(" · ".join(credits))
        source = track.source or source_name(track.query)
        if track.collection:
            collection = escape(track.collection)
            if track.collection_url:
                collection = f"[{collection}]({track.collection_url})"
            source = s.collection_on.format(collection=collection, source=source)
        lines.append(
            s.panel_details.format(source=source, user=escape(track.requested_by))
        )
        elapsed = player.elapsed()
        if state == "playing" and track.duration:
            # Discord counts a relative timestamp down by itself, so the panel needs no edits.
            ends = int(time.time() + max(0.0, track.duration - elapsed))
            lines.append(
                s.panel_ends.format(
                    duration=clock(track.duration), ends=f"<t:{ends}:R>"
                )
            )
        elif state == "playing":
            started = int(time.time() - elapsed)
            lines.append(s.panel_started.format(started=f"<t:{started}:R>"))
        elif state == "paused":
            progress = clock(elapsed)
            if track.duration:
                progress += f" / {clock(track.duration)}"
            lines.append(s.panel_paused_at.format(progress=progress))
        embed.description = "\n".join(lines)
        if state == "ended":
            return embed

        waiting = list(player.queue)
        upcoming = [
            f"`{position}.` {queued.list_line}"
            for position, queued in enumerate(waiting[:PANEL_NEXT_SHOWN], start=1)
        ]
        if len(waiting) > PANEL_NEXT_SHOWN:
            upcoming.append(s.panel_more.format(count=len(waiting) - PANEL_NEXT_SHOWN))
        embed.add_field(
            name=s.panel_next,
            value="\n".join(upcoming) or s.panel_next_none,
            inline=False,
        )
        loop_name = {
            "off": s.panel_loop_off,
            "track": s.panel_loop_track,
            "queue": s.panel_loop_queue,
        }[player.loop]
        embed.set_footer(text=s.panel_footer.format(loop=loop_name, volume=volume))
        return embed

    async def refresh_panel(
        self, guild: discord.Guild, *, new_track: bool = False
    ) -> None:
        """Shows the playing track on the guild's panel.

        The panel is one message in the channel where the track was requested.
        A new track moves it to the bottom when the chat has moved on, so it stays in sight.
        Any other change edits it where it is.

        Args:
            guild: The guild whose panel to update.
            new_track: Whether a track just started.
        """
        player = self._players.get(guild.id)
        if player is None or player.current is None:
            return
        s = self.bot.strings_for(guild)
        if not s.panel_playing:
            # The silent locale posts no panel.
            return
        track = player.current
        voice_client = guild.voice_client
        paused = (
            isinstance(voice_client, discord.VoiceClient) and voice_client.is_paused()
        )
        embed = self.panel_embed(
            player,
            track,
            s,
            state="paused" if paused else "playing",
            volume=await self.volume(guild.id),
        )
        view = PanelView(self, s=s, paused=paused, loop=player.loop)
        async with player.panel_lock:
            await self._place_panel(player, track.channel, embed, view, new_track)

    async def _place_panel(
        self,
        player: GuildPlayer,
        channel: discord.abc.Messageable,
        embed: discord.Embed,
        view: "PanelView",
        new_track: bool,
    ) -> None:
        # The cog's own PanelView answers every press, so this copy only draws the buttons.
        # A stopped view is not kept in memory for each message that it was sent with.
        view.stop()
        old = player.panel
        same_channel = old is not None and old.channel.id == getattr(
            channel, "id", None
        )
        at_bottom = (
            old is not None and getattr(channel, "last_message_id", None) == old.id
        )
        try:
            if old is not None and same_channel and (at_bottom or not new_track):
                try:
                    player.panel = await old.edit(embed=embed, view=view)
                    return
                except discord.NotFound:
                    # Someone deleted the panel, so a new one is posted.
                    old = None
            if old is not None:
                with contextlib.suppress(discord.HTTPException):
                    await old.delete()
            player.panel = await channel.send(embed=embed, view=view)
        except discord.HTTPException as error:
            log.warning(f"Could not update the music panel: {error}")
            player.panel = None

    async def end_panel(self, player: GuildPlayer) -> None:
        """Turns the panel into a record of the last track, without buttons, when the music ends."""
        async with player.panel_lock:
            panel, player.panel = player.panel, None
            if panel is None:
                return
            s = self.bot.strings_for(panel.guild)
            last = player.history[-1] if player.history else None
            try:
                if last is None or not s.panel_ended:
                    await panel.edit(view=None)
                else:
                    embed = self.panel_embed(player, last, s, state="ended")
                    await panel.edit(embed=embed, view=None)
            except discord.HTTPException as error:
                log.info(f"Could not end the music panel: {error}")

    def button_retry_after(self, user_id: int) -> float | None:
        """Counts a member's panel press, and returns the wait when they press too fast."""
        cooldown = self._button_cooldowns.setdefault(
            user_id, app_commands.Cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
        )
        return cooldown.update_rate_limit()

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


class PanelView(discord.ui.View):
    """The buttons of the now-playing panel.

    The cog keeps one instance without a timeout, which answers the presses on every panel.
    The buttons' fixed custom IDs let it answer panels posted before a restart too.
    Each panel is sent with a copy whose labels and look match the playing state.
    """

    def __init__(
        self,
        cog: MediaCog,
        *,
        s: CoreStrings | None = None,
        paused: bool = False,
        loop: str = "off",
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        if paused:
            self.pause_button.emoji = "▶️"
        if loop != "off":
            self.loop_button.style = discord.ButtonStyle.primary
        if loop == "track":
            self.loop_button.emoji = "🔂"
        if s is not None:
            self.shuffle_button.label = s.panel_shuffle or None
            self.queue_button.label = s.panel_queue or None
            self.lyrics_button.label = s.panel_lyrics or None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Lets a member press within the cooldown, and steer the music only from its channel."""
        s = self.cog.bot.strings_for(interaction, private=True)
        retry_after = self.cog.button_retry_after(interaction.user.id)
        if retry_after is not None:
            await interaction.response.send_message(
                s.cooldown.format(seconds=ceil(retry_after)), ephemeral=True
            )
            return False
        if (interaction.data or {}).get("custom_id") in PRIVATE_PANEL_BUTTONS:
            return True
        guild = interaction.guild
        voice_client = guild.voice_client if guild is not None else None
        if (
            not isinstance(voice_client, discord.VoiceClient)
            or not voice_client.is_connected()
        ):
            await interaction.response.send_message(s.nothing_playing, ephemeral=True)
            return False
        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or member.voice is None
            or member.voice.channel != voice_client.channel
        ):
            await interaction.response.send_message(
                s.panel_not_listening, ephemeral=True
            )
            return False
        return True

    async def _start(
        self, interaction: discord.Interaction
    ) -> tuple[discord.Guild, discord.VoiceClient, GuildPlayer]:
        """Acknowledges a press and returns what the controls act on.

        interaction_check has made sure that the bot is in voice.
        The panel itself shows the result, so the press gets no message of its own.
        Never call finish() after a press.
        A press's original response is the panel itself, which finish() would delete.
        """
        await interaction.response.defer()
        guild = guild_of(interaction)
        voice_client = guild.voice_client
        assert isinstance(voice_client, discord.VoiceClient)
        return guild, voice_client, self.cog.player(guild)

    async def _tell(self, interaction: discord.Interaction, text: str) -> None:
        if text:
            await interaction.followup.send(text, ephemeral=True)

    def _strings(self, interaction: discord.Interaction) -> CoreStrings:
        return self.cog.bot.strings_for(interaction, private=True)

    @discord.ui.button(emoji="⏮️", custom_id="media:previous", row=0)
    async def previous_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Goes back to the song before."""
        _, voice_client, player = await self._start(interaction)
        if self.cog.go_back(player, voice_client) is None:
            await self._tell(interaction, self._strings(interaction).previous_none)

    @discord.ui.button(emoji="⏸️", custom_id="media:pause", row=0)
    async def pause_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Pauses or resumes the playing song."""
        guild, voice_client, player = await self._start(interaction)
        if not (voice_client.is_playing() or voice_client.is_paused()):
            await self._tell(interaction, self._strings(interaction).nothing_playing)
            return
        player.toggle_pause(voice_client)
        await self.cog.refresh_panel(guild)

    @discord.ui.button(emoji="⏭️", custom_id="media:skip", row=0)
    async def skip_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Skips to the next song, which then shows on the panel."""
        _, voice_client, _ = await self._start(interaction)
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        else:
            await self._tell(interaction, self._strings(interaction).nothing_playing)

    @discord.ui.button(emoji="🔁", custom_id="media:loop", row=0)
    async def loop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Steps through repeating nothing, the whole queue, and the current song."""
        guild, _, player = await self._start(interaction)
        player.loop = NEXT_LOOP_MODE[player.loop]
        await self.cog.refresh_panel(guild)

    @discord.ui.button(emoji="⏹️", custom_id="media:stop", row=0)
    async def stop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Stops the music and clears the queue, which ends the panel."""
        _, voice_client, player = await self._start(interaction)
        player.clear()
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

    @discord.ui.button(emoji="🔀", custom_id="media:shuffle", row=1)
    async def shuffle_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Shuffles the waiting songs."""
        guild, _, player = await self._start(interaction)
        if player.shuffle():
            await self.cog.refresh_panel(guild)
        else:
            text = self._strings(interaction).queue_nothing_waiting
            await self._tell(interaction, text)

    @discord.ui.button(emoji="📜", custom_id="media:queue", row=1)
    async def queue_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Shows the whole queue to the presser."""
        await self.cog.send_queue(interaction)

    @discord.ui.button(emoji="🎤", custom_id="media:lyrics", row=1)
    async def lyrics_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["PanelView"]
    ) -> None:
        """Shows the playing song's lyrics to the presser."""
        await self.cog.send_lyrics(interaction, None)


class QueueView(discord.ui.View):
    """The page buttons of a private queue reply. Each page shows the queue as it is now."""

    def __init__(
        self,
        cog: MediaCog,
        player: GuildPlayer,
        s: CoreStrings,
        interaction: discord.Interaction,
    ) -> None:
        super().__init__(timeout=QUEUE_VIEW_TIMEOUT)
        self.cog = cog
        self.player = player
        self.s = s
        self.interaction = interaction
        self.page = 0
        self.pages = 1

    def page_embed(self) -> discord.Embed:
        """Builds the current page and enables only the buttons that lead to another page."""
        embed, self.pages = self.cog.queue_embed(self.player, self.s, self.page)
        self.page = min(max(self.page, 0), self.pages - 1)
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.pages - 1
        return embed

    @discord.ui.button(emoji="◀️")
    async def previous_page(
        self, interaction: discord.Interaction, _: discord.ui.Button["QueueView"]
    ) -> None:
        """Shows the page before."""
        self.page -= 1
        await interaction.response.edit_message(embed=self.page_embed(), view=self)

    @discord.ui.button(emoji="▶️")
    async def next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button["QueueView"]
    ) -> None:
        """Shows the next page."""
        self.page += 1
        await interaction.response.edit_message(embed=self.page_embed(), view=self)

    async def on_timeout(self) -> None:
        """Removes the buttons, which stop working now."""
        with contextlib.suppress(discord.HTTPException):
            await self.interaction.edit_original_response(view=None)


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
