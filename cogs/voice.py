from discord.ext import commands
from utils.checks import in_bot_channel


class VoiceCog(commands.Cog, name="Voice"):
    """Voice channel management: join, leave, skip."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _ffmpeg(self) -> str:
        return self.bot.config.FFMPEG_PATH or "ffmpeg"

    def _reply_channel(self, ctx: commands.Context):
        ch_id = self.bot.config.BOT_CHANNEL_ID
        return self.bot.get_channel(ch_id) if ch_id else ctx.channel

    @commands.command(name="join", aliases=["connect"])
    @in_bot_channel()
    async def join(self, ctx: commands.Context):
        """Join the voice channel you are currently in."""
        if ctx.author.voice is None:
            await self._reply_channel(ctx).send("You are not in a voice channel.")
            return
        target = ctx.author.voice.channel
        vc = ctx.voice_client
        if vc:
            await vc.move_to(target)
        else:
            await target.connect()
        await self._reply_channel(ctx).send(f"Joined `{target}`.")

    @commands.command(name="leave", aliases=["disconnect"])
    @in_bot_channel()
    async def leave(self, ctx: commands.Context):
        """Leave the current voice channel and stop audio."""
        vc = ctx.voice_client
        if vc is None:
            await self._reply_channel(ctx).send("Not in a voice channel.")
            return
        channel_name = vc.channel
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await self._reply_channel(ctx).send(f"Left `{channel_name}`.")

    @commands.command(name="skip")
    @in_bot_channel()
    async def skip(self, ctx: commands.Context):
        """Skip the currently playing audio."""
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await self._reply_channel(ctx).send("Skipped.")
        else:
            await self._reply_channel(ctx).send("Nothing to skip.")

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            return  # silently ignore wrong-channel usage
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
