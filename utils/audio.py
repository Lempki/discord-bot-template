"""Audio sources and the client for discord-api-media."""

import io
from pathlib import Path
from typing import Any

import discord
import httpx

__all__ = [
    "MediaAPIClient",
    "bytes_source",
    "file_source",
    "is_spotify_collection",
    "is_url",
    "is_youtube_playlist",
    "stream_source",
]

# Reconnect options keep long streams alive when the remote host briefly drops the connection.
_STREAM_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MediaAPIClient:
    """HTTP client for discord-api-media.

    Args:
        base_url: The service's base URL.
        secret: The bearer token the service expects.
    """

    def __init__(self, base_url: str, secret: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=120.0,
        )

    async def get_info(
        self, url: str | None = None, query: str | None = None
    ) -> dict[str, Any]:
        """Resolves a URL or search query to track metadata, including a fresh stream_url."""
        params = {
            key: value for key, value in (("url", url), ("query", query)) if value
        }
        response = await self._http.get("/media/info", params=params)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def get_playlist(self, url: str) -> list[dict[str, Any]]:
        """Expands a YouTube playlist or a Spotify album or playlist into its tracks."""
        response = await self._http.get("/media/playlist", params={"url": url})
        response.raise_for_status()
        tracks: list[dict[str, Any]] = response.json().get("tracks", [])
        return tracks

    async def aclose(self) -> None:
        """Closes the underlying HTTP connection pool."""
        await self._http.aclose()


def is_url(text: str) -> bool:
    """Returns whether text is an HTTP or HTTPS URL rather than a search query."""
    return text.startswith(("http://", "https://"))


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
