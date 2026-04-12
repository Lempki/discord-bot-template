import asyncio
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

    def _reply_channel(self, ctx: commands.Context):
        ch_id = self.bot.config.BOT_CHANNEL_ID
        return self.bot.get_channel(ch_id) if ch_id else ctx.channel

    def _ffmpeg(self) -> str:
        return self.bot.config.FFMPEG_PATH or "ffmpeg"

    async def _say(self, ctx: commands.Context, template: str, **kwargs) -> None:
        if msg := template.format(**kwargs):
            await self._reply_channel(ctx).send(msg)

    @commands.command(name="play", aliases=["youtube", "yt"])
    @in_bot_channel()
    async def play(self, ctx: commands.Context, *, url: str):
        """Add a YouTube URL or playlist to the queue and start playback if idle."""
        s = self.bot.strings
        guild_id = ctx.guild.id

        urls = await resolve_urls(url, loop=self.bot.loop)
        for u in urls:
            await self._queue(guild_id).put((ctx, u))

        if len(urls) > 1:
            await self._say(ctx, s.queued_many, count=len(urls), user=ctx.author)
        else:
            await self._say(ctx, s.queued_one, user=ctx.author)
        log(f"Queued {len(urls)} item(s) from {ctx.author}")

        if not self._playing.get(guild_id):
            await self._process_queue(guild_id)

    async def _process_queue(self, guild_id: int):
        q = self._queue(guild_id)
        if q.empty():
            self._playing[guild_id] = False
            return

        ctx, url = await q.get()
        s = self.bot.strings
        vc = ctx.voice_client

        if vc is None:
            if ctx.author.voice:
                vc = await ctx.author.voice.channel.connect()
            else:
                await self._say(ctx, s.not_in_voice, user=ctx.author)
                await self._process_queue(guild_id)
                return

        try:
            player = await YouTubeDLSource.from_url(
                url,
                loop=self.bot.loop,
                stream=True,
                ffmpeg_executable=self._ffmpeg(),
            )
        except Exception as e:
            log(f"Error loading '{url}': {e}")
            await self._say(ctx, s.load_error, user=ctx.author)
            await self._process_queue(guild_id)
            return

        self._playing[guild_id] = True
        vc.play(player)
        await self._say(ctx, s.now_playing, title=player.title, channel=vc.channel)
        log(f"Playing '{player.title}'")

        while vc.is_playing():
            await asyncio.sleep(1)

        self._playing[guild_id] = False
        await self._process_queue(guild_id)

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await self._say(ctx, self.bot.strings.play_usage, prefix=self.bot.config.COMMAND_PREFIX)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeCog(bot))
