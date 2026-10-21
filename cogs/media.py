"""Audio queue for YouTube, SoundCloud, and Spotify through api-media."""

import asyncio
import contextlib
import logging
import random
import time
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, replace
from math import ceil
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from utils import database
from utils.about import custom_status
from utils.audio import (
    MediaAPIClient,
    is_spotify_collection,
    is_url,
    is_youtube_playlist,
    prime,
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

# The page buttons of /queue show work this long, in seconds, within the 15 minutes of a reply.
QUEUE_VIEW_TIMEOUT = 600

# The panel lists this many waiting tracks and counts the rest.
PANEL_NEXT_SHOWN = 3

# A finished session's summary names this many members who added songs, and counts the rest.
SESSION_NAMES_SHOWN = 3

# A panel's progress line starts with its bar, or with the time for a song of unknown length.
PROGRESS_MARKS = ("▰", "▱", "`")

# The stop button's question waits this long for an answer, in seconds.
STOP_CONFIRM_TIMEOUT = 60

# The panel's progress moves this often, in seconds.
# Discord limits how often a bot may edit messages, so it cannot move every second.
PANEL_TICK_SECONDS = 10

# The progress bar has this many steps.
PROGRESS_WIDTH = 12

# The next song's audio starts buffering when this many seconds of the current one are left.
PREPARE_AUDIO_SECONDS = 20

# How often the player checks whether to prepare the next song, in seconds.
PREPARE_CHECK_SECONDS = 1.0

# A title in a list is cut to this many characters, so a page stays within an embed's limit.
LIST_TITLE_LIMIT = 80

# A link longer than this is left out of a list, for the same reason.
LIST_URL_LIMIT = 200

# An embed's title holds 256 characters.
EMBED_TITLE_LIMIT = 256

# The volume of a server that never set one, in percent.
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

WHEN_CHOICES = [
    app_commands.Choice(name="Next", value="next"),
    app_commands.Choice(name="Now", value="now"),
]

# The panel's repeat button steps through the modes in this order, as music apps do.
NEXT_LOOP_MODE = {"off": "queue", "queue": "track", "track": "off"}

# The panel's buttons that only show something to the presser, so anyone may press them.
PRIVATE_PANEL_BUTTONS = {"media:queue", "media:lyrics", "media:grab"}

# A member who leaves voice keeps their waiting songs for this long, in case they come back.
LEAVER_GRACE_SECONDS = 120

# /music previous can go back this many songs.
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


def progress_line(elapsed: float, duration: int | None) -> str:
    """Shows how far a song has played, as a bar and as M:SS / M:SS."""
    if not duration:
        return f"`{clock(elapsed)}`"
    played = min(elapsed, duration)
    filled = round(played / duration * PROGRESS_WIDTH)
    bar = "▰" * filled + "▱" * (PROGRESS_WIDTH - filled)
    return f"{bar} `{clock(played)} / {clock(duration)}`"


def loop_name(s: CoreStrings, mode: str) -> str:
    """Names a repeat mode in the panel's language."""
    return {
        "off": s.panel_loop_off,
        "track": s.panel_loop_track,
        "queue": s.panel_loop_queue,
    }[mode]


def stopped(player: GuildPlayer) -> bool:
    """Whether a member stopped the music, rather than the queue running out."""
    return player.last_action is not None and player.last_action[0].startswith(
        "stopped"
    )


def ended_heading(player: GuildPlayer, s: CoreStrings) -> str:
    """The heading of an ended panel, which tells a stop from a queue that ran out."""
    return s.panel_stopped if stopped(player) else s.panel_ended


def ended_card(embed: discord.Embed, s: CoreStrings) -> discord.Embed:
    """Turns the card of a panel that a restart left behind into a record of its song.

    The card keeps the song, its credits, and who added it, as an ended panel does.
    It loses its progress, its list of next songs, and its footer, which no longer hold.
    """
    card = embed.copy()
    if s.panel_ended:
        card.set_author(name=s.panel_ended)
    lines = (card.description or "").splitlines()
    kept = [line for line in lines if not line.startswith(PROGRESS_MARKS)]
    card.description = "\n".join(kept) or None
    card.clear_fields()
    card.remove_footer()
    return card


def session_length(seconds: float, s: CoreStrings) -> str:
    """Words how long a session played, in whole minutes, and in hours from an hour on."""
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    if hours:
        return s.session_hours.format(hours=hours, minutes=minutes)
    return s.session_minutes.format(minutes=minutes)


def join_names(names: list[str], s: CoreStrings) -> str:
    """Joins names into a sentence's list, such as "Ada, Bo, and Cy" in English."""
    if len(names) < 2:
        return "".join(names)
    if len(names) == 2:
        return s.names_two.format(first=names[0], second=names[1])
    return ", ".join(names[:-1]) + s.names_last.format(last=names[-1])


def cut_lyrics(lyrics: str, limit: int = LYRICS_LIMIT) -> str:
    """Shortens lyrics to fit an embed, ending at a whole line with an ellipsis."""
    if len(lyrics) <= limit:
        return lyrics
    cut = lyrics[: limit - 2]
    end = cut.rfind("\n")
    return (cut[:end] if end > 0 else cut).rstrip() + "\n…"


def skips_of(info: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    """Reads the parts of a track to leave out from api-media's answer."""
    skips: list[tuple[float, float]] = []
    for part in info.get("skip_segments") or ():
        with contextlib.suppress(TypeError, ValueError):
            start, end = (float(value) for value in part)
            if end > start:
                skips.append((start, end))
    return tuple(skips)


def played_length(
    duration: int | None, skips: tuple[tuple[float, float], ...]
) -> int | None:
    """The length of a track once its skipped parts are left out, in whole seconds."""
    if duration is None:
        return None
    return max(1, round(duration - sum(end - start for start, end in skips)))


def song_lines(track: Track, s: CoreStrings) -> list[str]:
    """The lines that name a song's artist and album, and where it came from and who added it."""
    lines: list[str] = []
    credits: list[str] = []
    if track.song and track.artist:
        credits.append(f"**{escape(track.artist)}**")
    if track.album and track.album != track.collection:
        # A track queued from its own album names the album in the line below.
        credits.append(f"*{escape(track.album)}*")
    if credits:
        lines.append(" · ".join(credits))
    source = track.source or source_name(track.query)
    if track.collection:
        collection = escape(collection_label(track))
        if track.collection_url:
            collection = f"[{collection}]({track.collection_url})"
        source = s.collection_on.format(collection=collection, source=source)
    lines.append(s.panel_details.format(source=source, user=escape(track.requested_by)))
    return lines


def song_card(track: Track, s: CoreStrings, server: str) -> discord.Embed:
    """The card that the panel's grab button sends: the song, its credits, and its length."""
    named_song = bool(track.song and track.artist)
    embed = discord.Embed(
        title=shorten(track.song if named_song else track.label, EMBED_TITLE_LIMIT),
        url=track.query if is_url(track.query) else None,
    )
    embed.set_author(name=shorten(s.grab_heading.format(server=server), 256))
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    lines = song_lines(track, s)
    if track.duration:
        lines.append(s.grab_length.format(length=clock(track.duration)))
    embed.description = "\n".join(lines)
    embed.timestamp = discord.utils.utcnow()
    return embed


def owner(track: Track) -> int | str:
    """Who queued a track, by ID when it is known, so the queue can take turns between members."""
    if track.requested_by_id is not None:
        return track.requested_by_id
    return track.requested_by


def collection_label(track: Track) -> str:
    """The track's playlist or album by name, without an artist that the card names already.

    YouTube names an artist's album "Artist - Album".
    The card shows the artist in the song's title or credits, so the name drops it.
    """
    name = track.collection or ""
    head, separator, rest = name.partition(" - ")
    if (
        separator
        and rest
        and (head == track.artist or track.label.startswith(f"{head} - "))
    ):
        return rest
    return name


@dataclass(frozen=True)
class Track:
    """One queued request.

    Attributes:
        query: The track's page URL or search text. The player looks it up again before it plays.
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
        requested_by_id: The ID of the member who queued it, which may skip it without a vote.
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
    requested_by_id: int | None = None

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


class SkipOutcome(NamedTuple):
    """What a request to skip did.

    Attributes:
        skip: Whether the song stops now.
        votes: The listeners' votes to skip so far, or 0 for a skip without a vote.
        needed: The votes that skip the song, or 0 for a skip without a vote.
        repeated: Whether the member had voted already, so their vote did not count again.
    """

    skip: bool
    votes: int = 0
    needed: int = 0
    repeated: bool = False

    def vote_text(self, s: CoreStrings) -> str:
        """Tells the member how the vote stands, or that they voted already."""
        template = s.skip_already_voted if self.repeated else s.skip_voted
        return template.format(votes=self.votes, needed=self.needed)


@dataclass
class Prepared:
    """The next song, looked up and maybe already buffering, while the current one plays.

    Attributes:
        track: The queued track that was prepared. It counts only while it is next in the queue.
        info: Its api-media fields, or None while the lookup runs or after it failed.
        source: Its audio, which starts buffering shortly before the current song ends.
        failed: Whether the lookup failed, so it is not tried again until the track plays.
    """

    track: Track
    info: dict[str, Any] | None = None
    source: discord.AudioSource | None = None
    failed: bool = False

    def close(self) -> None:
        """Stops the buffering audio, such as its FFmpeg process and its stream."""
        if self.source is not None:
            try:
                self.source.cleanup()
            except Exception as error:
                # The song is dropped either way, so a failed cleanup only goes to the log.
                log.info(f"Could not stop prepared audio: {error!r}")
            self.source = None


class GuildPlayer:
    """Plays one guild's queue in order until it is empty or the bot leaves voice."""

    def __init__(self, cog: MediaCog, guild: discord.Guild) -> None:
        self._cog = cog
        self._guild = guild
        # A deque rather than an asyncio.Queue, so that /queue can list the waiting tracks.
        self.queue: deque[Track] = deque()
        self.now_playing: str | None = None
        # When the current track started and how long it is, for the wait estimate.
        self.started_at: float | None = None
        self.now_playing_duration: int | None = None
        # The playing track with its page and title filled in, for the panel and for repeats.
        self.current: Track | None = None
        # The tracks that played, newest last, for /music previous.
        self.history: deque[Track] = deque(maxlen=HISTORY_SIZE)
        # off, track, or queue, as /music loop sets it.
        self.loop = "off"
        # Set while a track is stopped and put back in the queue, as /music previous and Now do.
        # It then stays out of the history and out of the repeat.
        self.requeued = False
        # Set while a stop ends the music, so that repeating the queue does not restart it.
        self.halted = False
        # Who last changed the music, how, and the values that the panel's line names.
        # A skip's note waits for the song that the skip started, so it shows on that song.
        self.last_action: tuple[str, str, dict[str, Any]] | None = None
        self.action_carries = False
        # The members who voted to skip the playing song.
        self.skip_votes: set[int] = set()
        # The songs that played since the music started, and how long they played in all.
        self.session: list[Track] = []
        self.session_seconds = 0.0
        # When the playing track was paused, so its progress stands still until it resumes.
        self.paused_at: float | None = None
        # The message that shows the playing track with its buttons.
        # The lock keeps two updates from posting two panels.
        self.panel: discord.Message | None = None
        self.panel_lock = asyncio.Lock()
        # The next song, prepared while the current one plays.
        self._prepared: Prepared | None = None
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

    def note(
        self, action: str, user: str, *, carries: bool = False, **values: Any
    ) -> None:
        """Records who changed the music and how, for the panel's line.

        Args:
            action: The change, which names an action_<action> text, such as skipped.
            user: The member's display name.
            carries: Whether the note belongs to the next song, as after a skip.
            **values: The values that the text names, such as title.
        """
        self.last_action = (action, user, values)
        self.action_carries = carries

    def note_stop(self, user: str) -> None:
        """Records a stop for the ended panel, with where the song stopped and what waited.

        The waiting songs may be other members' requests, so the panel says that they went.
        """
        at = clock(self.elapsed())
        duration = self.current.duration if self.current is not None else None
        if duration:
            at = f"{at} / {clock(duration)}"
        count = len(self.queue)
        action = {0: "stopped", 1: "stopped_cleared_one"}.get(count, "stopped_cleared")
        self.note(action, user, at=at, count=count)

    def play_now(self, track: Track, voice_client: discord.VoiceClient) -> bool:
        """Plays a track at once, putting the current one back in the queue right after it.

        Returns:
            Whether a playing track was interrupted.
        """
        if self.current is not None and (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            # The current song comes back after the new one, from its start.
            self.queue.appendleft(self.current)
            self.queue.appendleft(track)
            self.requeued = True
            voice_client.stop()
            return True
        self.enqueue([track], first=True)
        return False

    def halt(self, voice_client: discord.VoiceClient) -> None:
        """Stops the playing track and drops the queue, as /music stop and the stop button do."""
        self.clear()
        if voice_client.is_playing() or voice_client.is_paused():
            self.halted = True
            voice_client.stop()

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

    def enqueue(
        self, tracks: list[Track], *, first: bool = False, turns: bool = False
    ) -> int:
        """Adds tracks to the queue and starts playing if the player is idle.

        Args:
            tracks: The tracks in the order they should play.
            first: Whether they go before the waiting tracks, right after the current one.
            turns: Whether each track waits for its member's turn, so that the members take turns.
                Without it, the tracks go to the end.

        Returns:
            The queue position of the first track, where 1 is the track after the current one.
        """
        position = 1 if first else len(self.queue) + 1
        if first:
            self.queue.extendleft(reversed(tracks))
        elif turns:
            for number, track in enumerate(tracks):
                place = self._turn_place(track)
                self.queue.insert(place, track)
                if number == 0:
                    position = place + 1
        else:
            self.queue.extend(tracks)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name=f"media-player-{self._guild.id}"
            )
        return position

    def _turn_place(self, track: Track) -> int:
        """Finds where a track goes so that the members who add songs take turns.

        Each member's songs make up turns: their first song is in turn 1, their second in turn 2.
        The playing song counts as its member's first turn.
        A new track goes before the first song of a later turn than its own.
        It never passes a song of the same or an earlier turn, so the order stays as it was added.

        Returns:
            The index in the queue to insert the track at.
        """
        member = owner(track)
        turns: Counter[int | str] = Counter()
        if self.current is not None:
            turns[owner(self.current)] += 1
        own_turn = (
            turns[member] + sum(owner(queued) == member for queued in self.queue) + 1
        )
        for index, queued in enumerate(self.queue):
            turns[owner(queued)] += 1
            if turns[owner(queued)] > own_turn:
                return index
        return len(self.queue)

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
        self._drop_prepared()
        if self._task is not None:
            self._task.cancel()

    def _drop_prepared(self) -> None:
        if self._prepared is not None:
            self._prepared.close()
            self._prepared = None

    def _take_prepared(self, track: Track) -> Prepared | None:
        """Hands over the prepared song if it is the track that starts, and drops it otherwise."""
        prepared, self._prepared = self._prepared, None
        if prepared is not None and prepared.track is track:
            return prepared
        if prepared is not None:
            prepared.close()
        return None

    async def _lookup(self, track: Track) -> dict[str, Any]:
        """Asks api-media for a track's page and details."""
        if is_url(track.query):
            return await self._cog.client.get_info(url=track.query)
        return await self._cog.client.get_info(query=track.query)

    async def _prepare_next(self) -> None:
        """Gets the next song ready while the current one plays.

        It looks the next song up at once.
        Its audio starts buffering when PREPARE_AUDIO_SECONDS of the current song are left.
        A change to the queue, such as a skip, a move, or a shuffle, drops what was prepared.
        A paused song, or one of unknown length, starts no audio early.
        """
        while True:
            await asyncio.sleep(PREPARE_CHECK_SECONDS)
            upcoming = self.queue[0] if self.queue else None
            if self._prepared is not None and self._prepared.track is not upcoming:
                self._drop_prepared()
            if upcoming is None:
                continue
            if self._prepared is None:
                prepared = self._prepared = Prepared(upcoming)
                try:
                    info = await self._lookup(upcoming)
                except Exception as error:
                    # The song is looked up again when it starts, which reports a failure.
                    log.info(f"Could not prepare '{upcoming.query}': {error}")
                    prepared.failed = True
                    continue
                if prepared is self._prepared:
                    prepared.info = info
                continue
            prepared = self._prepared
            duration = self.now_playing_duration
            if (
                prepared.info is None
                or prepared.source is not None
                or duration is None
                or self.paused_at is not None
                or duration - self.elapsed() > PREPARE_AUDIO_SECONDS
            ):
                continue
            source = await self._audio(prepared.info)
            if prepared is self._prepared:
                prepared.source = source
            else:
                # The queue changed while the settings were read, so this audio has no song.
                try:
                    source.cleanup()
                except Exception as error:
                    log.info(f"Could not stop unused audio: {error!r}")

    async def _audio(self, info: dict[str, Any]) -> discord.AudioSource:
        """Starts a track's audio with the server's volume and loudness, minus its skips."""
        volume = await self._cog.volume(self._guild.id) / 100
        even = await self._cog.evens_loudness(self._guild.id)
        return self._cog.client.audio_source(
            info["webpage_url"],
            self._cog.bot.config.ffmpeg_path,
            volume=volume,
            skips=skips_of(info),
            even_loudness=even,
        )

    def remove_member(self, member_id: int) -> int:
        """Takes a member's waiting songs out of the queue, leaving the playing one.

        Returns:
            How many songs left the queue.
        """
        kept = [track for track in self.queue if track.requested_by_id != member_id]
        removed = len(self.queue) - len(kept)
        if removed:
            self.queue.clear()
            self.queue.extend(kept)
        return removed

    async def _run(self) -> None:
        channel: discord.abc.Connectable | None = None
        # A run lasts from the first song until the queue runs out, which makes one session.
        self.session = []
        self.session_seconds = 0.0
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
            self._drop_prepared()
            # The statuses and the panel keep the last song between tracks.
            # They change when the music ends.
            await self._cog.end_panel(self)
            await self._cog.show_idle(channel)

    def _after(self, played: Track, finished: bool) -> None:
        """Records a track that stopped and repeats it as /music loop asks.

        Args:
            played: The track with its page and title filled in.
            finished: Whether it played to its end rather than being skipped.
        """
        if self.requeued:
            # The track is already back in the queue, so it is neither recorded nor repeated.
            self.requeued = False
            return
        self.history.append(played)
        if self.halted:
            self.halted = False
            return
        if self.loop == "track" and finished:
            self.queue.appendleft(played)
        elif self.loop == "queue":
            self.queue.append(played)

    async def _tick(self) -> None:
        """Moves the panel's progress while a song plays, and stands still while it is paused."""
        while True:
            await asyncio.sleep(PANEL_TICK_SECONDS)
            if self.paused_at is not None or self.panel is None:
                continue
            try:
                await self._cog.refresh_panel(self._guild)
            except Exception as error:
                log.warning(f"Could not move the panel's progress: {error!r}")

    async def _play(self, track: Track, voice_client: discord.VoiceClient) -> None:
        bot = self._cog.bot
        # The player's messages belong to the music that a member started, so silence keeps them.
        s = bot.strings_for(self._guild, private=True)
        prepared = self._take_prepared(track)
        try:
            if prepared is not None and prepared.info is not None:
                info = prepared.info
            else:
                info = await self._lookup(track)
            page_url = info["webpage_url"]
        except Exception as error:
            if prepared is not None:
                prepared.close()
            # The service or the source site failed. The queue moves on to the next track.
            log.warning(f"Could not load '{track.query}': {error}")
            if message := s.play_failed.format(
                title=escape(track.label), user=escape(track.requested_by)
            ):
                await track.channel.send(message)
            return
        # A song keeps the names it was queued with, such as Spotify's for a Spotify link.
        # The lookup fills in only what the queue did not know.
        title = track.title or info.get("title") or track.query
        names = track if track.artist else None
        log.info(f"Playing '{title}' in {self._guild}.")
        # The skipped parts never play, so the panel counts the length without them.
        duration = played_length(
            info.get("duration_seconds") or track.duration, skips_of(info)
        )
        played = replace(
            track,
            query=page_url,
            title=title,
            duration=duration,
            source=track.source or source_name(page_url),
            thumbnail=track.thumbnail or info.get("thumbnail_url"),
            artist=names.artist if names else info.get("artist"),
            song=names.song if names else info.get("track"),
            album=names.album if names else info.get("album"),
        )
        self.current = played
        self.now_playing = title
        self.now_playing_duration = duration
        self.started_at = time.monotonic()
        self.paused_at = None
        self.skip_votes.clear()
        if self.action_carries:
            self.action_carries = False
        else:
            self.last_action = None
        await self._cog.show_playing(voice_client.channel, title)
        await self._cog.refresh_panel(self._guild, new_track=True)
        if prepared is not None and prepared.source is not None:
            # The audio has been buffering since shortly before the previous song ended.
            source = prepared.source
            if isinstance(source, discord.PCMVolumeTransformer):
                source.volume = await self._cog.volume(self._guild.id) / 100
        else:
            source = await self._audio(info)
        # The player's clock starts when audio waits, or the song's start plays too fast.
        await prime(source)
        ticker = asyncio.create_task(self._tick(), name=f"media-panel-{self._guild.id}")
        preparer = asyncio.create_task(
            self._prepare_next(), name=f"media-prepare-{self._guild.id}"
        )
        try:
            await bot.voice_presence.play(voice_client, source)
        except Exception as error:
            log.warning(f"Playback of '{title}' failed: {error}")
        finally:
            ticker.cancel()
            # What it prepared stays for the next song, which takes it if it is still next.
            preparer.cancel()
            listened = self.elapsed()
            finished = duration is None or listened >= duration - END_TOLERANCE_SECONDS
            self.session.append(played)
            self.session_seconds += listened
            self.current = None
            self.now_playing = None
            self.now_playing_duration = None
            self.started_at = None
            self.paused_at = None
            self._after(played, finished)


class MediaCog(commands.Cog, name="Media"):
    """Audio queue supporting YouTube, SoundCloud, and Spotify, with one queue per guild."""

    def __init__(self, bot: BotApp) -> None:
        # Raises ConfigError with the missing variable names, which stops the bot at startup.
        service = bot.config.service("media")
        self.bot = bot
        self.client = MediaAPIClient(base_url=service.url, secret=service.secret)
        self._players: dict[int, GuildPlayer] = {}
        # Typing repeats the same searches, such as after a deleted letter.
        self._suggestions: OrderedDict[
            tuple[str, str], list[app_commands.Choice[str]]
        ] = OrderedDict()
        # The bot's status as last sent, so an unchanged one is not sent again.
        self._status: str | None = None
        # Servers that refused the voice channel status, which are not asked again.
        self._status_refused: set[int] = set()
        # The panel buttons' cooldown of each member, as the commands have.
        self._button_cooldowns: dict[int, app_commands.Cooldown] = {}
        # Handles the buttons of every panel, including those posted before a restart.
        self._panel_buttons = PanelView(self)
        self._played_buttons = PlayedView(self)
        # Closes the panels that the previous run left behind, once the bot is connected.
        self._old_panels: asyncio.Task[None] | None = None
        # The members who left voice and whose waiting songs leave the queue unless they return.
        self._leavers: dict[tuple[int, int], asyncio.Task[None]] = {}

    def player(self, guild: discord.Guild) -> GuildPlayer:
        """Returns the guild's player, creating it on first use."""
        if guild.id not in self._players:
            self._players[guild.id] = GuildPlayer(self, guild)
        return self._players[guild.id]

    async def _dj_role(self, guild_id: int) -> int | None:
        """Returns a guild's DJ role, or None when it has none or the setting cannot be read."""
        try:
            settings = await database.get_settings(guild_id)
        except Exception as error:
            log.warning(f"Could not read the DJ role of guild {guild_id}: {error}")
            return None
        return settings.dj_role_id

    @staticmethod
    def listeners(guild: discord.Guild) -> list[discord.Member]:
        """Returns the members, not bots, in the bot's voice channel."""
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            return []
        return [m for m in voice_client.channel.members if not m.bot]

    async def may_control(
        self, member: discord.Member | discord.User, guild: discord.Guild
    ) -> bool:
        """Whether a member may use the controls that change the music for everyone.

        Without a DJ role, everyone may.
        With one, members with the role, admins who may manage the server, and a lone listener may.
        """
        role_id = await self._dj_role(guild.id)
        if role_id is None or not isinstance(member, discord.Member):
            return role_id is None
        if member.guild_permissions.manage_guild:
            return True
        if any(role.id == role_id for role in member.roles):
            return True
        return [m.id for m in self.listeners(guild)] == [member.id]

    async def _deny(self, interaction: discord.Interaction) -> None:
        """Tells a member privately that only the DJ role may do that, and ends the command."""
        s = self.bot.strings_for(interaction, private=True)
        await respond(interaction, s.dj_only, ephemeral=True)
        await finish(interaction)

    async def _may_change(
        self, interaction: discord.Interaction, player: GuildPlayer, position: int
    ) -> bool:
        """Lets a member change their own queued songs, and others' songs only with control."""
        if 1 <= position <= len(player.queue):
            track = player.queue[position - 1]
            if track.requested_by_id != interaction.user.id and not (
                await self.may_control(interaction.user, guild_of(interaction))
            ):
                await self._deny(interaction)
                return False
        return True

    async def request_skip(
        self, guild: discord.Guild, member: discord.Member | discord.User
    ) -> SkipOutcome:
        """Skips the playing song at once, or counts the member's vote to skip it.

        The song is skipped at once without a DJ role, for members with control, and for its adder.
        It is also skipped at once while at most two members listen.
        Otherwise it is skipped once half of the listeners voted.

        Returns:
            Whether the song should stop now, and how the vote stands.
        """
        player = self._players.get(guild.id)
        current = player.current if player is not None else None
        if player is None or current is None:
            return SkipOutcome(True)
        listeners = self.listeners(guild)
        if (
            len(listeners) <= 2
            or current.requested_by_id == member.id
            or await self.may_control(member, guild)
        ):
            self.note_skip(guild, member.display_name)
            return SkipOutcome(True)
        repeated = member.id in player.skip_votes
        player.skip_votes.add(member.id)
        listening = {m.id for m in listeners}
        votes = len(player.skip_votes & listening)
        needed = ceil(len(listeners) / 2)
        if votes >= needed:
            player.note(
                "skipped_vote",
                member.display_name,
                carries=True,
                title=escape(shorten(current.label, LIST_TITLE_LIMIT)),
            )
            return SkipOutcome(True, votes, needed)
        if not repeated:
            player.note("skipvote", member.display_name, votes=votes, needed=needed)
            await self.refresh_panel(guild)
        return SkipOutcome(False, votes, needed, repeated)

    async def evens_loudness(self, guild_id: int) -> bool:
        """Whether a guild's songs play at an even loudness, which is on when unreadable."""
        try:
            settings = await database.get_settings(guild_id)
        except Exception as error:
            log.warning(
                f"Could not read the loudness setting of guild {guild_id}: {error}"
            )
            return True
        return settings.even_loudness

    async def drops_leavers(self, guild_id: int) -> bool:
        """Whether a guild drops the waiting songs of members who leave voice."""
        try:
            settings = await database.get_settings(guild_id)
        except Exception as error:
            log.warning(
                f"Could not read the leaver setting of guild {guild_id}: {error}"
            )
            return False
        return settings.leave_cleanup

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Gives a member who left the bot's voice channel time to return before their songs go."""
        if member.bot:
            return
        voice_client = member.guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            return
        key = (member.guild.id, member.id)
        if after.channel == voice_client.channel:
            # Back in time, so their songs stay.
            if (pending := self._leavers.pop(key, None)) is not None:
                pending.cancel()
            return
        if before.channel != voice_client.channel or key in self._leavers:
            return
        player = self._players.get(member.guild.id)
        if player is None or not any(
            track.requested_by_id == member.id for track in player.queue
        ):
            return
        if not await self.drops_leavers(member.guild.id):
            return
        self._leavers[key] = asyncio.create_task(
            self._drop_leaver(member),
            name=f"media-leaver-{member.guild.id}-{member.id}",
        )

    async def _drop_leaver(self, member: discord.Member) -> None:
        """Takes a member's waiting songs out of the queue, unless they came back to listen."""
        key = (member.guild.id, member.id)
        try:
            await asyncio.sleep(LEAVER_GRACE_SECONDS)
        finally:
            if self._leavers.get(key) is asyncio.current_task():
                del self._leavers[key]
        voice_client = member.guild.voice_client
        voice = member.voice
        if not isinstance(voice_client, discord.VoiceClient) or (
            voice is not None and voice.channel == voice_client.channel
        ):
            return
        player = self._players.get(member.guild.id)
        removed = player.remove_member(member.id) if player is not None else 0
        if player is None or not removed:
            return
        action = "left_one" if removed == 1 else "left"
        player.note(action, member.display_name, count=removed)
        log.info(f"Removed {removed} waiting song(s) of {member}, who left voice.")
        await self.refresh_panel(member.guild)

    async def takes_turns(self, guild_id: int) -> bool:
        """Whether a guild's queue takes turns between members, which is off when unreadable."""
        try:
            settings = await database.get_settings(guild_id)
        except Exception as error:
            log.warning(f"Could not read the queue order of guild {guild_id}: {error}")
            return False
        return settings.fair_queue

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
    @app_commands.describe(
        query="A YouTube, SoundCloud, or Spotify link, or words to search for.",
        source="Where a search looks. A link plays from its own site.",
        when="When it plays. Leave it out to add it to the end of the queue.",
    )
    @app_commands.choices(source=SEARCH_SOURCES, when=WHEN_CHOICES)
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        source: app_commands.Choice[str] | None = None,
        when: app_commands.Choice[str] | None = None,
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
            await respond(interaction, s.not_in_voice)
            await finish(interaction)
            return
        if interaction.channel is None or not isinstance(
            interaction.channel, discord.abc.Messageable
        ):
            await finish(interaction)
            return

        player = self.player(guild)
        interrupts = when is not None and when.value == "now" and not player.idle
        if interrupts and not await self.may_control(member, guild):
            await self._deny(interaction)
            return
        limit = self.bot.config.max_queue_length
        room = limit - len(player.queue)
        if room <= 0:
            await respond(interaction, s.queue_full, limit=limit)
            await finish(interaction)
            return

        site = source.value if source is not None else "youtube"
        collection: str | None = None
        failure = s.load_error
        try:
            collection, found = await self._resolve(query, site)
        except httpx.HTTPStatusError as error:
            log.warning(f"Could not load '{query}': {error}")
            found = []
            if error.response.status_code == 403 and is_spotify_collection(query):
                failure = s.playlist_unavailable
        except Exception as error:
            log.warning(f"Could not load '{query}': {error}")
            found = []
        if not found:
            await respond(interaction, failure)
            await finish(interaction)
            return
        # Tracks past the limit are left out, and the reply says how many.
        left_out = max(0, len(found) - room)
        found = found[:room]

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
                member.id,
            )
            for info in found
        ]
        idle = player.idle
        # With nothing playing, the first track starts at once whatever when says.
        mode = "end" if idle or when is None else when.value
        waiting = len(player.queue)
        turns = await self.takes_turns(guild.id)
        if mode == "end":
            position = placed = player.enqueue(tracks, turns=turns)
        else:
            position = 1
            # Only the first track jumps ahead, so a playlist never buries the waiting tracks.
            placed = player.enqueue(tracks[1:], turns=turns)
        wait = player.wait_seconds(position)
        if mode != "end":
            voice_client = guild.voice_client
            interrupted = player.current
            if mode == "now" and isinstance(voice_client, discord.VoiceClient):
                if player.play_now(tracks[0], voice_client) and interrupted:
                    player.note(
                        "now",
                        member.display_name,
                        carries=True,
                        title=escape(shorten(interrupted.label, LIST_TITLE_LIMIT)),
                    )
            else:
                player.enqueue(tracks[:1], first=True)
        log.info(f"Queued {len(tracks)} track(s) from {member} in {guild}.")

        values: dict[str, Any] = {
            "user": member.display_name,
            "source": named,
            "position": position,
            "count": len(tracks),
            "more": len(tracks) - 1,
            "title": tracks[0].linked_title,
        }
        playing_now = idle or mode == "now"
        if len(tracks) > 1:
            if playing_now:
                template = s.queued_many_now
            elif mode == "next":
                template = s.queued_many_next
                # The rest start where they were placed, behind the first one.
                values["position"] = placed + 1
            else:
                template = s.queued_many
            # A playlist reply links to the playlist that the member gave, by its name if known.
            if collection:
                values["source"] = s.collection_on.format(
                    collection=link(collection, query), source=named
                )
            else:
                values["source"] = link(named, query)
        elif playing_now:
            template = s.queued_now
        elif wait is not None:
            template = s.queued_one_wait
            values["minutes"] = max(1, round(wait / 60))
        else:
            template = s.queued_one
        if left_out and template and s.queue_cut:
            template = f"{template}\n{s.queue_cut}"
            values.update(left=left_out, limit=limit)
        if turns and placed <= waiting and template and s.queue_turns:
            # The songs went ahead of others' songs, which the member would not expect.
            template = f"{template}\n{s.queue_turns}"
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

    # /play stays a top-level command, the one that members reach for first.
    # The other music commands sit in two groups, so their names say what they act on.
    music = app_commands.Group(
        name="music",
        description="Control the music that plays now.",
        guild_only=True,
        allowed_contexts=app_commands.AppCommandContext(guild=True),
    )
    queue_group = app_commands.Group(
        name="queue",
        description="See and change the songs waiting in the queue.",
        guild_only=True,
        allowed_contexts=app_commands.AppCommandContext(guild=True),
    )

    @music.command(name="stop")
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
        elif not await self.may_control(interaction.user, guild):
            await self._deny(interaction)
            return
        else:
            self.stop_music(guild, interaction.user.display_name)
            await respond(interaction, s.stopped)
        await finish(interaction)

    @music.command(name="pause")
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
        player = self.player(guild)
        paused = player.toggle_pause(voice_client)
        player.note("paused" if paused else "resumed", interaction.user.display_name)
        await respond(interaction, s.paused if paused else s.resumed)
        await finish(interaction)
        await self.refresh_panel(guild)

    @queue_group.command(name="show")
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
        self, player: GuildPlayer, s: CoreStrings, page: int
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

    @queue_group.command(name="remove")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(position="The track's number in /queue show.")
    async def remove(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
        """Remove a track from the queue."""
        s = self.bot.strings_for(interaction)
        player = self.player(guild_of(interaction))
        if not await self._may_change(interaction, player, position):
            return
        track = player.remove(position)
        if track is None:
            await self._queue_reply(interaction, s.queue_no_position, position=position)
        else:
            await self._queue_reply(
                interaction, s.queue_removed, title=track.linked_title
            )

    @queue_group.command(name="move")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(
        position="The track's number in /queue show.", to="The track's new number."
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
        if not await self._may_change(interaction, player, position):
            return
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

    @queue_group.command(name="shuffle")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    async def shuffle(self, interaction: discord.Interaction) -> None:
        """Shuffle the tracks waiting in the queue."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        if not await self.may_control(interaction.user, guild):
            await self._deny(interaction)
            return
        player = self.player(guild)
        count = player.shuffle()
        if count:
            player.note("shuffled", interaction.user.display_name)
        template = s.queue_shuffled if count else s.queue_nothing_waiting
        await self._queue_reply(interaction, template, count=count)

    @queue_group.command(name="clear")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    async def clear(self, interaction: discord.Interaction) -> None:
        """Remove every waiting track. The current track keeps playing."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        if not await self.may_control(interaction.user, guild):
            await self._deny(interaction)
            return
        player = self.player(guild)
        count = player.clear()
        if count:
            player.note("cleared", interaction.user.display_name)
        template = s.queue_cleared if count else s.queue_nothing_waiting
        await self._queue_reply(interaction, template, count=count)

    @queue_group.command(name="skipto")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(position="The track's number in /queue show.")
    async def skip_to(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
        """Skip to a track in the queue, dropping the tracks before it."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        if not await self.may_control(interaction.user, guild):
            await self._deny(interaction)
            return
        player = self.player(guild)
        track = player.skip_to(position)
        if track is None:
            await self._queue_reply(interaction, s.queue_no_position, position=position)
            return
        voice_client = guild.voice_client
        if isinstance(voice_client, discord.VoiceClient) and (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            player.note("skipto", interaction.user.display_name, carries=True)
            # Stopping the current track makes the player start the next one.
            voice_client.stop()
        await self._queue_reply(
            interaction, s.queue_skipping_to, title=track.linked_title
        )

    @music.command(name="volume")
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
        if not await self.may_control(interaction.user, guild):
            await self._deny(interaction)
            return
        await database.upsert_settings(guild.id, music_volume=percent)
        self.player(guild).note("volume", interaction.user.display_name, volume=percent)
        voice_client = guild.voice_client
        if isinstance(voice_client, discord.VoiceClient) and isinstance(
            voice_client.source, discord.PCMVolumeTransformer
        ):
            # The playing track changes at once, and the next tracks read the stored volume.
            voice_client.source.volume = percent / 100
        await self._queue_reply(interaction, s.volume_set, volume=percent)

    @music.command(name="skip")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    async def skip(self, interaction: discord.Interaction) -> None:
        """Skip the song that plays now, or vote to skip it while others listen."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient) or not (
            voice_client.is_playing() or voice_client.is_paused()
        ):
            await respond(interaction, s.nothing_playing)
            await finish(interaction)
            return
        outcome = await self.request_skip(guild, interaction.user)
        if not outcome.skip:
            private = self.bot.strings_for(interaction, private=True)
            text = outcome.vote_text(private)
            await respond(
                interaction, text.replace("{", "{{").replace("}", "}}"), ephemeral=True
            )
            await finish(interaction)
            return
        # Stopping the current song makes the player start the next one.
        voice_client.stop()
        await respond(interaction, s.skipped)
        await finish(interaction)

    @music.command(name="previous")
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
        earlier = self.go_back(player, voice_client, interaction.user.display_name)
        if earlier is None:
            await self._queue_reply(interaction, s.previous_none)
        else:
            await self._queue_reply(
                interaction, s.previous_playing, title=earlier.linked_title
            )

    def go_back(
        self, player: GuildPlayer, voice_client: discord.VoiceClient, user: str
    ) -> Track | None:
        """Plays the song before, for /music previous and the panel.

        Args:
            player: The guild's player.
            voice_client: The bot's voice connection in the guild.
            user: The display name of the member who went back.

        Returns:
            The song that plays now, or None when no song played before.
        """
        if not player.history:
            return None
        earlier = player.history.pop()
        player.note("previous", user, carries=True)
        player.play_now(earlier, voice_client)
        return earlier

    @music.command(name="loop")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(mode="What to repeat.")
    @app_commands.choices(mode=LOOP_MODES)
    async def loop(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        """Repeat the current song or the whole queue."""
        s = self.bot.strings_for(interaction)
        guild = guild_of(interaction)
        if not await self.may_control(interaction.user, guild):
            await self._deny(interaction)
            return
        player = self.player(guild)
        player.loop = mode.value
        player.note("loop", interaction.user.display_name, loop=mode.value)
        template = {"off": s.loop_off, "track": s.loop_track, "queue": s.loop_queue}
        await self._queue_reply(interaction, template[mode.value])

    @music.command(name="lyrics")
    @in_bot_channel()
    @app_commands.checks.cooldown(CONTROL_RATE, CONTROL_PER_SECONDS)
    @app_commands.describe(song="A song to look up. Leave it out for the playing song.")
    async def lyrics(
        self, interaction: discord.Interaction, song: str | None = None
    ) -> None:
        """Show the lyrics of the playing song, or of a song you name."""
        await self.send_lyrics(interaction, song)

    async def send_song(self, interaction: discord.Interaction) -> None:
        """Sends the playing song to the presser's direct messages, or privately if closed."""
        # Thinking makes the press answer with a new private message after the direct message.
        await interaction.response.defer(ephemeral=True, thinking=True)
        s = self.bot.strings_for(interaction, private=True)
        guild = guild_of(interaction)
        player = self._players.get(guild.id)
        track = player.current if player is not None else None
        if track is None:
            await interaction.followup.send(s.grab_nothing, ephemeral=True)
            mark_replied(interaction)
            return
        card = song_card(track, s, guild.name)
        try:
            await interaction.user.send(embed=card)
        except discord.HTTPException:
            # A member who closed direct messages from server members gets the card here.
            await interaction.followup.send(s.grab_closed, embed=card, ephemeral=True)
        else:
            await interaction.followup.send(s.grab_sent, ephemeral=True)
        mark_replied(interaction)

    async def send_lyrics(
        self, interaction: discord.Interaction, song: str | None
    ) -> None:
        """Shows lyrics privately, for /music lyrics and the panel."""
        # Thinking makes a button press answer with a new private message.
        await interaction.response.defer(ephemeral=True, thinking=True)
        s = self.bot.strings_for(interaction, private=True)
        player = self._players.get(guild_of(interaction).id)
        title, duration = song, None
        artist = track = None
        if title is None and player is not None and player.current is not None:
            current = player.current
            title, duration = current.title, current.duration
            # The artist and song name find the right lyrics more often than a site's title.
            artist, track = current.artist, current.song
        if not title:
            await respond(interaction, s.lyrics_nothing, ephemeral=True)
            await finish(interaction)
            return
        try:
            found = await self.client.get_lyrics(title, duration, artist, track)
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
        self.bot.add_view(self._played_buttons)
        self._old_panels = asyncio.create_task(
            self._close_old_panels(), name="media-old-panels"
        )
        log.info(f"{self.qualified_name} cog loaded.")

    async def cog_unload(self) -> None:
        """Stops every player, restores the bot's status, and closes the media API client."""
        self._panel_buttons.stop()
        self._played_buttons.stop()
        if self._old_panels is not None:
            self._old_panels.cancel()
        for player in self._players.values():
            player.cancel()
        for pending in self._leavers.values():
            pending.cancel()
        try:
            await self._set_bot_status(playing=False)
        except Exception as error:
            # The cog unloads either way, so these steps only report what failed.
            log.info(f"Could not reset the status while unloading: {error!r}")
        try:
            await self.client.aclose()
        except Exception as error:
            log.info(f"Could not close the media client while unloading: {error!r}")

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
            "ended": ended_heading(player, s),
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
        lines = song_lines(track, s)
        if state != "ended":
            lines.append(progress_line(player.elapsed(), track.duration))
        if action := self._action_line(player, s, state):
            lines.append(action)
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
        embed.set_footer(
            text=s.panel_footer.format(loop=loop_name(s, player.loop), volume=volume)
        )
        return embed

    def _action_line(self, player: GuildPlayer, s: CoreStrings, state: str) -> str:
        """Says who last changed the music and how, or nothing.

        An ended panel names only a stop, because other changes belong to the songs that played.
        """
        if player.last_action is None:
            return ""
        action, user, values = player.last_action
        if state == "ended" and not stopped(player):
            return ""
        template: str = getattr(s, f"action_{action}", "")
        if "loop" in values:
            values = {**values, "loop": loop_name(s, values["loop"])}
        return template.format(user=escape(user), **values) if template else ""

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
        # The panel is the music's controls, so LOCALE=silent posts it too.
        s = self.bot.strings_for(guild, private=True)
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
        view: PanelView,
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
            await self._record_panel(player.panel)
        except discord.HTTPException as error:
            log.warning(f"Could not update the music panel: {error}")
            player.panel = None

    async def end_panel(self, player: GuildPlayer) -> None:
        """Turns the panel into a record of the last track, without buttons, when the music ends."""
        async with player.panel_lock:
            panel, player.panel = player.panel, None
            if panel is None:
                return
            await self._forget_panel(panel)
            s = self.bot.strings_for(panel.guild, private=True)
            last = player.history[-1] if player.history else None
            songs = list(player.session)
            view: PlayedView | None = None
            try:
                if last is None:
                    await panel.edit(view=None)
                    return
                if len(songs) > 1:
                    embed = self.session_card(player, songs, s)
                    if await self._store_session(panel, songs):
                        view = PlayedView(self, s=s)
                        # The cog's own PlayedView answers the presses on every finished panel.
                        view.stop()
                else:
                    embed = self.panel_embed(player, last, s, state="ended")
                embed.timestamp = discord.utils.utcnow()
                await panel.edit(embed=embed, view=view)
            except discord.HTTPException as error:
                log.info(f"Could not end the music panel: {error}")

    async def _store_session(self, panel: discord.Message, songs: list[Track]) -> bool:
        """Stores a finished session's songs under its panel, for the Played songs button."""
        if panel.guild is None:
            return False
        entries = [
            {
                "title": track.label,
                "url": track.query if is_url(track.query) else None,
                "duration": track.duration,
                "user": track.requested_by,
            }
            for track in songs
        ]
        try:
            await database.save_session(panel.guild.id, panel.id, entries)
        except Exception as error:
            log.warning(f"Could not store the songs of a session: {error!r}")
            return False
        return True

    def session_card(
        self, player: GuildPlayer, songs: list[Track], s: CoreStrings
    ) -> discord.Embed:
        """Sums up a finished session of several songs: how many, how long, and who added them."""
        last = songs[-1]
        embed = discord.Embed(
            title=s.session_title.format(
                count=len(songs), length=session_length(player.session_seconds, s)
            )
        )
        embed.set_author(name=ended_heading(player, s))
        if last.thumbnail:
            embed.set_thumbnail(url=last.thumbnail)
        counts = Counter(track.requested_by for track in songs)
        names = [escape(name) for name, _ in counts.most_common(SESSION_NAMES_SHOWN)]
        if len(counts) > SESSION_NAMES_SHOWN:
            names.append(s.names_others.format(count=len(counts) - SESSION_NAMES_SHOWN))
        lines = [s.session_added_by.format(users=join_names(names, s))]
        origins = Counter(
            (track.collection, track.collection_url, track.source)
            for track in songs
            if track.collection
        )
        if origins:
            (collection, url, source), count = origins.most_common(1)[0]
            if count * 2 > len(songs) and collection:
                name = escape(collection)
                if url:
                    name = f"[{name}]({url})"
                origin = s.collection_on.format(collection=name, source=source or "")
                lines.append(s.session_mostly.format(source=origin))
        title = last.list_line
        if last.song and last.artist:
            title = f"{title} – {escape(last.artist)}"
        lines.append(s.session_last.format(title=title))
        if action := self._action_line(player, s, "ended"):
            lines.append(action)
        embed.description = "\n".join(lines)
        return embed

    async def send_played(self, interaction: discord.Interaction) -> None:
        """Shows the songs of a finished session privately, a page at a time."""
        s = self.bot.strings_for(interaction, private=True)
        message = interaction.message
        try:
            songs = await database.get_session(message.id) if message else None
        except Exception as error:
            log.warning(f"Could not read the songs of a session: {error!r}")
            songs = None
        if not songs:
            await respond(interaction, s.played_gone, ephemeral=True)
            return
        lines = []
        for position, song in enumerate(songs, start=1):
            title = escape(shorten(str(song.get("title") or ""), LIST_TITLE_LIMIT))
            url = song.get("url")
            if url and len(url) <= LIST_URL_LIMIT:
                title = f"[{title}]({url})"
            if song.get("duration"):
                title = f"{title} `{clock(song['duration'])}`"
            user = escape(str(song.get("user") or ""))
            lines.append(s.queue_line.format(position=position, title=title, user=user))
        pages = [
            discord.Embed(
                title=s.played_title,
                description="\n".join(lines[start : start + QUEUE_PAGE_SIZE]),
            )
            for start in range(0, len(lines), QUEUE_PAGE_SIZE)
        ]
        view = PagesView(pages, interaction)
        if len(pages) > 1:
            await interaction.response.send_message(
                embed=view.page(), view=view, ephemeral=True
            )
        else:
            view.stop()
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        mark_replied(interaction)

    def stop_music(self, guild: discord.Guild, user: str) -> None:
        """Stops the playing song and drops the queue, for /music stop and the stop button."""
        voice_client = guild.voice_client
        if not isinstance(voice_client, discord.VoiceClient):
            return
        player = self.player(guild)
        if voice_client.is_playing() or voice_client.is_paused():
            player.note_stop(user)
        player.halt(voice_client)

    def note_skip(self, guild: discord.Guild, user: str) -> None:
        """Records a skip for the panel of the song that the skip starts.

        request_skip calls it for /music skip, the panel's button, and /voice stop alike.
        """
        player = self._players.get(guild.id)
        if player is None:
            return
        title = player.current.label if player.current is not None else ""
        player.note(
            "skipped",
            user,
            carries=True,
            title=escape(shorten(title, LIST_TITLE_LIMIT)),
        )

    async def _record_panel(self, panel: discord.Message) -> None:
        """Records a live panel, so the next start can close it if the bot stops meanwhile."""
        if panel.guild is None:
            return
        try:
            await database.save_panel(panel.guild.id, panel.channel.id, panel.id)
        except Exception as error:
            log.warning(f"Could not record the music panel: {error!r}")

    async def _forget_panel(self, panel: discord.Message) -> None:
        if panel.guild is None:
            return
        try:
            await database.forget_panel(panel.guild.id, panel.id)
        except Exception as error:
            log.warning(f"Could not forget the music panel: {error!r}")

    async def _close_old_panels(self) -> None:
        """Closes the panels that the previous run left playing, which lost their music."""
        await self.bot.wait_until_ready()
        try:
            panels = await database.list_panels()
        except Exception as error:
            log.warning(f"Could not read the music panels: {error!r}")
            return
        for guild_id, channel_id, message_id in panels:
            await self.close_old_panel(guild_id, channel_id, message_id)

    async def close_old_panel(
        self, guild_id: int, channel_id: int, message_id: int
    ) -> None:
        """Turns one panel from before the restart into a record of its song, without buttons."""
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(
                channel_id
            )
            if not isinstance(channel, discord.abc.Messageable):
                return
            message = await channel.fetch_message(message_id)
            s = self.bot.strings_for(message.guild, private=True)
            embeds = [ended_card(embed, s) for embed in message.embeds[:1]]
            await message.edit(embeds=embeds, view=None)
            log.info(f"Closed a music panel that the last run left in {message.guild}.")
        except discord.HTTPException as error:
            # A deleted panel or a channel the bot lost access to needs nothing more.
            log.info(f"Could not close an old music panel: {error}")
        finally:
            try:
                await database.forget_panel(guild_id, message_id)
            except Exception as error:
                log.warning(f"Could not forget the music panel: {error!r}")

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
        """Says whether music plays in any server.

        The status is the same in every server, so it names no song.
        The voice channel's status and the panel name the song where it plays.
        """
        playing = any(p.now_playing for p in self._players.values())
        await self._set_bot_status(playing=playing)

    async def _set_bot_status(self, *, playing: bool) -> None:
        # The status is no reply, so the silent locale still shows it in the bot's language.
        s = self.bot.strings_for(None, private=True)
        text = s.status_playing if playing else s.status_idle
        if text == self._status:
            return
        self._status = text
        try:
            await self.bot.change_presence(activity=custom_status(text))
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
            self.stop_button.label = s.panel_stop or None
            self.queue_button.label = s.panel_queue or None
            self.lyrics_button.label = s.panel_lyrics or None
            self.grab_button.label = s.panel_grab or None

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
        """Returns what the controls act on.

        interaction_check has made sure that the bot is in voice.
        A press acts first and is acknowledged after, with _ack() or _tell().
        Acting before the round trip to Discord makes a pause or a skip heard sooner.
        Never call finish() after a press.
        A press's original response is the panel itself, which finish() would delete.
        """
        guild = guild_of(interaction)
        voice_client = guild.voice_client
        assert isinstance(voice_client, discord.VoiceClient)
        return guild, voice_client, self.cog.player(guild)

    async def _ack(self, interaction: discord.Interaction) -> None:
        """Acknowledges a press that got no message, before the panel shows the result."""
        if not interaction.response.is_done():
            await interaction.response.defer()

    async def _tell(self, interaction: discord.Interaction, text: str) -> None:
        """Answers a press with a message that only the presser sees."""
        if not text:
            await self._ack(interaction)
        elif interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    def _strings(self, interaction: discord.Interaction) -> CoreStrings:
        return self.cog.bot.strings_for(interaction, private=True)

    @discord.ui.button(emoji="🔀", custom_id="media:shuffle", row=0)
    async def shuffle_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Shuffles the waiting songs."""
        guild, _, player = await self._start(interaction)
        if not await self.cog.may_control(interaction.user, guild):
            await self._tell(interaction, self._strings(interaction).dj_only)
            return
        if player.shuffle():
            player.note("shuffled", interaction.user.display_name)
            await self._ack(interaction)
            await self.cog.refresh_panel(guild)
        else:
            text = self._strings(interaction).queue_nothing_waiting
            await self._tell(interaction, text)

    @discord.ui.button(emoji="⏮️", custom_id="media:previous", row=0)
    async def previous_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Goes back to the song before."""
        _, voice_client, player = await self._start(interaction)
        user = interaction.user.display_name
        if self.cog.go_back(player, voice_client, user) is None:
            await self._tell(interaction, self._strings(interaction).previous_none)
        await self._ack(interaction)

    @discord.ui.button(emoji="⏸️", custom_id="media:pause", row=0)
    async def pause_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Pauses or resumes the playing song."""
        guild, voice_client, player = await self._start(interaction)
        if not (voice_client.is_playing() or voice_client.is_paused()):
            await self._tell(interaction, self._strings(interaction).nothing_playing)
            return
        paused = player.toggle_pause(voice_client)
        await self._ack(interaction)
        player.note("paused" if paused else "resumed", interaction.user.display_name)
        await self.cog.refresh_panel(guild)

    @discord.ui.button(emoji="⏭️", custom_id="media:skip", row=0)
    async def skip_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Skips to the next song, or counts a vote to skip it while others listen."""
        guild, voice_client, _ = await self._start(interaction)
        if voice_client.is_playing() or voice_client.is_paused():
            outcome = await self.cog.request_skip(guild, interaction.user)
            if outcome.skip:
                voice_client.stop()
            else:
                await self._tell(
                    interaction, outcome.vote_text(self._strings(interaction))
                )
        else:
            await self._tell(interaction, self._strings(interaction).nothing_playing)
        await self._ack(interaction)

    @discord.ui.button(emoji="🔁", custom_id="media:loop", row=0)
    async def loop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Steps through repeating nothing, the whole queue, and the current song."""
        guild, _, player = await self._start(interaction)
        if not await self.cog.may_control(interaction.user, guild):
            await self._tell(interaction, self._strings(interaction).dj_only)
            return
        player.loop = NEXT_LOOP_MODE[player.loop]
        player.note("loop", interaction.user.display_name, loop=player.loop)
        await self._ack(interaction)
        await self.cog.refresh_panel(guild)

    @discord.ui.button(
        emoji="⏹️", custom_id="media:stop", style=discord.ButtonStyle.danger, row=1
    )
    async def stop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Stops the music, asking first when it would remove waiting songs."""
        guild, voice_client, player = await self._start(interaction)
        if not await self.cog.may_control(interaction.user, guild):
            await self._tell(interaction, self._strings(interaction).dj_only)
            return
        if not player.queue:
            # Nothing waits, so nothing can be lost.
            self.cog.stop_music(guild, interaction.user.display_name)
            await self._ack(interaction)
            return
        s = self._strings(interaction)
        view = StopConfirmView(self.cog, s)
        count = len(player.queue)
        question = s.stop_confirm_one if count == 1 else s.stop_confirm
        await interaction.response.send_message(
            question.format(count=count), view=view, ephemeral=True
        )
        view.message = await interaction.original_response()

    @discord.ui.button(emoji="📜", custom_id="media:queue", row=1)
    async def queue_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Shows the whole queue to the presser."""
        await self.cog.send_queue(interaction)

    @discord.ui.button(emoji="🎤", custom_id="media:lyrics", row=1)
    async def lyrics_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Shows the playing song's lyrics to the presser."""
        await self.cog.send_lyrics(interaction, None)

    @discord.ui.button(emoji="📩", custom_id="media:grab", row=1)
    async def grab_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PanelView]
    ) -> None:
        """Sends the playing song to the presser."""
        await self.cog.send_song(interaction)


class StopConfirmView(discord.ui.View):
    """The private question that the stop button asks before it removes waiting songs.

    Only the member who pressed stop sees it, and the queue stays unless they confirm.
    """

    def __init__(self, cog: MediaCog, s: CoreStrings) -> None:
        super().__init__(timeout=STOP_CONFIRM_TIMEOUT)
        self.cog = cog
        self.s = s
        self.message: discord.Message | None = None
        self.confirm.label = s.stop_confirm_yes or None
        self.cancel.label = s.stop_confirm_no or None

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button[StopConfirmView]
    ) -> None:
        """Stops the music and removes the waiting songs."""
        self.stop()
        self.cog.stop_music(guild_of(interaction), interaction.user.display_name)
        await interaction.response.edit_message(content=self.s.stopped, view=None)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _: discord.ui.Button[StopConfirmView]
    ) -> None:
        """Leaves the music and the queue as they are."""
        self.stop()
        await interaction.response.edit_message(content=self.s.stop_kept, view=None)

    async def on_timeout(self) -> None:
        """Removes the buttons of an unanswered question, which then changes nothing."""
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(content=self.s.stop_kept, view=None)


