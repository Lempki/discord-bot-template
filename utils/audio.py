import asyncio
import discord
import yt_dlp


YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": "%(id)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,   # only used in from_url (per-item extraction)
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

# Used only for the initial URL resolution step — fast flat extraction, no download.
_YTDL_FLAT_OPTIONS = {
    **YTDL_OPTIONS,
    "extract_flat": "in_playlist",
    "noplaylist": False,  # allow playlists at this stage
}

FFMPEG_STREAM_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class YouTubeDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.FFmpegAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        stream: bool = True,
        ffmpeg_executable: str = "ffmpeg",
    ) -> "YouTubeDLSource":
        loop = loop or asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            data = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=not stream)
            )
        if "entries" in data:
            data = data["entries"][0]
        file = data["url"] if stream else yt_dlp.YoutubeDL.prepare_filename(data)
        source = discord.FFmpegPCMAudio(
            file, executable=ffmpeg_executable, **FFMPEG_STREAM_OPTIONS
        )
        return cls(source, data=data)


async def resolve_urls(
    url: str,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list[str]:
    """Resolve a URL to one or more streamable video URLs.

    For a single video: returns ``[url]`` unchanged.
    For a playlist: returns one URL per entry in playlist order.
    Uses flat extraction so large playlists resolve quickly.
    """
    loop = loop or asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(_YTDL_FLAT_OPTIONS) as ydl:
        data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))

    entries = data.get("entries")
    if not entries:
        return [url]

    urls = []
    for entry in entries:
        vid_url = entry.get("webpage_url") or entry.get("url")
        if not vid_url and entry.get("id"):
            vid_url = f"https://www.youtube.com/watch?v={entry['id']}"
        if vid_url:
            urls.append(vid_url)
    return urls or [url]


async def play_file(
    voice_client: discord.VoiceClient,
    file_path: str,
    ffmpeg_executable: str = "ffmpeg",
) -> None:
    source = discord.FFmpegPCMAudio(source=file_path, executable=ffmpeg_executable)
    voice_client.play(source)
    while voice_client.is_playing():
        await asyncio.sleep(1)
