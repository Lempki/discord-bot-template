"""Tests for the media cog's per-guild player, with the service and voice faked out."""

import asyncio
import shlex
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
import pytest
from discord import app_commands

from bot import BotApp
from cogs.media import (
    DEFAULT_VOLUME,
    LEAVER_GRACE_SECONDS,
    QUEUE_PAGE_SIZE,
    GuildPlayer,
    MediaCog,
    PanelView,
    Prepared,
    QueueView,
    StopConfirmView,
    Track,
    clock,
    collection_label,
    cut_lyrics,
    ended_card,
    join_names,
    link,
    played_length,
    progress_line,
    session_length,
    skips_of,
    suggestion_name,
)
from config import Config, ServiceConfig
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils import database
from utils.audio import (
    LOUDNESS_FILTER,
    SILENCE,
    BufferedSource,
    MediaAPIClient,
    audio_filters,
    prime,
    source_name,
)

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


def panel_channel() -> MagicMock:
    """A text channel that records its messages, where nobody else writes."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 50
    channel.last_message_id = None
    channel.sent = []

    async def send(**kwargs: Any) -> MagicMock:
        message = MagicMock(spec=discord.Message)
        message.id = 100 + len(channel.sent)
        message.channel = channel
        message.guild = MagicMock(id=GUILD_ID)
        message.embeds = [kwargs["embed"]]
        message.view = kwargs.get("view")

        async def edit_message(**changes: Any) -> MagicMock:
            if "embed" in changes:
                message.embeds = [changes["embed"]]
            message.view = changes.get("view")
            return message

        message.edit = AsyncMock(side_effect=edit_message)
        message.delete = AsyncMock()
        channel.sent.append(message)
        channel.last_message_id = message.id
        return message

    channel.send = AsyncMock(side_effect=send)
    return channel


async def test_player_plays_the_queue_in_order_on_one_panel() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        side_effect=lambda **kw: {
            "webpage_url": kw["url"],
            "title": f"Song {kw['url'][-1]}",
            "thumbnail_url": "https://img.test/1.jpg",
        }
    )
    shown: list[str | None] = []
    details: list[str] = []
    channel = panel_channel()

    def play(vc: Any, source: Any) -> None:
        shown.append(channel.sent[-1].embeds[0].title)
        details.append(channel.sent[-1].embeds[0].description.splitlines()[0])

    bot.voice_presence.play = AsyncMock(side_effect=play)  # type: ignore[method-assign]
    player = GuildPlayer(cog, connected_guild())
    cog._players[1] = player

    player.enqueue(
        [Track(f"https://a/{n}", "Ada", channel, source="SoundCloud") for n in range(3)]
    )
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    assert shown == ["Song 0", "Song 1", "Song 2"]
    # Nobody wrote in between, so the one panel was edited for each song.
    assert channel.send.await_count == 1
    panel = channel.sent[0]
    assert details[0] == EN.panel_details.format(source="SoundCloud", user="Ada")
    assert panel.embeds[0].thumbnail.url == "https://img.test/1.jpg"
    # The music ended after three songs, so the panel sums the session up.
    ended = panel.embeds[0]
    assert ended.author.name == EN.panel_ended
    assert ended.title == EN.session_title.format(
        count=3, length=EN.session_minutes.format(minutes=1)
    )
    assert ended.description.splitlines()[0] == EN.session_added_by.format(users="Ada")
    # Without a database the songs are not stored, so no Played songs button appears.
    assert panel.view is None


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
        [
            Track("https://a/1", "**Ada**", channel, "One"),
            Track("https://a/2", "Ada", channel),
        ]
    )
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    assert bot.voice_presence.play.await_count == 1
    # The failure names the track and who added it, with markdown in the name shown as typed.
    assert channel.send.call_args_list[0].args[0] == EN.play_failed.format(
        title="One", user=r"\*\*Ada\*\*"
    )


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
    # A real buffer would start a thread that reads the mocked FFmpeg forever.
    monkeypatch.setattr("utils.audio.BufferedSource", MagicMock())
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


async def test_queue_command_shows_the_queue_privately_a_page_at_a_time() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = Track(
        "https://youtu.be/now", "Ada", MagicMock(), "Hotel {California}"
    )
    player.queue.extend(
        Track(f"https://youtu.be/{n}", "**Ada**", MagicMock(), f"Song {n}", 60)
        for n in range(1, QUEUE_PAGE_SIZE + 3)
    )
    interaction = make_interaction()

    await cog.show_queue.callback(cog, interaction)  # type: ignore[arg-type]

    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    lines = kwargs["embed"].description.splitlines()
    assert lines[0] == EN.queue_now_playing.format(
        title="[Hotel {California}](https://youtu.be/now)"
    )
    assert lines[1] == EN.queue_next
    assert lines[2] == EN.queue_line.format(
        position=1, title="[Song 1](https://youtu.be/1) `1:00`", user=r"\*\*Ada\*\*"
    )
    assert len(lines) == 2 + QUEUE_PAGE_SIZE
    assert kwargs["embed"].footer.text == EN.queue_footer.format(
        page=1, pages=2, count=QUEUE_PAGE_SIZE + 2, length="12:00"
    )

    view = kwargs["view"]
    assert isinstance(view, QueueView)
    assert view.previous_page.disabled
    page_press = make_interaction()
    page_press.response.edit_message = AsyncMock()
    await view.next_page.callback(page_press)  # type: ignore[call-arg]
    second = page_press.response.edit_message.call_args.kwargs["embed"]
    assert second.description.splitlines()[2].startswith(
        f"`{QUEUE_PAGE_SIZE + 1}.` [Song {QUEUE_PAGE_SIZE + 1}]"
    )
    assert view.next_page.disabled


async def test_a_short_queue_has_no_page_buttons() -> None:
    _, cog = await media_cog()
    queued_player(cog, 2)
    interaction = make_interaction()

    await cog.show_queue.callback(cog, interaction)  # type: ignore[arg-type]

    assert "view" not in interaction.response.send_message.call_args.kwargs


async def test_queue_command_without_music() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()

    await cog.show_queue.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.queue_empty]


@pytest.mark.parametrize(
    ("query", "name"),
    [
        ("https://www.youtube.com/watch?v=x", "YouTube"),
        ("https://youtu.be/x", "YouTube"),
        ("https://music.youtube.com/watch?v=x", "YouTube"),
        ("https://soundcloud.com/a/b", "SoundCloud"),
        ("https://open.spotify.com/track/x", "Spotify"),
        ("https://www.example.org/song.mp3", "example.org"),
        ("never gonna give you up", "YouTube"),
    ],
)
def test_source_name(query: str, name: str) -> None:
    assert source_name(query) == name


def busy_player(
    cog: MediaCog, now_playing: int | None, waiting: list[int | None]
) -> GuildPlayer:
    """A player whose current track started 60 seconds ago, with waiting tracks of given lengths."""
    player = cog.player(MagicMock(id=GUILD_ID))
    player.now_playing = "Current"
    player.now_playing_duration = now_playing
    player.started_at = time.monotonic() - 60
    player.queue.extend(
        Track(f"https://youtu.be/{n}", "Ada", MagicMock(), f"Song {n}", length)
        for n, length in enumerate(waiting)
    )
    # A task that never finishes keeps enqueue from starting real playback.
    player._task = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    return player


async def test_wait_adds_the_rest_of_the_current_track_and_the_tracks_ahead() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[200, 100])

    assert player.wait_seconds(1) == 180
    assert player.wait_seconds(3) == 480


async def test_wait_is_unknown_when_a_length_is_missing() -> None:
    _, cog = await media_cog()

    assert busy_player(cog, now_playing=None, waiting=[]).wait_seconds(1) is None
    assert busy_player(cog, now_playing=240, waiting=[None]).wait_seconds(2) is None


def member_in_voice() -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.display_name = "Ada"
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    return member


async def run_play(
    cog: MediaCog, url: str, *, when: str | None = None
) -> tuple[MagicMock, list[str]]:
    interaction = make_interaction(user=member_in_voice())
    interaction.channel = MagicMock(spec=discord.TextChannel)
    cog.bot.voice_presence.connect = AsyncMock()  # type: ignore[method-assign]
    choice = app_commands.Choice(name=when, value=when) if when else None
    await cog.play.callback(cog, interaction, url, None, choice)  # type: ignore[arg-type]
    return interaction, sent_messages(interaction)


async def test_play_names_the_track_that_starts_now() -> None:
    _, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://youtu.be/a", "title": "**Bold** song"}
    )

    _, messages = await run_play(cog, "bold song")

    assert messages == [
        EN.queued_now.format(
            title=r"[\*\*Bold\*\* song](<https://youtu.be/a>)",
            source="YouTube",
            user="Ada",
        )
    ]
    cog.client.get_info.assert_awaited_once_with(query="bold song", source="youtube")


async def test_play_says_where_the_track_waits_and_for_how_long() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[200, 100])
    cog.client.get_info = AsyncMock(
        return_value={
            "webpage_url": "https://youtu.be/b",
            "title": "B",
            "duration_seconds": 90,
        }
    )

    _, messages = await run_play(cog, "https://open.spotify.com/track/b")

    assert messages == [
        EN.queued_one_wait.format(
            title="[B](<https://youtu.be/b>)",
            source="Spotify",
            position=3,
            minutes=8,
            user="Ada",
        )
    ]
    # The queue holds the page that the search found, so the bot plays what it named.
    assert player.queue[-1].query == "https://youtu.be/b"
    assert player.queue[-1].duration == 90


async def test_play_next_puts_the_track_first() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[200, 100])
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://youtu.be/n", "title": "Next"}
    )

    _, messages = await run_play(cog, "https://youtu.be/n", when="next")

    assert player.queue[0].query == "https://youtu.be/n"
    assert messages == [
        EN.queued_one_wait.format(
            title="[Next](<https://youtu.be/n>)",
            source="YouTube",
            position=1,
            minutes=3,
            user="Ada",
        )
    ]


async def test_play_without_a_known_wait_names_only_the_position() -> None:
    _, cog = await media_cog()
    busy_player(cog, now_playing=None, waiting=[])
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://youtu.be/c", "title": "C"}
    )

    _, messages = await run_play(cog, "https://youtu.be/c")

    assert messages == [
        EN.queued_one.format(
            title="[C](<https://youtu.be/c>)", source="YouTube", position=1, user="Ada"
        )
    ]


async def test_play_counts_the_tracks_of_a_playlist() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=None, waiting=[60])
    cog.client.get_playlist = AsyncMock(
        return_value=(
            None,
            [
                {
                    "webpage_url": "https://youtu.be/1",
                    "title": "One",
                    "duration_seconds": 61,
                },
                {"webpage_url": "https://youtu.be/2", "title": "Two"},
                {"title": "No link, left out"},
            ],
        )
    )

    _, messages = await run_play(cog, "https://open.spotify.com/album/x")

    assert messages == [
        EN.queued_many.format(
            count=2,
            source="[Spotify](<https://open.spotify.com/album/x>)",
            position=2,
            user="Ada",
        )
    ]
    assert titles(player) == ["Song 0", "One", "Two"]


async def test_an_album_that_starts_at_once_names_its_first_track_and_itself() -> None:
    _, cog = await media_cog()
    cog.client.get_playlist = AsyncMock(
        return_value=(
            "One Wayne G",
            [
                {
                    "webpage_url": f"https://open.spotify.com/track/{n}",
                    "title": f"Mac DeMarco - 2018051{n}",
                    "artist": "Mac DeMarco",
                    "track": f"2018051{n}",
                    "album": "One Wayne G",
                }
                for n in range(3)
            ],
        )
    )
    player = MagicMock(idle=True, queue=[])
    cog.player = MagicMock(return_value=player)  # type: ignore[method-assign]

    _, messages = await run_play(cog, "https://open.spotify.com/album/x")

    assert messages == [
        EN.queued_many_now.format(
            title="[Mac DeMarco - 20180510](<https://open.spotify.com/track/0>)",
            source=EN.collection_on.format(
                collection="[One Wayne G](<https://open.spotify.com/album/x>)",
                source="Spotify",
            ),
            more=2,
        )
    ]
    queued = player.enqueue.call_args.args[0][0]
    assert (queued.artist, queued.song, queued.album) == (
        "Mac DeMarco",
        "20180510",
        "One Wayne G",
    )
    assert queued.collection == "One Wayne G"
    assert queued.collection_url == "https://open.spotify.com/album/x"


async def test_play_reports_a_track_that_cannot_be_found() -> None:
    _, cog = await media_cog()
    cog.client.get_info = AsyncMock(side_effect=RuntimeError("502"))

    _, messages = await run_play(cog, "nothing like this exists")

    assert messages == [EN.load_error.format(user="Ada")]
    assert not cog.player(MagicMock(id=GUILD_ID)).queue


def test_replies_to_a_command_never_name_its_caller() -> None:
    # Discord shows who ran a command above its reply, so the reply need not say it again.
    for language in ("en", "fi"):
        strings = LOCALES[language]
        for field in (
            "not_in_voice",
            "already_same_channel",
            "queued_now",
            "queued_one",
            "queued_one_wait",
            "queued_many",
            "queued_many_now",
            "load_error",
        ):
            assert "{user}" not in getattr(strings, field), (language, field)


def queued_player(cog: MediaCog, count: int) -> GuildPlayer:
    """A player with numbered tracks waiting and a task that never starts playback."""
    player = cog.player(MagicMock(id=GUILD_ID))
    player.queue.extend(
        Track(f"https://youtu.be/{n}", "Ada", MagicMock(), f"Song {n}")
        for n in range(1, count + 1)
    )
    player._task = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    return player


def titles(player: GuildPlayer) -> list[str]:
    return [track.title or "" for track in player.queue]


async def test_remove_takes_the_track_at_a_position() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 3)
    interaction = make_interaction()

    await cog.remove.callback(cog, interaction, 2)  # type: ignore[arg-type]

    assert titles(player) == ["Song 1", "Song 3"]
    assert sent_messages(interaction) == [
        EN.queue_removed.format(title="[Song 2](<https://youtu.be/2>)")
    ]


async def test_queue_commands_explain_a_missing_position() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 2)
    interaction = make_interaction()

    await cog.remove.callback(cog, interaction, 5)  # type: ignore[arg-type]

    assert titles(player) == ["Song 1", "Song 2"]
    assert sent_messages(interaction) == [EN.queue_no_position.format(position=5)]


@pytest.mark.parametrize(
    ("position", "to", "order", "new_position"),
    [
        (3, 1, ["Song 3", "Song 1", "Song 2"], 1),
        (1, 2, ["Song 2", "Song 1", "Song 3"], 2),
        (1, 99, ["Song 2", "Song 3", "Song 1"], 3),
    ],
)
async def test_move_puts_the_track_at_its_new_position(
    position: int, to: int, order: list[str], new_position: int
) -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 3)
    interaction = make_interaction()

    await cog.move.callback(cog, interaction, position, to)  # type: ignore[arg-type]

    assert titles(player) == order
    assert sent_messages(interaction)[0].endswith(f"to #{new_position}.")


async def test_shuffle_keeps_every_track() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 20)
    interaction = make_interaction()

    await cog.shuffle.callback(cog, interaction)  # type: ignore[arg-type]

    assert sorted(titles(player)) == sorted(f"Song {n}" for n in range(1, 21))
    assert sent_messages(interaction) == [EN.queue_shuffled.format(count=20)]


async def test_clear_empties_the_queue_and_says_how_many_went() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 4)
    interaction = make_interaction()

    await cog.clear.callback(cog, interaction)  # type: ignore[arg-type]

    assert not player.queue
    assert sent_messages(interaction) == [EN.queue_cleared.format(count=4)]


async def test_shuffle_and_clear_say_when_nothing_waits() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()

    await cog.clear.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.queue_nothing_waiting]


async def test_skip_to_drops_the_tracks_before_and_stops_the_current_one() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 4)
    interaction = make_interaction()
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.is_playing.return_value = True
    interaction.guild.voice_client = voice_client

    await cog.skip_to.callback(cog, interaction, 3)  # type: ignore[arg-type]

    assert titles(player) == ["Song 3", "Song 4"]
    voice_client.stop.assert_called_once()
    assert sent_messages(interaction) == [
        EN.queue_skipping_to.format(title="[Song 3](<https://youtu.be/3>)")
    ]


@pytest.mark.usefixtures("db")
async def test_volume_is_stored_and_applied_to_the_playing_track() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()
    voice_client = MagicMock(spec=discord.VoiceClient)
    audio = MagicMock(spec=discord.AudioSource)
    audio.is_opus.return_value = False
    voice_client.source = discord.PCMVolumeTransformer(audio)
    interaction.guild.voice_client = voice_client

    await cog.set_volume.callback(cog, interaction, 80)  # type: ignore[arg-type]

    assert voice_client.source.volume == 0.8
    assert await cog.volume(GUILD_ID) == 80
    assert sent_messages(interaction) == [EN.volume_set.format(volume=80)]


@pytest.mark.usefixtures("db")
async def test_volume_without_a_value_shows_the_current_one() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()

    await cog.set_volume.callback(cog, interaction, None)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.volume_now.format(volume=50)]


async def test_volume_falls_back_to_the_default_without_a_database() -> None:
    _, cog = await media_cog()

    assert await cog.volume(GUILD_ID) == 50


def search_results(count: int) -> list[dict[str, str]]:
    return [
        {
            "title": f"Result {n}",
            "webpage_url": f"https://youtu.be/{n}",
            "duration_formatted": "3:30",
        }
        for n in range(count)
    ]


async def suggest(cog: MediaCog, text: str, source: object = None) -> list[Any]:
    interaction = make_interaction()
    interaction.namespace = SimpleNamespace(source=source)
    return await cog.suggest(interaction, text)


async def test_suggestions_come_from_the_chosen_source_and_are_cached() -> None:
    _, cog = await media_cog()
    cog.client.search = AsyncMock(return_value=search_results(2))

    first = await suggest(cog, "hotel california", "soundcloud")
    again = await suggest(cog, "Hotel California", "soundcloud")

    assert [(c.name, c.value) for c in first] == [
        ("Result 0 (3:30)", "https://youtu.be/0"),
        ("Result 1 (3:30)", "https://youtu.be/1"),
    ]
    assert again == first
    cog.client.search.assert_awaited_once_with("hotel california", "soundcloud", 5)


@pytest.mark.parametrize("text", ["", "ho", "https://youtu.be/x"])
async def test_no_suggestions_for_short_text_or_a_link(text: str) -> None:
    _, cog = await media_cog()
    cog.client.search = AsyncMock()

    assert await suggest(cog, text) == []
    cog.client.search.assert_not_awaited()


async def test_slow_or_failed_search_gives_no_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, cog = await media_cog()
    monkeypatch.setattr("cogs.media.SUGGESTION_TIMEOUT_SECONDS", 0.01)

    async def slow(*_args: object) -> list[dict[str, str]]:
        await asyncio.sleep(1)
        return search_results(1)

    cog.client.search = slow

    assert await suggest(cog, "hotel california") == []


def test_long_titles_fit_discords_limit() -> None:
    name = suggestion_name({"title": "x" * 150, "duration_formatted": "1:02:03"})

    assert len(name) == 100
    assert name.endswith("… (1:02:03)")


def test_link_text_cannot_break_out_of_its_link() -> None:
    assert link("x](https://evil.example)", "https://youtu.be/a") == (
        r"[x\](https://evil.example)](<https://youtu.be/a>)"
    )


async def test_play_names_the_chosen_search_site() -> None:
    _, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://soundcloud.com/a/b", "title": "B"}
    )
    interaction = make_interaction(user=member_in_voice())
    interaction.channel = MagicMock(spec=discord.TextChannel)
    cog.bot.voice_presence.connect = AsyncMock()  # type: ignore[method-assign]
    source = app_commands.Choice(name="SoundCloud", value="soundcloud")

    await cog.play.callback(cog, interaction, "b", source, None)  # type: ignore[arg-type]

    cog.client.get_info.assert_awaited_once_with(query="b", source="soundcloud")
    assert "from SoundCloud" in sent_messages(interaction)[0]


def song(name: str, duration: int | None = 210) -> Track:
    return Track(
        f"https://youtu.be/{name}", "Ada", MagicMock(send=AsyncMock()), name, duration
    )


def playing_guild(*, playing: bool = True) -> tuple[MagicMock, MagicMock]:
    """An interaction in a guild where the bot is connected and maybe playing."""
    interaction = make_interaction()
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = playing
    voice_client.is_paused.return_value = False
    voice_client.channel = MagicMock(spec=discord.VoiceChannel)
    interaction.guild.voice_client = voice_client
    interaction.user.display_name = "Ada"
    return interaction, voice_client


async def test_previous_plays_the_last_song_and_then_the_current_one_again() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 1)
    player.history.append(song("Earlier"))
    player.current = song("Current")
    interaction, voice_client = playing_guild()

    await cog.previous.callback(cog, interaction)  # type: ignore[arg-type]

    assert titles(player) == ["Earlier", "Current", "Song 1"]
    assert player.requeued
    voice_client.stop.assert_called_once()
    assert sent_messages(interaction) == [
        EN.previous_playing.format(title="[Earlier](<https://youtu.be/Earlier>)")
    ]


async def test_previous_without_history_says_so() -> None:
    _, cog = await media_cog()
    interaction, _ = playing_guild()

    await cog.previous.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.previous_none]


@pytest.mark.parametrize(
    ("loop", "finished", "queue", "history"),
    [
        ("off", True, [], ["Song"]),
        ("track", True, ["Song"], ["Song"]),
        ("track", False, [], ["Song"]),
        ("queue", False, ["Song"], ["Song"]),
    ],
    ids=["off", "track-finished", "track-skipped", "queue"],
)
async def test_a_stopped_song_is_recorded_and_repeated_as_loop_says(
    loop: str, finished: bool, queue: list[str], history: list[str]
) -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.loop = loop

    player._after(song("Song"), finished)

    assert titles(player) == queue
    assert [t.title for t in player.history] == history


async def test_requeued_leaves_the_stopped_song_out_of_the_history() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.requeued = True

    player._after(song("Current"), finished=False)

    assert not player.history
    assert not player.requeued


async def test_loop_sets_the_mode() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()
    mode = app_commands.Choice(name="The whole queue", value="queue")

    await cog.loop.callback(cog, interaction, mode)  # type: ignore[arg-type]

    assert cog.player(MagicMock(id=GUILD_ID)).loop == "queue"
    assert sent_messages(interaction) == [EN.loop_queue]


@pytest.mark.parametrize(
    ("seconds", "text"), [(0, "0:00"), (75.9, "1:15"), (3725, "1:02:05")]
)
def test_clock(seconds: float, text: str) -> None:
    assert clock(seconds) == text


def test_long_lyrics_end_at_a_whole_line() -> None:
    lyrics = "\n".join(f"Line {n} of the song" for n in range(500))

    cut = cut_lyrics(lyrics)

    assert len(cut) <= 4096
    assert cut.endswith("of the song\n…")


async def test_lyrics_of_the_playing_song_come_in_a_private_embed() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = song("Eagles - Hotel California", duration=391)
    cog.client.get_lyrics = AsyncMock(
        return_value={
            "track": "Hotel California",
            "artist": "Eagles",
            "lyrics": "On a dark desert highway",
        }
    )
    interaction = make_interaction()

    await cog.lyrics.callback(cog, interaction, None)  # type: ignore[arg-type]

    cog.client.get_lyrics.assert_awaited_once_with(
        "Eagles - Hotel California", 391, None, None
    )
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "Hotel California – Eagles"
    assert kwargs["embed"].description == "On a dark desert highway"
    assert kwargs["embed"].footer.text == EN.lyrics_footer


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404)
            ),
            EN.lyrics_none.format(title="Some song"),
        ),
        (httpx.ConnectError("down"), EN.lyrics_unavailable),
    ],
    ids=["not-found", "unreachable"],
)
async def test_lyrics_explain_why_none_came(error: Exception, expected: str) -> None:
    _, cog = await media_cog()
    cog.client.get_lyrics = AsyncMock(side_effect=error)
    interaction = make_interaction()

    await cog.lyrics.callback(cog, interaction, "Some song")  # type: ignore[arg-type]

    assert sent_messages(interaction) == [expected]


async def test_lyrics_need_a_song() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()

    await cog.lyrics.callback(cog, interaction, None)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.lyrics_nothing]


def voice_channel(guild_id: int = GUILD_ID) -> MagicMock:
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.guild = MagicMock(id=guild_id)
    channel.edit = AsyncMock()
    return channel


async def test_the_channel_names_the_song_and_the_bot_says_it_plays_music() -> None:
    bot, cog = await media_cog()
    bot.change_presence = AsyncMock()  # type: ignore[method-assign]
    cog.player(MagicMock(id=GUILD_ID)).now_playing = "Hotel California"
    channel = voice_channel()

    await cog.show_playing(channel, "Hotel California")
    await cog.show_playing(channel, "Hotel California")

    channel.edit.assert_awaited_with(status="🎵 Hotel California")
    # An unchanged bot status is not sent to Discord again.
    bot.change_presence.assert_awaited_once()
    activity = bot.change_presence.call_args.kwargs["activity"]
    assert isinstance(activity, discord.CustomActivity)
    assert activity.name == EN.status_playing


async def test_the_statuses_clear_when_the_music_ends() -> None:
    bot, cog = await media_cog()
    bot.change_presence = AsyncMock()  # type: ignore[method-assign]
    player = cog.player(MagicMock(id=GUILD_ID))
    player.now_playing = "Song"
    channel = voice_channel()
    await cog.show_playing(channel, "Song")
    player.now_playing = None

    await cog.show_idle(channel)

    channel.edit.assert_awaited_with(status=None)
    assert bot.change_presence.call_args.kwargs["activity"].name == EN.status_idle


async def test_the_bot_status_stays_on_music_while_another_server_plays() -> None:
    bot, cog = await media_cog()
    bot.change_presence = AsyncMock()  # type: ignore[method-assign]
    cog.player(MagicMock(id=1)).now_playing = "One"
    two = cog.player(MagicMock(id=2))
    two.now_playing = "Two"
    await cog.show_playing(voice_channel(1), "One")
    two.now_playing = None

    await cog.show_idle(voice_channel(2))

    bot.change_presence.assert_awaited_once()
    assert bot.change_presence.call_args.kwargs["activity"].name == EN.status_playing


def test_the_starting_status_points_to_help_in_the_bots_language() -> None:
    bot = media_bot()

    # discord.py keeps the payload that it sends on login, with the text as its state.
    sent = bot._connection._activity
    assert sent is not None
    assert (sent["type"], sent.get("state")) == (
        discord.ActivityType.custom.value,
        EN.status_idle,
    )


async def test_a_song_keeps_the_names_it_was_queued_with() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        return_value={
            "webpage_url": "https://youtu.be/x",
            "title": "Baby Talk",
            "artist": "Himiko Kikuchi",
            "track": "Baby Talk",
            "album": "Flying Beagle",
            "thumbnail_url": "https://i.ytimg.com/x.jpg",
        }
    )
    seen: list[Track | None] = []
    player = GuildPlayer(cog, connected_guild())
    bot.voice_presence.play = AsyncMock(
        side_effect=lambda vc, source: seen.append(player.current)
    )  # type: ignore[method-assign]
    queued = Track(
        "https://youtu.be/x",
        "Ada",
        MagicMock(send=AsyncMock()),
        "菊池ひみこ - Baby Talk",
        thumbnail="https://i.scdn.co/cover.jpg",
        artist="菊池ひみこ",
        song="Baby Talk",
    )

    player.enqueue([queued])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    current = seen[0]
    assert current is not None
    assert current.title == "菊池ひみこ - Baby Talk"
    assert (current.artist, current.song, current.album) == (
        "菊池ひみこ",
        "Baby Talk",
        None,
    )
    assert current.thumbnail == "https://i.scdn.co/cover.jpg"


async def test_a_server_that_refuses_the_channel_status_is_not_asked_again() -> None:
    _, cog = await media_cog()
    channel = voice_channel()
    channel.edit.side_effect = discord.Forbidden(MagicMock(status=403), "Missing")

    await cog.show_playing(channel, "Song")
    await cog.show_playing(channel, "Song")

    channel.edit.assert_awaited_once()


async def test_a_pause_stops_the_progress_until_the_song_resumes() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    _, voice_client = playing_guild()
    player.started_at = time.monotonic() - 130

    assert player.toggle_pause(voice_client) is True
    voice_client.pause.assert_called_once()
    # The song played 30 seconds and then stood paused for 100.
    assert player.paused_at is not None
    player.paused_at -= 100
    assert round(player.elapsed()) == 30
    voice_client.is_paused.return_value = True

    assert player.toggle_pause(voice_client) is False
    voice_client.resume.assert_called_once()
    assert round(player.elapsed()) == 30


def panel_track() -> Track:
    return Track(
        "https://youtu.be/now",
        "Ada",
        panel_channel(),
        "Hotel California",
        391,
        "Spotify",
        "https://img.test/now.jpg",
    )


async def test_the_panel_shows_the_song_its_end_and_whats_next() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 5)
    player.current = panel_track()
    player.started_at = time.monotonic() - 91
    player.loop = "queue"

    embed = cog.panel_embed(player, player.current, EN, state="playing", volume=70)

    assert embed.author.name == EN.panel_playing
    assert embed.title == "Hotel California"
    assert embed.url == "https://youtu.be/now"
    details, progress = embed.description.splitlines()
    assert details == EN.panel_details.format(source="Spotify", user="Ada")
    assert progress == progress_line(91, 391)
    upcoming = embed.fields[0].value.splitlines()
    assert upcoming[0] == "`1.` [Song 1](https://youtu.be/1)"
    assert upcoming[-1] == EN.panel_more.format(count=2)
    assert embed.footer.text == EN.panel_footer.format(
        loop=EN.panel_loop_queue, volume=70
    )


async def test_a_paused_panel_shows_where_the_song_stopped() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    player.started_at = time.monotonic() - 75
    player.paused_at = time.monotonic()

    embed = cog.panel_embed(player, player.current, EN, state="paused")

    assert embed.author.name == EN.panel_paused
    # The progress stands still at the pause.
    assert embed.description.splitlines()[1] == progress_line(75, 391)
    assert embed.fields[0].value == EN.panel_next_none


async def test_the_panel_moves_to_the_bottom_when_a_new_song_starts_after_chat() -> (
    None
):
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    guild = playing_guild()[0].guild
    channel = player.current.channel

    await cog.refresh_panel(guild, new_track=True)
    first = channel.sent[0]
    await cog.refresh_panel(guild)
    channel.last_message_id = 999  # Someone wrote below the panel.
    await cog.refresh_panel(guild)
    assert channel.send.await_count == 1
    await cog.refresh_panel(guild, new_track=True)

    assert channel.send.await_count == 2
    first.delete.assert_awaited_once()
    assert player.panel is channel.sent[1]


async def test_the_silent_locale_still_posts_the_panel() -> None:
    bot, cog = await media_cog()
    bot.config = replace(bot.config, locale="silent")
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()

    await cog.refresh_panel(MagicMock(id=GUILD_ID))

    # The panel is the music's controls, so muting command replies must not hide it.
    (panel,) = player.current.channel.sent
    assert panel.embeds[0].author.name == EN.panel_playing


def listener(voice_channel: Any) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 7
    member.voice = MagicMock(channel=voice_channel)
    return member


def press(custom_id: str, user: Any) -> MagicMock:
    interaction = make_interaction(user=user)
    interaction.data = {"custom_id": custom_id}
    return interaction


async def test_only_listeners_may_steer_the_music_from_the_panel() -> None:
    _, cog = await media_cog()
    view = PanelView(cog)
    interaction, voice_client = playing_guild()
    outsider = press("media:skip", listener(MagicMock()))
    outsider.guild = interaction.guild

    assert await view.interaction_check(outsider) is False
    assert sent_messages(outsider) == [EN.panel_not_listening]

    member = listener(voice_client.channel)
    inside = press("media:skip", member)
    inside.guild = interaction.guild
    assert await view.interaction_check(inside) is True
    # Anyone may look at the queue, which only the presser sees.
    looker = press("media:queue", listener(None))
    looker.user.id = 8
    assert await view.interaction_check(looker) is True


async def test_a_member_who_presses_too_fast_is_told_to_wait() -> None:
    _, cog = await media_cog()
    view = PanelView(cog)
    member = listener(None)

    results = [
        await view.interaction_check(press("media:queue", member)) for _ in range(6)
    ]

    assert results == [True] * 5 + [False]


async def test_the_panel_buttons_control_the_player() -> None:
    _, cog = await media_cog()
    view = PanelView(cog)
    player = queued_player(cog, 3)
    player.current = panel_track()
    interaction, voice_client = playing_guild()

    await view.loop_button.callback(interaction)  # type: ignore[call-arg]
    assert player.loop == "queue"
    await view.loop_button.callback(interaction)  # type: ignore[call-arg]
    assert player.loop == "track"

    await view.pause_button.callback(interaction)  # type: ignore[call-arg]
    voice_client.pause.assert_called_once()

    await view.skip_button.callback(interaction)  # type: ignore[call-arg]
    voice_client.stop.assert_called_once()

    # A press updates the panel and sends no message of its own.
    assert sent_messages(interaction) == []


async def test_the_panel_buttons_show_the_state() -> None:
    _, cog = await media_cog()

    view = PanelView(cog, s=EN, paused=True, loop="track")

    assert str(view.pause_button.emoji) == "▶️"
    assert str(view.loop_button.emoji) == "🔂"
    assert view.loop_button.style is discord.ButtonStyle.primary
    assert view.queue_button.label == EN.panel_queue
    assert view.stop_button.style is discord.ButtonStyle.danger
    # The top row is the usual player row, and stop sits below it.
    rows = [
        [item.custom_id for item in view.children if item.row == row] for row in (0, 1)
    ]  # type: ignore[attr-defined]
    assert rows == [
        ["media:shuffle", "media:previous", "media:pause", "media:skip", "media:loop"],
        ["media:stop", "media:queue", "media:lyrics", "media:grab"],
    ]
    assert all(item.custom_id.startswith("media:") for item in view.children)  # type: ignore[attr-defined]


async def test_the_panel_names_the_artist_album_and_where_the_song_came_from() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    track = replace(
        panel_track(),
        title="Mac DeMarco - 20180512",
        artist="Mac DeMarco",
        song="20180512",
        album="Here Comes the Cowboy",
        collection="Mellow",
        collection_url="https://open.spotify.com/playlist/p1",
    )

    embed = cog.panel_embed(player, track, EN, state="ended")

    assert embed.title == "20180512"
    credits, details = embed.description.splitlines()
    assert credits == "**Mac DeMarco** · *Here Comes the Cowboy*"
    assert details == EN.panel_details.format(
        source=EN.collection_on.format(
            collection="[Mellow](https://open.spotify.com/playlist/p1)",
            source="Spotify",
        ),
        user="Ada",
    )


async def test_a_song_from_its_own_album_names_the_album_once() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    track = replace(
        panel_track(),
        artist="Mac DeMarco",
        song="20180512",
        album="One Wayne G",
        collection="One Wayne G",
    )

    embed = cog.panel_embed(player, track, EN, state="ended")

    assert embed.description.splitlines()[0] == "**Mac DeMarco**"


async def test_the_player_takes_the_names_that_the_service_found() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        return_value={
            "webpage_url": "https://youtu.be/x",
            "title": "Mac DeMarco - 20180512",
            "artist": "Mac DeMarco",
            "track": "20180512",
            "album": "One Wayne G",
        }
    )
    seen: list[Track | None] = []
    player = GuildPlayer(cog, connected_guild())
    bot.voice_presence.play = AsyncMock(
        side_effect=lambda vc, source: seen.append(player.current)
    )  # type: ignore[method-assign]

    player.enqueue(
        [Track("https://open.spotify.com/track/1", "Ada", MagicMock(send=AsyncMock()))]
    )
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    current = seen[0]
    assert current is not None
    assert (current.artist, current.song, current.album) == (
        "Mac DeMarco",
        "20180512",
        "One Wayne G",
    )


@pytest.mark.parametrize(
    ("elapsed", "duration", "line"),
    [
        (0, 240, "▱▱▱▱▱▱▱▱▱▱▱▱ `0:00 / 4:00`"),
        (60, 240, "▰▰▰▱▱▱▱▱▱▱▱▱ `1:00 / 4:00`"),
        (300, 240, "▰▰▰▰▰▰▰▰▰▰▰▰ `4:00 / 4:00`"),
        (75, None, "`1:15`"),
    ],
    ids=["start", "quarter", "past-the-end", "unknown-length"],
)
def test_progress_line(elapsed: float, duration: int | None, line: str) -> None:
    assert progress_line(elapsed, duration) == line


async def test_play_next_puts_only_a_playlists_first_track_ahead() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[200, 100])
    cog.client.get_playlist = AsyncMock(
        return_value=(
            "Album",
            [
                {"webpage_url": f"https://youtu.be/new{n}", "title": f"New {n}"}
                for n in range(3)
            ],
        )
    )

    _, messages = await run_play(cog, "https://open.spotify.com/album/x", when="next")

    assert titles(player) == ["New 0", "Song 0", "Song 1", "New 1", "New 2"]
    assert messages == [
        EN.queued_many_next.format(
            count=3,
            source=EN.collection_on.format(
                collection="[Album](<https://open.spotify.com/album/x>)",
                source="Spotify",
            ),
            title="[New 0](<https://youtu.be/new0>)",
            position=4,
        )
    ]


async def test_play_now_interrupts_the_song_and_plays_it_after() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[200])
    player.current = song("Current")
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://youtu.be/urgent", "title": "Urgent"}
    )
    interaction = make_interaction(user=member_in_voice())
    interaction.channel = MagicMock(spec=discord.TextChannel)
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.is_playing.return_value = True
    interaction.guild.voice_client = voice_client
    cog.bot.voice_presence.connect = AsyncMock()  # type: ignore[method-assign]

    now = app_commands.Choice(name="Now", value="now")
    await cog.play.callback(cog, interaction, "urgent", None, now)  # type: ignore[arg-type]

    assert titles(player) == ["Urgent", "Current", "Song 0"]
    assert player.requeued
    voice_client.stop.assert_called_once()
    assert sent_messages(interaction) == [
        EN.queued_now.format(
            title="[Urgent](<https://youtu.be/urgent>)", source="YouTube"
        )
    ]
    assert player.last_action == ("now", "Ada", {"title": "Current"})
    assert player.action_carries


async def test_stop_does_not_restart_a_repeating_queue() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 2)
    player.loop = "queue"
    _, voice_client = playing_guild()

    player.halt(voice_client)
    player._after(song("Current"), finished=False)

    assert not player.queue
    assert [t.title for t in player.history] == ["Current"]


async def test_previous_does_not_repeat_the_song_that_it_put_back() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.loop = "queue"
    player.requeued = True

    player._after(song("Current"), finished=False)

    assert not player.queue


async def test_the_panel_names_who_skipped_on_the_next_song() -> None:
    _, cog = await media_cog()
    view = PanelView(cog)
    player = queued_player(cog, 2)
    player.current = panel_track()
    interaction, _ = playing_guild()

    await view.skip_button.callback(interaction)  # type: ignore[call-arg]
    assert player.action_carries
    next_song = replace(panel_track(), title="Next song")
    embed = cog.panel_embed(player, next_song, EN, state="playing")

    assert embed.description.splitlines()[-1] == EN.action_skipped.format(
        user="Ada", title="Hotel California"
    )


async def test_the_panel_names_the_repeat_mode_in_its_language() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.note("loop", "**Ada**", loop="track")

    embed = cog.panel_embed(player, panel_track(), EN, state="playing")

    assert embed.description.splitlines()[-1] == EN.action_loop.format(
        user=r"\*\*Ada\*\*", loop=EN.panel_loop_track
    )


async def test_an_ended_panel_names_only_a_stop() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.note("paused", "Ada")
    paused = cog.panel_embed(player, panel_track(), EN, state="ended")
    player.note("stopped", "Ada", at="1:15", count=0)
    stopped = cog.panel_embed(player, panel_track(), EN, state="ended")

    assert EN.action_paused.format(user="Ada") not in paused.description
    assert paused.author.name == EN.panel_ended
    assert stopped.description.splitlines()[-1] == EN.action_stopped.format(
        user="Ada", at="1:15"
    )
    assert stopped.author.name == EN.panel_stopped


@pytest.mark.parametrize(
    ("waiting", "action"),
    [(0, "stopped"), (1, "stopped_cleared_one"), (3, "stopped_cleared")],
)
async def test_a_stop_records_where_the_song_stopped_and_what_it_cleared(
    waiting: int, action: str
) -> None:
    _, cog = await media_cog()
    player = queued_player(cog, waiting)
    player.current = panel_track()
    player.started_at = time.monotonic() - 75
    interaction, voice_client = playing_guild()

    cog.stop_music(interaction.guild, "Ada")

    assert player.last_action == (
        action,
        "Ada",
        {"at": f"1:15 / {clock(panel_track().duration or 0)}", "count": waiting},
    )
    assert not player.queue
    voice_client.stop.assert_called_once()
    line = cog.panel_embed(player, panel_track(), EN, state="ended").description
    assert line.splitlines()[-1] == getattr(EN, f"action_{action}").format(
        user="Ada", at=f"1:15 / {clock(panel_track().duration or 0)}", count=waiting
    )


def test_collection_label_drops_an_artist_that_the_card_names() -> None:
    album = replace(
        panel_track(),
        title="Toshiki Kadomatsu - Airport Lady",
        collection="Toshiki Kadomatsu - After 5 Clash",
    )
    assert collection_label(album) == "After 5 Clash"
    named = replace(album, title="Airport Lady", artist="Toshiki Kadomatsu")
    assert collection_label(named) == "After 5 Clash"
    # Another artist's name, or a playlist without one, stays whole.
    mix = replace(album, collection="Various - City Pop")
    assert collection_label(mix) == "Various - City Pop"
    assert collection_label(replace(album, collection="City Pop")) == "City Pop"


async def test_stop_asks_before_it_removes_waiting_songs() -> None:
    _, cog = await media_cog()
    view = PanelView(cog)
    player = queued_player(cog, 3)
    player.current = panel_track()
    interaction, voice_client = playing_guild()
    interaction.original_response = AsyncMock(return_value=MagicMock())

    await view.stop_button.callback(interaction)  # type: ignore[call-arg]

    # Nothing stops until the presser answers.
    voice_client.stop.assert_not_called()
    assert len(player.queue) == 3
    # The question is the press's own reply, sent before any other round trip.
    call = interaction.response.send_message.call_args
    assert call.args[0] == EN.stop_confirm.format(count=3)
    assert EN.stop_confirm_one != EN.stop_confirm
    assert call.kwargs["ephemeral"] is True
    question = call.kwargs["view"]
    assert isinstance(question, StopConfirmView)
    assert question.confirm.label == EN.stop_confirm_yes

    answer = make_interaction()
    answer.guild = interaction.guild
    answer.user.display_name = "Ada"
    answer.response.edit_message = AsyncMock()
    await question.confirm.callback(answer)  # type: ignore[call-arg]

    assert not player.queue
    voice_client.stop.assert_called_once()
    assert player.last_action is not None
    assert player.last_action[:2] == ("stopped_cleared", "Ada")
    answer.response.edit_message.assert_awaited_once_with(content=EN.stopped, view=None)


async def test_cancelling_the_stop_keeps_the_music_and_the_queue() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 3)
    _, voice_client = playing_guild()
    question = StopConfirmView(cog, EN)
    answer = make_interaction()
    answer.response.edit_message = AsyncMock()

    await question.cancel.callback(answer)  # type: ignore[call-arg]

    assert len(player.queue) == 3
    voice_client.stop.assert_not_called()
    answer.response.edit_message.assert_awaited_once_with(
        content=EN.stop_kept, view=None
    )


async def test_stop_without_waiting_songs_stops_at_once() -> None:
    _, cog = await media_cog()
    view = PanelView(cog)
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    interaction, voice_client = playing_guild()
    cog._players[GUILD_ID] = player

    await view.stop_button.callback(interaction)  # type: ignore[call-arg]

    voice_client.stop.assert_called_once()
    interaction.followup.send.assert_not_awaited()


class FakeStream(discord.AudioSource):
    """Hands out numbered frames, and blocks at a frame until released, like a stalled stream."""

    def __init__(self, count: int, stall_at: int | None = None) -> None:
        self.count = count
        self.stall_at = stall_at
        self.released = threading.Event()
        self.n = 0
        self.cleaned = False

    def read(self) -> bytes:
        if self.n == self.stall_at:
            self.released.wait(5)
        self.n += 1
        return bytes([self.n]) * 3840 if self.n <= self.count else b""

    def cleanup(self) -> None:
        self.cleaned = True
        self.released.set()


def test_a_buffered_stream_plays_its_frames_in_order_and_then_ends() -> None:
    stream = FakeStream(5)
    source = BufferedSource(stream, prime_frames=3)

    assert source.wait_until_ready(2)
    frames = [source.read() for _ in range(5)]
    deadline = time.monotonic() + 2
    while (end := source.read()) == SILENCE and time.monotonic() < deadline:
        time.sleep(0.01)

    assert [frame[0] for frame in frames] == [1, 2, 3, 4, 5]
    assert end == b""


def test_a_stalled_stream_plays_silence_instead_of_blocking() -> None:
    stream = FakeStream(10, stall_at=2)
    source = BufferedSource(stream, prime_frames=2)
    assert source.wait_until_ready(2)

    assert [source.read()[0] for _ in range(2)] == [1, 2]
    started = time.monotonic()
    assert source.read() == SILENCE
    # The player's 20 ms clock must never wait on the network.
    assert time.monotonic() - started < 0.05

    stream.released.set()
    deadline = time.monotonic() + 2
    while (frame := source.read()) == SILENCE and time.monotonic() < deadline:
        time.sleep(0.01)
    assert frame[0] == 3
    source.cleanup()


def test_cleanup_closes_the_stream_behind_the_buffer() -> None:
    stream = FakeStream(10_000)
    source = BufferedSource(stream, buffer_frames=4)

    source.cleanup()

    assert stream.cleaned


async def test_prime_waits_for_the_buffer_behind_a_volume_control() -> None:
    stream = FakeStream(3)
    source = discord.PCMVolumeTransformer(BufferedSource(stream, prime_frames=3))

    await asyncio.wait_for(prime(source), timeout=2)

    assert source.read() != SILENCE


def limited(cog: MediaCog, limit: int) -> None:
    cog.bot.config = replace(cog.bot.config, max_queue_length=limit)


async def test_a_full_queue_takes_no_more_songs() -> None:
    _, cog = await media_cog()
    limited(cog, 3)
    queued_player(cog, 3)
    cog.client.get_info = AsyncMock()

    interaction, messages = await run_play(cog, "one more song")

    assert messages == [EN.queue_full.format(limit=3)]
    # The bot neither looks the song up nor joins voice.
    cog.client.get_info.assert_not_awaited()
    cog.bot.voice_presence.connect.assert_not_awaited()


async def test_a_playlist_fills_the_queue_and_says_how_many_were_left_out() -> None:
    _, cog = await media_cog()
    limited(cog, 4)
    player = queued_player(cog, 1)
    cog.client.get_playlist = AsyncMock(
        return_value=(
            None,
            [
                {"webpage_url": f"https://youtu.be/new{n}", "title": f"New {n}"}
                for n in range(5)
            ],
        )
    )

    _, messages = await run_play(cog, "https://www.youtube.com/playlist?list=x")

    assert titles(player) == ["Song 1", "New 0", "New 1", "New 2"]
    assert messages == [
        EN.queued_many.format(
            count=3,
            source="[YouTube](<https://www.youtube.com/playlist?list=x>)",
            position=2,
        )
        + "\n"
        + EN.queue_cut.format(left=2, limit=4)
    ]


async def test_a_withheld_spotify_playlist_is_explained() -> None:
    _, cog = await media_cog()
    response = MagicMock(status_code=403)
    cog.client.get_playlist = AsyncMock(
        side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=response)
    )

    _, messages = await run_play(cog, "https://open.spotify.com/playlist/p2")

    assert messages == [EN.playlist_unavailable]


async def test_a_prepared_song_starts_without_a_new_lookup_or_stream() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock()
    bot.voice_presence.play = AsyncMock()  # type: ignore[method-assign]
    player = GuildPlayer(cog, connected_guild())
    track = Track("https://youtu.be/next", "Ada", MagicMock(send=AsyncMock()), "Next")
    pcm = MagicMock(spec=discord.AudioSource)
    pcm.is_opus.return_value = False
    buffering = discord.PCMVolumeTransformer(pcm, 0.2)
    player._prepared = Prepared(
        track, info={"webpage_url": "https://youtu.be/next"}, source=buffering
    )

    player.enqueue([track])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    cog.client.get_info.assert_not_awaited()
    cog.client.audio_source.assert_not_called()
    assert bot.voice_presence.play.call_args.args[1] is buffering
    # The volume is the server's current one, not the one from when it was prepared.
    assert buffering.volume == DEFAULT_VOLUME / 100


async def test_a_prepared_song_that_is_no_longer_next_is_dropped() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(return_value={"webpage_url": "https://youtu.be/a"})
    bot.voice_presence.play = AsyncMock()  # type: ignore[method-assign]
    player = GuildPlayer(cog, connected_guild())
    stale = MagicMock(spec=discord.AudioSource)
    player._prepared = Prepared(song("Moved"), info={"webpage_url": "x"}, source=stale)

    player.enqueue([song("Other")])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    stale.cleanup.assert_called_once()
    cog.client.get_info.assert_awaited_once()


async def test_the_next_song_is_looked_up_at_once_and_buffered_near_the_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cogs.media.PREPARE_CHECK_SECONDS", 0.01)
    _, cog = await media_cog()
    cog.client.get_info = AsyncMock(return_value={"webpage_url": "https://youtu.be/b"})
    player = queued_player(cog, 1)
    upcoming = player.queue[0]
    player.now_playing_duration = 200
    player.started_at = time.monotonic() - 60
    preparer = asyncio.create_task(player._prepare_next())

    async def settle() -> None:
        for _ in range(50):
            await asyncio.sleep(0.01)

    await settle()
    assert player._prepared is not None and player._prepared.track is upcoming
    assert player._prepared.info == {"webpage_url": "https://youtu.be/b"}
    # 140 seconds are left, so no audio starts yet.
    cog.client.audio_source.assert_not_called()

    player.started_at = time.monotonic() - 190
    await settle()
    cog.client.audio_source.assert_called_once()
    source = player._prepared.source
    assert source is not None

    player.queue.clear()
    await settle()
    preparer.cancel()
    # The queue changed, so the buffering audio was closed.
    assert player._prepared is None
    source.cleanup.assert_called_once()


async def test_a_paused_song_starts_no_audio_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cogs.media.PREPARE_CHECK_SECONDS", 0.01)
    _, cog = await media_cog()
    cog.client.get_info = AsyncMock(return_value={"webpage_url": "https://youtu.be/b"})
    player = queued_player(cog, 1)
    player.now_playing_duration = 200
    player.started_at = time.monotonic() - 195
    player.paused_at = time.monotonic()
    preparer = asyncio.create_task(player._prepare_next())

    for _ in range(30):
        await asyncio.sleep(0.01)
    preparer.cancel()

    cog.client.audio_source.assert_not_called()


def listener_named(
    member_id: int, *, roles: tuple[int, ...] = (), admin: bool = False
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.bot = False
    member.display_name = f"Member {member_id}"
    member.roles = [MagicMock(id=role) for role in roles]
    member.guild_permissions = MagicMock(manage_guild=admin)
    return member


def dj_guild(cog: MediaCog, members: list[MagicMock], dj_role: int | None) -> MagicMock:
    """A guild where the bot plays a song, the members listen, and dj_role is the DJ role."""
    guild = MagicMock(id=GUILD_ID)
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.channel = MagicMock(members=members)
    guild.voice_client = voice_client
    cog._dj_role = AsyncMock(return_value=dj_role)  # type: ignore[method-assign]
    cog.refresh_panel = AsyncMock()  # type: ignore[method-assign]
    player = cog.player(guild)
    player.current = replace(song("Current"), requested_by_id=1)
    return guild


@pytest.mark.parametrize(
    ("dj_role", "member", "listening", "allowed"),
    [
        (None, listener_named(5), 4, True),
        (77, listener_named(5, roles=(77,)), 4, True),
        (77, listener_named(5, admin=True), 4, True),
        (77, listener_named(5), 1, True),
        (77, listener_named(5), 4, False),
    ],
    ids=["no-dj-role", "dj", "admin", "alone", "listener"],
)
async def test_who_may_control_the_music(
    dj_role: int | None, member: MagicMock, listening: int, allowed: bool
) -> None:
    _, cog = await media_cog()
    others = [listener_named(100 + n) for n in range(listening - 1)]
    guild = dj_guild(cog, [member, *others], dj_role)

    assert await cog.may_control(member, guild) is allowed


async def test_a_skip_needs_half_of_the_listeners_while_others_listen() -> None:
    _, cog = await media_cog()
    # Five members listen.
    members = [listener_named(n) for n in range(2, 7)]
    guild = dj_guild(cog, members, 77)
    player = cog.player(guild)

    first = await cog.request_skip(guild, members[0])
    again = await cog.request_skip(guild, members[0])
    second = await cog.request_skip(guild, members[1])
    third = await cog.request_skip(guild, members[2])

    assert first == (False, 1, 3, False)
    # A second vote from the same member does not count twice, and they hear so.
    assert again.vote_text(EN) == EN.skip_already_voted.format(votes=1, needed=3)
    assert again == (False, 1, 3, True)
    assert second == (False, 2, 3, False)
    assert third == (True, 3, 3, False)
    assert player.last_action is not None
    assert player.last_action[0] == "skipped_vote"


@pytest.mark.parametrize(
    ("skipper", "listening"),
    [(1, 5), (2, 2)],
    ids=["added-the-song", "two-listeners"],
)
async def test_some_skips_need_no_vote(skipper: int, listening: int) -> None:
    _, cog = await media_cog()
    members = [listener_named(n) for n in range(1, listening + 1)]
    guild = dj_guild(cog, members, 77)
    member = next(m for m in members if m.id == skipper)

    assert await cog.request_skip(guild, member) == (True, 0, 0, False)


async def test_a_listener_without_the_dj_role_cannot_clear_the_queue() -> None:
    _, cog = await media_cog()
    member = listener_named(5)
    guild = dj_guild(cog, [member, listener_named(6)], 77)
    player = queued_player(cog, 3)
    interaction = make_interaction(user=member)
    interaction.guild = guild

    await cog.clear.callback(cog, interaction)  # type: ignore[arg-type]

    assert len(player.queue) == 3
    assert sent_messages(interaction) == [EN.dj_only]
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_a_listener_may_remove_their_own_song_but_not_others() -> None:
    _, cog = await media_cog()
    member = listener_named(5)
    guild = dj_guild(cog, [member, listener_named(6)], 77)
    player = queued_player(cog, 2)
    player.queue[0] = replace(player.queue[0], requested_by_id=5)
    player.queue[1] = replace(player.queue[1], requested_by_id=6)

    others = make_interaction(user=member)
    others.guild = guild
    await cog.remove.callback(cog, others, 2)  # type: ignore[arg-type]
    own = make_interaction(user=member)
    own.guild = guild
    await cog.remove.callback(cog, own, 1)  # type: ignore[arg-type]

    assert sent_messages(others) == [EN.dj_only]
    assert titles(player) == ["Song 2"]


async def test_a_panel_from_before_a_restart_becomes_a_record_of_its_song(
    db: None,
) -> None:
    bot, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    player.started_at = time.monotonic() - 30
    live = cog.panel_embed(player, player.current, EN, state="playing")
    message = MagicMock(spec=discord.Message)
    message.guild = MagicMock(id=GUILD_ID)
    message.embeds = [live]
    message.edit = AsyncMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    bot.get_channel = MagicMock(return_value=channel)  # type: ignore[method-assign]
    await database.save_panel(GUILD_ID, 50, 500)

    await cog.close_old_panel(GUILD_ID, 50, 500)

    kwargs = message.edit.call_args.kwargs
    assert kwargs["view"] is None
    card = kwargs["embeds"][0]
    assert card.author.name == EN.panel_ended
    assert card.title == "Hotel California"
    # The progress, the next songs, and the footer no longer hold.
    assert card.description == EN.panel_details.format(source="Spotify", user="Ada")
    assert not card.fields
    assert card.footer.text is None
    assert await database.list_panels() == []


async def test_a_deleted_old_panel_is_forgotten(db: None) -> None:
    bot, cog = await media_cog()
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "Unknown Message")
    )
    bot.get_channel = MagicMock(return_value=channel)  # type: ignore[method-assign]
    await database.save_panel(GUILD_ID, 50, 500)

    await cog.close_old_panel(GUILD_ID, 50, 500)

    assert await database.list_panels() == []


async def test_a_posted_panel_is_recorded_and_an_ended_one_forgotten(db: None) -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    channel = player.current.channel

    await cog.refresh_panel(MagicMock(id=GUILD_ID), new_track=True)
    panel = channel.sent[0]
    assert await database.list_panels() == [(GUILD_ID, channel.id, panel.id)]

    player.history.append(player.current)
    await cog.end_panel(player)
    assert await database.list_panels() == []


def test_ended_card_keeps_a_card_without_progress() -> None:
    card = ended_card(discord.Embed(title="Song", description="`1:15`"), EN)

    assert card.description is None
    assert card.author.name == EN.panel_ended


def session_song(name: str, user: str, **extra: Any) -> Track:
    return replace(song(name), requested_by=user, **extra)


async def test_a_session_card_sums_up_the_songs_and_who_added_them() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    album = {
        "collection": "One Wayne G",
        "collection_url": "https://open.spotify.com/album/x",
        "source": "Spotify",
    }
    songs = [
        session_song("20180512", "Kempli", **album),
        session_song("20180529", "Kempli", **album),
        session_song("Other", "Bo"),
        session_song(
            "20180701",
            "Ada",
            artist="Mac DeMarco",
            song="20180701",
            thumbnail="https://i.scdn.co/cover.jpg",
            **album,
        ),
    ]
    player.session_seconds = 72 * 60
    player.note("stopped", "Kempli", at="2:13 / 4:20", count=0)

    card = cog.session_card(player, songs, EN)

    assert card.title == EN.session_title.format(
        count=4, length=EN.session_hours.format(hours=1, minutes=12)
    )
    added, mostly, last, stopped = card.description.splitlines()
    # The member who added the most songs comes first.
    assert added == EN.session_added_by.format(users="Kempli, Bo, and Ada")
    assert mostly == EN.session_mostly.format(
        source=EN.collection_on.format(
            collection="[One Wayne G](https://open.spotify.com/album/x)",
            source="Spotify",
        )
    )
    assert last == EN.session_last.format(
        title="[20180701](https://youtu.be/20180701) `3:30` – Mac DeMarco"
    )
    assert stopped == EN.action_stopped.format(user="Kempli", at="2:13 / 4:20")
    assert card.author.name == EN.panel_stopped
    assert card.thumbnail.url == "https://i.scdn.co/cover.jpg"


def test_join_names_and_others() -> None:
    assert join_names(["Ada"], EN) == "Ada"
    assert join_names(["Ada", "Bo"], EN) == "Ada and Bo"
    others = EN.names_others.format(count=2)
    assert join_names(["Ada", "Bo", "Cy", others], EN) == f"Ada, Bo, Cy, and {others}"
    assert join_names(["Ada", "Bo", "Cy"], LOCALES["fi"]) == "Ada, Bo ja Cy"


@pytest.mark.parametrize(
    ("seconds", "minutes", "hours"),
    [(20, 1, 0), (12 * 60 + 20, 12, 0), (60 * 60, 0, 1), (125 * 60, 5, 2)],
)
def test_session_length(seconds: float, minutes: int, hours: int) -> None:
    expected = (
        EN.session_hours.format(hours=hours, minutes=minutes)
        if hours
        else EN.session_minutes.format(minutes=minutes)
    )
    assert session_length(seconds, EN) == expected


async def test_a_finished_session_keeps_its_songs_for_the_played_button(
    db: None,
) -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    await cog.refresh_panel(MagicMock(id=GUILD_ID), new_track=True)
    panel = player.panel
    assert panel is not None
    player.session = [session_song(f"Song {n}", "Ada") for n in range(12)]
    player.session_seconds = 600
    player.history.append(player.session[-1])

    await cog.end_panel(player)

    # The card says when the music ended, which Discord shows in each viewer's time zone.
    assert panel.embeds[0].timestamp is not None
    assert panel.embeds[0].author.name == EN.panel_ended
    assert panel.view is not None
    assert panel.view.played_button.label == EN.panel_played
    press = make_interaction()
    press.message = panel
    await cog.send_played(press)

    kwargs = press.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    first = kwargs["embed"]
    assert first.title == EN.played_title
    assert first.description.splitlines()[0] == EN.queue_line.format(
        position=1, title="[Song 0](https://youtu.be/Song 0) `3:30`", user="Ada"
    )
    assert first.footer.text == "1/2"


async def test_a_list_that_is_no_longer_kept_says_so(db: None) -> None:
    _, cog = await media_cog()
    press = make_interaction()
    press.message = MagicMock(id=999)

    await cog.send_played(press)

    assert sent_messages(press) == [EN.played_gone]


async def test_each_server_keeps_the_last_20_sessions(db: None) -> None:
    for message_id in range(1, 23):
        await database.save_session(GUILD_ID, message_id, [{"title": f"{message_id}"}])

    assert await database.get_session(1) is None
    assert await database.get_session(2) is None
    assert await database.get_session(3) == [{"title": "3"}]
    assert await database.get_session(22) == [{"title": "22"}]


async def test_music_skip_stops_the_song_or_counts_a_vote() -> None:
    _, cog = await media_cog()
    members = [listener_named(n) for n in range(2, 7)]
    guild = dj_guild(cog, members, 77)
    voice_client = guild.voice_client
    voice_client.is_playing.return_value = True
    voter = make_interaction(user=members[0])
    voter.guild = guild

    await cog.skip.callback(cog, voter)  # type: ignore[arg-type]

    voice_client.stop.assert_not_called()
    assert sent_messages(voter) == [EN.skip_voted.format(votes=1, needed=3)]

    adder = make_interaction(user=listener_named(1))
    adder.guild = guild
    await cog.skip.callback(cog, adder)  # type: ignore[arg-type]

    voice_client.stop.assert_called_once()
    assert sent_messages(adder) == [EN.skipped]


def member_song(name: str, member_id: int) -> Track:
    return Track(
        f"https://youtu.be/{name}",
        f"Member {member_id}",
        MagicMock(),
        name,
        requested_by_id=member_id,
    )


async def test_the_queue_takes_turns_between_members() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[])
    player.current = member_song("Ada 1", 1)
    album = [member_song(f"Ada {n}", 1) for n in range(2, 6)]
    assert player.enqueue(album, turns=True) == 1

    # Bo's first song waits only for the song that plays, then the songs take turns.
    assert (
        player.enqueue([member_song("Bo 1", 2), member_song("Bo 2", 2)], turns=True)
        == 1
    )
    # Cy has had no turn yet, so Cy's song goes ahead of everyone's second turn.
    assert player.enqueue([member_song("Cy 1", 3)], turns=True) == 2
    # Ada's next song waits for every turn before hers.
    assert player.enqueue([member_song("Ada 6", 1)], turns=True) == 8

    assert titles(player) == [
        "Bo 1",
        "Cy 1",
        "Ada 2",
        "Bo 2",
        "Ada 3",
        "Ada 4",
        "Ada 5",
        "Ada 6",
    ]


async def test_without_turns_the_queue_keeps_the_order_of_adding() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[])
    player.current = member_song("Ada 1", 1)
    player.enqueue([member_song("Ada 2", 1), member_song("Ada 3", 1)])

    assert player.enqueue([member_song("Bo 1", 2)]) == 3
    assert titles(player) == ["Ada 2", "Ada 3", "Bo 1"]


async def test_play_says_when_a_song_went_ahead_by_taking_turns(db: None) -> None:
    _, cog = await media_cog()
    await database.upsert_settings(GUILD_ID, fair_queue=True)
    player = busy_player(cog, now_playing=None, waiting=[])
    # The panel moves after the reply, so the playing song needs a channel to post in.
    player.current = replace(member_song("Bo 1", 2), channel=panel_channel())
    player.enqueue([member_song("Bo 2", 2), member_song("Bo 3", 2)])
    cog.client.get_info = AsyncMock(
        return_value={"webpage_url": "https://youtu.be/c", "title": "C"}
    )

    _, messages = await run_play(cog, "https://youtu.be/c")

    # The member in voice has had no turn, so the song goes ahead of Bo's second one.
    assert titles(player)[0] == "C"
    assert messages == [
        EN.queued_one.format(
            title="[C](<https://youtu.be/c>)", source="YouTube", position=1, user="Ada"
        )
        + "\n"
        + EN.queue_turns
    ]


def test_audio_filters_cut_first_and_then_even_the_loudness() -> None:
    assert audio_filters((), even_loudness=False) is None
    assert audio_filters((), even_loudness=True) == LOUDNESS_FILTER
    cut = audio_filters(((0.0, 9.5), (200.0, 212.0)), even_loudness=True)
    assert cut == (
        "aselect='not(between(t,0,9.5)+between(t,200,212))',asetpts=N/SR/TB,"
        + LOUDNESS_FILTER
    )


async def test_audio_source_passes_the_filters_to_ffmpeg_as_one_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = MagicMock()
    monkeypatch.setattr("utils.audio.discord.FFmpegPCMAudio", ffmpeg)
    monkeypatch.setattr("utils.audio.discord.PCMVolumeTransformer", MagicMock())
    monkeypatch.setattr("utils.audio.BufferedSource", MagicMock())
    client = MediaAPIClient("http://media:8000/", "s3cret")

    client.audio_source(
        "https://youtu.be/x", "ffmpeg", skips=((0.0, 9.5),), even_loudness=True
    )
    await client.aclose()

    # discord.py splits the options like a shell, so the filter chain must stay whole.
    options = shlex.split(ffmpeg.call_args.kwargs["options"])
    assert options[:2] == ["-vn", "-af"]
    assert options[2] == audio_filters(((0.0, 9.5),), even_loudness=True)


def test_skips_of_reads_only_usable_parts() -> None:
    info = {"skip_segments": [[0, 9.5], [30, 20], ["x", 1], [100.0, 110.0]]}

    assert skips_of(info) == ((0.0, 9.5), (100.0, 110.0))
    assert skips_of({}) == ()


def test_played_length_leaves_out_the_skipped_parts() -> None:
    assert played_length(212, ((0.0, 9.5), (200.0, 212.0))) == 190
    assert played_length(None, ((0.0, 9.5),)) is None
    assert played_length(212, ()) == 212


async def test_the_player_cuts_the_skipped_parts_and_evens_the_loudness() -> None:
    bot, cog = await media_cog()
    cog.client.get_info = AsyncMock(
        return_value={
            "webpage_url": "https://youtu.be/x",
            "title": "Song",
            "duration_seconds": 200,
            "skip_segments": [[0, 10]],
        }
    )
    lengths: list[int | None] = []
    player = GuildPlayer(cog, connected_guild())
    bot.voice_presence.play = AsyncMock(
        side_effect=lambda vc, source: lengths.append(player.now_playing_duration)
    )  # type: ignore[method-assign]

    player.enqueue([Track("song name", "Ada", MagicMock(send=AsyncMock()))])
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    kwargs = cog.client.audio_source.call_args.kwargs
    assert kwargs["skips"] == ((0.0, 10.0),)
    # The setting cannot be read without a database, so the loudness stays even.
    assert kwargs["even_loudness"] is True
    # The panel counts the song's length without the skipped part.
    assert lengths == [190]


async def test_remove_member_takes_only_that_members_waiting_songs() -> None:
    _, cog = await media_cog()
    player = busy_player(cog, now_playing=240, waiting=[])
    player.current = member_song("Ada 1", 1)
    player.enqueue(
        [member_song("Ada 2", 1), member_song("Bo 1", 2), member_song("Ada 3", 1)]
    )

    assert player.remove_member(1) == 2
    assert titles(player) == ["Bo 1"]
    assert player.remove_member(1) == 0


def grab_press(player: GuildPlayer, *, dm_open: bool = True) -> MagicMock:
    press = make_interaction()
    press.guild.name = "Lähettämö"
    press.user.send = AsyncMock(
        side_effect=None
        if dm_open
        else discord.Forbidden(
            MagicMock(status=403), "Cannot send messages to this user"
        )
    )
    return press


async def test_the_grab_button_sends_the_song_to_the_presser() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = replace(panel_track(), artist="Eagles", song="Hotel California")
    press = grab_press(player)

    await PanelView(cog).grab_button.callback(press)  # type: ignore[call-arg]

    card = press.user.send.call_args.kwargs["embed"]
    assert card.title == "Hotel California"
    assert card.author.name == EN.grab_heading.format(server="Lähettämö")
    assert card.description.splitlines()[0] == "**Eagles**"
    assert card.description.splitlines()[-1] == EN.grab_length.format(length="6:31")
    press.followup.send.assert_awaited_once_with(EN.grab_sent, ephemeral=True)


async def test_the_grab_button_shows_the_song_privately_when_dms_are_closed() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()
    press = grab_press(player, dm_open=False)

    await PanelView(cog).grab_button.callback(press)  # type: ignore[call-arg]

    call = press.followup.send.call_args
    assert call.args == (EN.grab_closed,)
    assert call.kwargs["embed"].title == "Hotel California"
    assert call.kwargs["ephemeral"] is True


async def test_the_grab_button_says_when_nothing_plays() -> None:
    _, cog = await media_cog()
    press = grab_press(cog.player(MagicMock(id=GUILD_ID)))

    await PanelView(cog).grab_button.callback(press)  # type: ignore[call-arg]

    press.user.send.assert_not_awaited()
    press.followup.send.assert_awaited_once_with(EN.grab_nothing, ephemeral=True)


def voice_member(member_id: int, guild: MagicMock, channel: object | None) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.bot = False
    member.display_name = f"Member {member_id}"
    member.guild = guild
    member.voice = SimpleNamespace(channel=channel) if channel is not None else None
    return member


def leaver_guild() -> tuple[MagicMock, MagicMock]:
    guild = MagicMock(id=GUILD_ID)
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.channel = MagicMock(name="voice")
    guild.voice_client = voice_client
    return guild, voice_client.channel


async def test_a_leavers_waiting_songs_go_after_the_grace_period(
    db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cogs.media.LEAVER_GRACE_SECONDS", 0)
    await database.upsert_settings(GUILD_ID, leave_cleanup=True)
    _, cog = await media_cog()
    guild, channel = leaver_guild()
    player = cog.player(guild)
    player._task = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    player.enqueue([member_song("Ada 2", 1), member_song("Bo 1", 2)])
    member = voice_member(1, guild, None)

    await cog.on_voice_state_update(
        member,
        SimpleNamespace(channel=channel),
        SimpleNamespace(channel=None),  # type: ignore[arg-type]
    )
    await asyncio.wait_for(cog._leavers[(GUILD_ID, 1)], timeout=1)

    assert titles(player) == ["Bo 1"]
    assert player.last_action == ("left_one", "Member 1", {"count": 1})
    assert not cog._leavers


async def test_a_leaver_who_returns_in_time_keeps_their_songs(
    db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    await database.upsert_settings(GUILD_ID, leave_cleanup=True)
    _, cog = await media_cog()
    guild, channel = leaver_guild()
    player = cog.player(guild)
    player._task = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    player.enqueue([member_song("Ada 2", 1)])
    member = voice_member(1, guild, channel)
    left = SimpleNamespace(channel=None)
    there = SimpleNamespace(channel=channel)

    await cog.on_voice_state_update(member, there, left)  # type: ignore[arg-type]
    pending = cog._leavers[(GUILD_ID, 1)]
    await cog.on_voice_state_update(member, left, there)  # type: ignore[arg-type]
    await asyncio.sleep(0)

    assert pending.cancelled()
    assert titles(player) == ["Ada 2"]


async def test_leavers_keep_their_songs_when_the_setting_is_off(db: None) -> None:
    _, cog = await media_cog()
    guild, channel = leaver_guild()
    player = cog.player(guild)
    player._task = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    player.enqueue([member_song("Ada 2", 1)])

    await cog.on_voice_state_update(
        voice_member(1, guild, None),
        SimpleNamespace(channel=channel),
        SimpleNamespace(channel=None),  # type: ignore[arg-type]
    )

    assert not cog._leavers
    assert LEAVER_GRACE_SECONDS == 120
