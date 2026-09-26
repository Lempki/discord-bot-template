"""Tests for the media cog's per-guild player, with the service and voice faked out."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot import BotApp
from cogs.media import GuildPlayer, MediaCog, Track
from config import Config, ServiceConfig
from localization import LOCALES

EN = LOCALES["en"]


@pytest.fixture(autouse=True)
def no_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replaces real FFmpeg sources, which would start an ffmpeg process per track."""
    monkeypatch.setattr("cogs.media.stream_source", lambda url, ffmpeg: MagicMock())


async def media_cog() -> tuple[BotApp, MediaCog]:
    """A media cog whose service client is replaced by a mock."""
    bot = media_bot()
    cog = MediaCog(bot)
    await cog.client.aclose()
    cog.client = MagicMock()
    return bot, cog


def media_bot() -> BotApp:
    config = Config(
        discord_token="t",
        locale="en",
        services={"media": ServiceConfig("http://media.test", "secret")},
    )
    return BotApp(config)


def connected_guild() -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.preferred_locale = discord.Locale.american_english
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.is_connected.return_value = True
    voice_client.channel = MagicMock()
    voice_client.channel.name = "General"
    guild.voice_client = voice_client
    return guild


async def test_player_plays_queue_in_order_and_announces_each_track() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        side_effect=lambda **kw: {"stream_url": "s", "title": kw["url"]}
    )
    played: list[str] = []
    bot.voice_presence.play = AsyncMock(
        side_effect=lambda vc, source: played.append("x")
    )  # type: ignore[method-assign]
    channel = MagicMock()
    channel.send = AsyncMock()
    player = GuildPlayer(cog, connected_guild())

    player.enqueue([Track(f"https://a/{n}", "Ada", channel) for n in range(3)])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    assert len(played) == 3
    titles = [call.args[0] for call in channel.send.call_args_list]
    assert titles == [
        EN.now_playing.format(title=f"https://a/{n}", channel="General")
        for n in range(3)
    ]


async def test_player_skips_a_track_that_fails_to_load() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        side_effect=[RuntimeError("down"), {"stream_url": "s"}]
    )
    bot.voice_presence.play = AsyncMock()  # type: ignore[method-assign]
    channel = MagicMock()
    channel.send = AsyncMock()
    player = GuildPlayer(cog, connected_guild())

    player.enqueue(
        [Track("https://a/1", "Ada", channel), Track("https://a/2", "Ada", channel)]
    )
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    assert bot.voice_presence.play.await_count == 1
    assert channel.send.call_args_list[0].args[0] == EN.load_error.format(user="Ada")


async def test_player_drops_the_queue_when_the_bot_left_voice() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock()
    guild = connected_guild()
    guild.voice_client = None
    player = GuildPlayer(cog, guild)

    player.enqueue([Track("https://a/1", "Ada", MagicMock())])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    cog.client.get_info.assert_not_awaited()
    assert player.queue.empty()
