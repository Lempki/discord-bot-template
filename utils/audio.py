"""Audio sources and the client for api-media."""

import asyncio
import io
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import discord
import httpx

__all__ = [
    "BufferedSource",
    "MediaAPIClient",
    "bytes_source",
    "file_source",
    "is_spotify_collection",
    "is_url",
    "is_youtube_playlist",
    "prime",
    "source_name",
    "stream_source",
]

log = logging.getLogger(__name__)

# One 20 ms frame of 48 kHz 16-bit stereo PCM, which the voice player sends at a time.
FRAME_BYTES = discord.opus.Encoder.FRAME_SIZE
SILENCE = b"\0" * FRAME_BYTES

# A stream starts playing once this many frames wait, 2 seconds of audio.
PRIME_FRAMES = 100

# A stream reads ahead this many frames, 10 seconds of audio, to ride out network stalls.
BUFFER_FRAMES = 500

# A stream that has no audio after this many seconds starts anyway, and ends if it stays empty.
PRIME_TIMEOUT_SECONDS = 30.0

# A stall shorter than this is normal jitter and goes unlogged.
STALL_LOG_SECONDS = 0.5

# The sites that messages name, by the domain of a link.
_SOURCE_NAMES = (
    ("youtube.com", "YouTube"),
    ("youtu.be", "YouTube"),
    ("soundcloud.com", "SoundCloud"),
    ("spotify.com", "Spotify"),
)

# Reconnect options keep long streams alive when the remote host briefly drops the connection.
_STREAM_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MediaAPIClient:
    """HTTP client for api-media.

    Args:
        base_url: The service's base URL.
        secret: The bearer token the service expects.
    """

    def __init__(self, base_url: str, secret: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=120.0,
        )

    def audio_source(
        self, track_url: str, ffmpeg: str, volume: float = 0.5
    ) -> discord.AudioSource:
        """Returns an audio source that plays a track through api-media's /media/stream.

        api-media downloads the audio with yt-dlp, which survives YouTube resetting connections.
        A direct stream URL held open for a whole track does not.
        The FFmpeg reconnect options are left out on purpose.
        A reconnect would make api-media start the track again from the beginning.

        Args:
            track_url: The track's page URL, the webpage_url that get_info() returns.
            ffmpeg: The FFmpeg executable.
            volume: The playback volume, where 1.0 is unchanged.

        Returns:
            A volume-adjusted audio source.
        """
        url = f"{self._base_url}/media/stream?{urlencode({'url': track_url})}"
        # FFmpeg takes extra request headers as one string in which each line ends in CRLF.
        headers = f"Authorization: Bearer {self._secret}\r\n"
        source = discord.FFmpegPCMAudio(
            url,
            executable=ffmpeg,
            before_options=f'-headers "{headers}"',
            options="-vn",
        )
        # The volume wraps the buffer, so a volume change is heard at once.
        return discord.PCMVolumeTransformer(BufferedSource(source), volume=volume)

    async def get_info(
        self,
        url: str | None = None,
        query: str | None = None,
        source: str = "youtube",
    ) -> dict[str, Any]:
        """Resolves a URL or search query to track metadata, including a fresh stream_url.

        Args:
            url: A track's link.
            query: Words to search for, used when url is None.
            source: The site that a search looks on, youtube or soundcloud.
        """
        params = {
            key: value for key, value in (("url", url), ("query", query)) if value
        }
        if query and not url:
            params["source"] = source
        response = await self._http.get("/media/info", params=params)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def search(
        self, query: str, source: str, max_results: int
    ) -> list[dict[str, Any]]:
        """Returns the first search results on a site, without stream URLs.

        Args:
            query: The words to search for.
            source: The site, youtube or soundcloud.
            max_results: How many results to return at most.
        """
        response = await self._http.post(
            "/media/search",
            json={"query": query, "source": source, "max_results": max_results},
        )
        response.raise_for_status()
        results: list[dict[str, Any]] = response.json().get("results", [])
        return results

    async def get_lyrics(self, title: str, duration: int | None) -> dict[str, Any]:
        """Looks up a song's lyrics through api-media, which asks LRCLIB.

        Args:
            title: The song's title, such as a YouTube title with the artist first.
            duration: The song's length in seconds, which picks the right recording.

        Raises:
            httpx.HTTPStatusError: With status 404 when no lyrics were found.
        """
        params: dict[str, str | int] = {"title": title}
        if duration:
            params["duration"] = duration
        response = await self._http.get("/media/lyrics", params=params)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def get_playlist(self, url: str) -> tuple[str | None, list[dict[str, Any]]]:
        """Expands a YouTube playlist or a Spotify album or playlist into its tracks.

        Returns:
            The playlist's or album's name, when the site gives one, and its tracks.
        """
        response = await self._http.get("/media/playlist", params={"url": url})
        response.raise_for_status()
        data = response.json()
        tracks: list[dict[str, Any]] = data.get("tracks", [])
        return data.get("title") or None, tracks

    async def aclose(self) -> None:
        """Closes the underlying HTTP connection pool."""
        await self._http.aclose()


def is_url(text: str) -> bool:
    """Returns whether text is an HTTP or HTTPS URL rather than a search query."""
    return text.startswith(("http://", "https://"))


