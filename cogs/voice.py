from discord.ext import commands
from utils.checks import in_bot_channel


class VoiceCog(commands.Cog, name="Voice"):
    """Voice channel management: join, leave, skip."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _reply_channel(self, ctx: commands.Context):
        ch_id = self.bot.config.BOT_CHANNEL_ID
        return self.bot.get_channel(ch_id) if ch_id else ctx.channel

    async def _say(self, ctx: commands.Context, template: str, **kwargs) -> None:
        if not (msg := template.format(**kwargs)):
            return
        if ctx.interaction:
            await ctx.send(msg)
        else:
            await self._reply_channel(ctx).send(msg)

    @commands.hybrid_command(name="join", aliases=["connect"])
    @in_bot_channel()
    async def join(self, ctx: commands.Context):
        """Join the voice channel you are currently in."""
        s = self.bot.strings
        if ctx.author.voice is None:
            await self._say(ctx, s.not_in_voice, user=ctx.author)
            return
        target = ctx.author.voice.channel
        vc = ctx.voice_client
        if vc:
            await vc.move_to(target)
            await self._say(ctx, s.moved_voice, channel=target)
        else:
            await target.connect()
            await self._say(ctx, s.joined_voice, channel=target)

    @commands.hybrid_command(name="leave", aliases=["disconnect"])
    @in_bot_channel()
    async def leave(self, ctx: commands.Context):
        """Leave the current voice channel and stop audio."""
        s = self.bot.strings
        vc = ctx.voice_client
        if vc is None:
            await self._say(ctx, s.bot_not_in_voice)
            return
        channel = vc.channel
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await self._say(ctx, s.left_voice, channel=channel)

    @commands.hybrid_command(name="skip")
    @in_bot_channel()
    async def skip(self, ctx: commands.Context):
        """Skip the currently playing audio."""
        s = self.bot.strings
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await self._say(ctx, s.skipped)
        else:
            await self._say(ctx, s.nothing_to_skip)

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(
                    "This command can only be used in the designated bot channel.",
                    ephemeral=True,
                )
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
