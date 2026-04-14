import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from utils.audio import YouTubeDLSource, resolve_urls
from utils.checks import in_bot_channel
from utils.logging import log


class YouTubeCog(commands.Cog, name="YouTube"):
    """YouTube audio queue. Supports concurrent queues across multiple guilds."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._queues: dict[int, asyncio.Queue] = {}
        self._playing: dict[int, bool] = {}

    def _queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self._queues:
            self._queues[guild_id] = asyncio.Queue()
        return self._queues[guild_id]

    def _ffmpeg(self) -> str:
        return self.bot.config.FFMPEG_PATH or "ffmpeg"

    async def _say(self, interaction: discord.Interaction, template: str, **kwargs) -> None:
        if not (msg := template.format(**kwargs)):
            return
        if interaction.response.is_done():
            await interaction.followup.send(msg)
        else:
            await interaction.response.send_message(msg)

    @app_commands.command(name="play")
    @in_bot_channel()
    async def play(self, interaction: discord.Interaction, url: str):
        """Add a YouTube URL or playlist to the queue and start playback if idle."""
        await interaction.response.defer()
        s = self.bot.strings
        guild_id = interaction.guild_id

        urls = await resolve_urls(url, loop=asyncio.get_running_loop())
        for u in urls:
            await self._queue(guild_id).put((interaction, u))

        if len(urls) > 1:
            await self._say(interaction, s.queued_many, count=len(urls), user=interaction.user)
        else:
            await self._say(interaction, s.queued_one, user=interaction.user)
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
            player = await YouTubeDLSource.from_url(
                url,
                loop=asyncio.get_running_loop(),
                stream=True,
                ffmpeg_executable=self._ffmpeg(),
            )
        except Exception as e:
            log(f"Error loading '{url}': {e}")
            await self._say(interaction, s.load_error, user=interaction.user)
            await self._process_queue(guild_id)
            return

        self._playing[guild_id] = True
        vc.play(player)
        await self._say(interaction, s.now_playing, title=player.title, channel=vc.channel)
        log(f"Playing '{player.title}'")

        while vc.is_playing():
            await asyncio.sleep(1)

        self._playing[guild_id] = False
        await self._process_queue(guild_id)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "This command can only be used in the designated bot channel.",
                    ephemeral=True,
                )
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeCog(bot))
