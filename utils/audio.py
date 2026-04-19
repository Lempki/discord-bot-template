import asyncio

import discord
import httpx


class MediaAPIClient:
    """HTTP client for discord-api-media."""

    def __init__(self, base_url: str, secret: str):
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=120.0,
        )

    async def get_info(self, url: str | None = None, query: str | None = None) -> dict:
        """Resolve a URL or search query to full track metadata including stream_url."""
        params: dict[str, str] = {}
        if url:
            params["url"] = url
        if query:
            params["query"] = query
        resp = await self._http.get("/media/info", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_playlist(self, url: str) -> list[dict]:
        """Expand a YouTube playlist or Spotify album/playlist into a list of tracks."""
        resp = await self._http.get("/media/playlist", params={"url": url})
        resp.raise_for_status()
        return resp.json().get("tracks", [])

    async def aclose(self) -> None:
        await self._http.aclose()


def is_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


def is_spotify_collection(url: str) -> bool:
    return "spotify.com" in url and ("/album/" in url or "/playlist/" in url)


def is_youtube_playlist(url: str) -> bool:
    return ("youtube.com" in url or "youtu.be" in url) and "list=" in url


async def play_file(
    voice_client: discord.VoiceClient,
    file_path: str,
    ffmpeg_executable: str = "ffmpeg",
) -> None:
    source = discord.FFmpegPCMAudio(source=file_path, executable=ffmpeg_executable)
    voice_client.play(source)
    while voice_client.is_playing():
        await asyncio.sleep(1)