class PlayedView(discord.ui.View):
    """The Played songs button of a finished session's panel.

    Like PanelView, the cog keeps one instance that answers the presses on every finished panel.
    The songs come from the database, so the button works after a restart too.
    """

    def __init__(self, cog: MediaCog, *, s: CoreStrings | None = None) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        if s is not None:
            self.played_button.label = s.panel_played or None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Lets a member press within the cooldown that the other buttons have."""
        retry_after = self.cog.button_retry_after(interaction.user.id)
        if retry_after is None:
            return True
        s = self.cog.bot.strings_for(interaction, private=True)
        await interaction.response.send_message(
            s.cooldown.format(seconds=ceil(retry_after)), ephemeral=True
        )
        return False

    @discord.ui.button(emoji="📜", custom_id="media:played")
    async def played_button(
        self, interaction: discord.Interaction, _: discord.ui.Button[PlayedView]
    ) -> None:
        """Lists the session's songs to the presser."""
        await self.cog.send_played(interaction)


class PagesView(discord.ui.View):
    """The page buttons of a private reply whose pages are fixed, such as a session's songs."""

    def __init__(
        self, pages: list[discord.Embed], interaction: discord.Interaction
    ) -> None:
        super().__init__(timeout=QUEUE_VIEW_TIMEOUT)
        self.pages = pages
        self.interaction = interaction
        self.index = 0

    def page(self) -> discord.Embed:
        """Returns the current page, and enables only the buttons that lead to another page."""
        self.back.disabled = self.index == 0
        self.forward.disabled = self.index >= len(self.pages) - 1
        embed = self.pages[self.index].copy()
        embed.set_footer(text=f"{self.index + 1}/{len(self.pages)}")
        return embed

    @discord.ui.button(emoji="◀️")
    async def back(
        self, interaction: discord.Interaction, _: discord.ui.Button[PagesView]
    ) -> None:
        """Shows the page before."""
        self.index = max(0, self.index - 1)
        await interaction.response.edit_message(embed=self.page(), view=self)

    @discord.ui.button(emoji="▶️")
    async def forward(
        self, interaction: discord.Interaction, _: discord.ui.Button[PagesView]
    ) -> None:
        """Shows the next page."""
        self.index = min(len(self.pages) - 1, self.index + 1)
        await interaction.response.edit_message(embed=self.page(), view=self)

    async def on_timeout(self) -> None:
        """Removes the buttons, which stop working now."""
        with contextlib.suppress(discord.HTTPException):
            await self.interaction.edit_original_response(view=None)


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
        self, interaction: discord.Interaction, _: discord.ui.Button[QueueView]
    ) -> None:
        """Shows the page before."""
        self.page -= 1
        await interaction.response.edit_message(embed=self.page_embed(), view=self)

    @discord.ui.button(emoji="▶️")
    async def next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button[QueueView]
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


async def setup(bot: BotApp) -> None:
    """Adds the cog. discord.py calls this when the extension loads."""
    await bot.add_cog(MediaCog(bot))
