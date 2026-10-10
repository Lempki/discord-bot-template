"""Tests for the media cog's per-guild player, with the service and voice faked out."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot import BotApp
from cogs.media import QUEUE_SHOWN, GuildPlayer, MediaCog, Track
from config import Config, ServiceConfig
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils.audio import MediaAPIClient

EN = LOCALES["en"]


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
        side_effect=lambda **kw: {"webpage_url": kw["url"], "title": kw["url"]}
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


async def test_player_streams_the_page_url_through_the_service() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://youtu.be/x", "title": "Song"}
    )
    playing: list[str | None] = []
    player = GuildPlayer(cog, connected_guild())
    bot.voice_presence.play = AsyncMock(
        side_effect=lambda vc, source: playing.append(player.now_playing)
    )  # type: ignore[method-assign]

    player.enqueue([Track("song name", "Ada", MagicMock(send=AsyncMock()))])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    assert cog.client.audio_source.call_args.args[0] == "https://youtu.be/x"
    assert playing == ["Song"]
    assert player.now_playing is None


async def test_player_skips_a_track_that_fails_to_load() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        side_effect=[RuntimeError("down"), {"webpage_url": "https://a/2"}]
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
    assert not player.queue


async def test_audio_source_streams_from_the_service_with_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = MagicMock()
    monkeypatch.setattr("utils.audio.discord.FFmpegPCMAudio", ffmpeg)
    monkeypatch.setattr("utils.audio.discord.PCMVolumeTransformer", MagicMock())
    client = MediaAPIClient("http://media:8000/", "s3cret")

    client.audio_source("https://youtu.be/x?si=a&t=1", "ffmpeg")
    await client.aclose()

    url = ffmpeg.call_args.args[0]
    options = ffmpeg.call_args.kwargs["before_options"]
    assert (
        url
        == "http://media:8000/media/stream?url=https%3A%2F%2Fyoutu.be%2Fx%3Fsi%3Da%26t%3D1"
    )
    assert "Authorization: Bearer s3cret\r\n" in options
    # A reconnect would make the service start the track again from the beginning.
    assert "-reconnect" not in options


@pytest.mark.parametrize(
    ("track", "label"),
    [
        (Track("https://youtu.be/x", "Ada", MagicMock(), "Easy Lover"), "Easy Lover"),
        (Track("https://youtu.be/x", "Ada", MagicMock()), "<https://youtu.be/x>"),
        (Track("hotel california", "Ada", MagicMock()), "hotel california"),
    ],
)
def test_track_label(track: Track, label: str) -> None:
    assert track.label == label


async def test_queue_command_lists_the_current_and_waiting_tracks() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.now_playing = "Hotel {California}"
    waiting = [
        Track(f"https://youtu.be/{n}", "Ada", MagicMock(), f"Song {n}")
        for n in range(QUEUE_SHOWN + 2)
    ]
    player.queue.extend(waiting)
    interaction = make_interaction()

    await cog.show_queue.callback(cog, interaction)  # type: ignore[arg-type]

    text = "\n".join(sent_messages(interaction))
    lines = text.splitlines()
    assert lines[0] == EN.queue_now_playing.format(title="Hotel {California}")
    assert lines[1] == EN.queue_next
    assert lines[2] == EN.queue_line.format(position=1, title="Song 0", user="Ada")
    assert lines[-1] == EN.queue_more.format(count=2)
    assert len(lines) == 2 + QUEUE_SHOWN + 1


async def test_queue_command_without_music() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()

    await cog.show_queue.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.queue_empty]