def source_name(query: str) -> str:
    """Names the site that a link comes from, for messages. Search text goes to YouTube."""
    if not is_url(query):
        return "YouTube"
    host = (urlsplit(query).hostname or "").removeprefix("www.")
    for domain, name in _SOURCE_NAMES:
        if host == domain or host.endswith(f".{domain}"):
            return name
    return host


def is_spotify_collection(url: str) -> bool:
    """Returns whether a URL points to a Spotify album or playlist."""
    return "spotify.com" in url and ("/album/" in url or "/playlist/" in url)


def is_youtube_playlist(url: str) -> bool:
    """Returns whether a URL points to a YouTube playlist."""
    return ("youtube.com" in url or "youtu.be" in url) and "list=" in url


def file_source(path: Path | str, ffmpeg: str) -> discord.AudioSource:
    """Returns an audio source for a local file."""
    return discord.FFmpegPCMAudio(str(path), executable=ffmpeg)


def bytes_source(data: bytes, ffmpeg: str) -> discord.AudioSource:
    """Returns an audio source for audio held in memory, such as a generated WAV file."""
    return discord.FFmpegPCMAudio(io.BytesIO(data), executable=ffmpeg, pipe=True)


def stream_source(url: str, ffmpeg: str, volume: float = 0.5) -> discord.AudioSource:
    """Returns a volume-adjusted, buffered audio source for a remote stream URL."""
    source = discord.FFmpegPCMAudio(url, executable=ffmpeg, **_STREAM_OPTIONS)
    return discord.PCMVolumeTransformer(BufferedSource(source), volume=volume)


class BufferedSource(discord.AudioSource):
    """Reads a streamed source ahead in a thread, so the voice player never waits on it.

    discord.py's player sends a 20 ms frame on a fixed clock that starts before its first read.
    A read that blocks, as while a stream starts or the network stalls, puts the player behind.
    It then sends the late frames back to back, and Discord's apps play that burst faster.
    Listeners hear the song speed up, most often at its start.

    This source fills a buffer from its own thread instead.
    prime() waits until the buffer holds a moment of audio, so the player's clock starts on time.
    When the buffer runs dry anyway, read() returns silence rather than blocking.
    A long stall then pauses the song instead of rushing it afterwards.

    Args:
        source: The PCM source to read ahead, such as an FFmpegPCMAudio of a stream.
        prime_frames: How many frames make the source ready to play.
        buffer_frames: How many frames the thread reads ahead at most.
    """

    def __init__(
        self,
        source: discord.AudioSource,
        *,
        prime_frames: int = PRIME_FRAMES,
        buffer_frames: int = BUFFER_FRAMES,
    ) -> None:
        self._source = source
        self._frames: queue.Queue[bytes] = queue.Queue(maxsize=buffer_frames)
        self._prime_frames = min(prime_frames, buffer_frames)
        self._ready = threading.Event()
        self._finished = threading.Event()
        self._closed = threading.Event()
        self._stalled_at: float | None = None
        self._thread = threading.Thread(
            target=self._fill, name="audio-read-ahead", daemon=True
        )
        self._thread.start()

    def _fill(self) -> None:
        try:
            while not self._closed.is_set():
                frame = self._source.read()
                if not frame:
                    break
                while not self._closed.is_set():
                    try:
                        # A full buffer, such as during a pause, waits for the player.
                        self._frames.put(frame, timeout=0.5)
                        break
                    except queue.Full:
                        continue
                if self._frames.qsize() >= self._prime_frames:
                    self._ready.set()
        except Exception as error:
            log.warning(f"Reading the audio stream failed: {error!r}")
        finally:
            self._finished.set()
            self._ready.set()

    def wait_until_ready(self, timeout: float = PRIME_TIMEOUT_SECONDS) -> bool:
        """Blocks until a moment of audio waits or the stream ended, and says which came first."""
        return self._ready.wait(timeout)

    def read(self) -> bytes:
        """Returns the next frame, silence while the stream stalls, or nothing once it ended."""
        try:
            frame = self._frames.get_nowait()
        except queue.Empty:
            if self._finished.is_set():
                return b""
            if self._stalled_at is None:
                self._stalled_at = time.monotonic()
            return SILENCE
        if self._stalled_at is not None:
            stalled = time.monotonic() - self._stalled_at
            self._stalled_at = None
            if stalled >= STALL_LOG_SECONDS:
                log.info(
                    f"The audio stream stalled for {stalled:.1f} s and played silence."
                )
        return frame

    def is_opus(self) -> bool:
        """Says that the frames are PCM, which the player encodes."""
        return False

    def cleanup(self) -> None:
        """Stops reading ahead and closes the inner source, such as its FFmpeg process."""
        self._closed.set()
        self._source.cleanup()


async def prime(source: discord.AudioSource) -> None:
    """Waits until a buffered source, or the one that a volume control wraps, can play.

    Call it before playing, so that the player's clock starts once audio waits.
    Other sources start at once.
    """
    inner = getattr(source, "original", source)
    if isinstance(inner, BufferedSource):
        await asyncio.to_thread(inner.wait_until_ready)
