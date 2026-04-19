import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from utils.audio import MediaAPIClient, is_spotify_collection, is_url, is_youtube_playlist
from utils.checks import in_bot_channel
from utils.logging import log

_FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MediaCog(commands.Cog, name="Media"):
    """Audio queue supporting YouTube and Spotify. Concurrent queues per guild."""

    def __init__(self, bot: commands.Bot):
        if not bot.config.DISCORD_API_MEDIA_URL or not bot.config.DISCORD_API_MEDIA_SECRET:
            raise RuntimeError(
                "DISCORD_API_MEDIA_URL and DISCORD_API_MEDIA_SECRET must be set to use the media cog."
            )
        self.bot = bot
        self._queues: dict[int, asyncio.Queue] = {}
        self._playing: dict[int, bool] = {}
        self._client = MediaAPIClient(
            base_url=bot.config.DISCORD_API_MEDIA_URL,
            secret=bot.config.DISCORD_API_MEDIA_SECRET,
        )

    def _queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self._queues:
            self._queues[guild_id] = asyncio.Queue()
        return self._queues[guild_id]

    def _ffmpeg(self) -> str:
        return self.bot.config.FFMPEG_PATH or "ffmpeg"

    async def _say(self, interaction: discord.Interaction, template: str, **kwargs) -> bool:
        """Format and send *template*. Returns True if a message was sent."""
        if not (msg := template.format(**kwargs)):
            return False
        if interaction.response.is_done():
            await interaction.followup.send(msg)
        else:
            await interaction.response.send_message(msg)
        return True

    @app_commands.command(name="play")
    @in_bot_channel()
    async def play(self, interaction: discord.Interaction, url: str):
        """Add a URL or search query to the queue and start playback if idle.

        Accepts YouTube video URLs, YouTube playlist URLs, Spotify track URLs,
        Spotify album URLs, Spotify playlist URLs, and plain search queries.
        """
        await interaction.response.defer()
        s = self.bot.strings
        guild_id = interaction.guild_id

        vc = interaction.guild.voice_client
        if vc is None and interaction.user.voice is None:
            if not await self._say(interaction, s.not_in_voice, user=interaction.user):
                await interaction.delete_original_response()
            return

        try:
            if is_spotify_collection(url) or is_youtube_playlist(url):
                tracks = await self._client.get_playlist(url)
                urls = [t["webpage_url"] for t in tracks if t.get("webpage_url")]
            else:
                urls = [url]
        except Exception as e:
            log(f"Error resolving '{url}': {e}")
            if not await self._say(interaction, s.load_error, user=interaction.user):
                await interaction.delete_original_response()
            return

        for u in urls:
            await self._queue(guild_id).put((interaction, u))

        if len(urls) > 1:
            sent = await self._say(interaction, s.queued_many, count=len(urls), user=interaction.user)
        else:
            sent = await self._say(interaction, s.queued_one, user=interaction.user)
        if not sent:
            await interaction.delete_original_response()

        log(f"Queued {len(urls)} item(s) from {interaction.user}")

        if not self._playing.get(guild_id):
            await self._process_queue(guild_id)

    async def _process_queue(self, guild_id: int):
        q = self._queue(guild_id)
        if q.empty():
            self._playing[guild_id] = False
            return

        interaction, url = await q.get()
        s = self.bot.strings
        vc = interaction.guild.voice_client

        if vc is None:
            if interaction.user.voice:
                vc = await interaction.user.voice.channel.connect()
            else:
                await self._say(interaction, s.not_in_voice, user=interaction.user)
                await self._process_queue(guild_id)
                return

        try:
            if is_url(url):
                info = await self._client.get_info(url=url)
            else:
                info = await self._client.get_info(query=url)
            stream_url = info["stream_url"]
            title = info.get("title", url)
        except Exception as e:
            log(f"Error loading '{url}': {e}")
            await self._say(interaction, s.load_error, user=interaction.user)
            await self._process_queue(guild_id)
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, executable=self._ffmpeg(), **_FFMPEG_OPTIONS),
            volume=0.5,
        )

        self._playing[guild_id] = True
        vc.play(source)
        await self._say(interaction, s.now_playing, title=title, channel=vc.channel)
        log(f"Playing '{title}'")

        while vc.is_playing() or vc.is_paused():
            await asyncio.sleep(1)

        self._playing[guild_id] = False
        await self._process_queue(guild_id)

    @app_commands.command(name="stop")
    @in_bot_channel()
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and clear the queue."""
        await interaction.response.defer()
        s = self.bot.strings
        guild_id = interaction.guild_id
        vc = interaction.guild.voice_client
        if vc is None or (not vc.is_playing() and not vc.is_paused()):
            if not await self._say(interaction, s.nothing_to_skip):
                await interaction.delete_original_response()
            return
        q = self._queue(guild_id)
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
        vc.stop()
        if not await self._say(interaction, s.stopped):
            await interaction.delete_original_response()

    @app_commands.command(name="pause")
    @in_bot_channel()
    async def pause(self, interaction: discord.Interaction):
        """Pause or resume the current audio."""
        await interaction.response.defer()
        s = self.bot.strings
        vc = interaction.guild.voice_client
        if vc is None or (not vc.is_playing() and not vc.is_paused()):
            if not await self._say(interaction, s.nothing_to_skip):
                await interaction.delete_original_response()
            return
        if vc.is_paused():
            vc.resume()
            if not await self._say(interaction, s.resumed):
                await interaction.delete_original_response()
        else:
            vc.pause()
            if not await self._say(interaction, s.paused):
                await interaction.delete_original_response()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                if msg := self.bot.strings.bot_channel_only:
                    await interaction.response.send_message(msg, ephemeral=True)
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(MediaCog(bot))
