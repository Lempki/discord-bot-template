"""Audio sources and the client for api-media."""

import io
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import discord
import httpx

__all__ = [
    "MediaAPIClient",
    "bytes_source",
    "file_source",
    "is_spotify_collection",
    "is_url",
    "is_youtube_playlist",
    "source_name",
    "stream_source",
]

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
        return discord.PCMVolumeTransformer(source, volume=volume)

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
    """Returns a volume-adjusted audio source for a remote stream URL."""
    return discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(url, executable=ffmpeg, **_STREAM_OPTIONS), volume=volume
    )
