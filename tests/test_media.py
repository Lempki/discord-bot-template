"""Tests for the media cog's per-guild player, with the service and voice faked out."""

import asyncio
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
    QUEUE_PAGE_SIZE,
    GuildPlayer,
    MediaCog,
    PanelView,
    QueueView,
    Track,
    clock,
    cut_lyrics,
    link,
    suggestion_name,
)
from config import Config, ServiceConfig
from localization import LOCALES
from tests.conftest import GUILD_ID, make_interaction, sent_messages
from utils.audio import MediaAPIClient, source_name

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
    channel = panel_channel()
    bot.voice_presence.play = AsyncMock(
        side_effect=lambda vc, source: shown.append(channel.sent[-1].embeds[0].title)
    )  # type: ignore[method-assign]
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
    assert panel.embeds[0].description.startswith(
        EN.panel_details.format(source="SoundCloud", user="Ada")
    )
    assert panel.embeds[0].thumbnail.url == "https://img.test/1.jpg"
    # The music ended, so the panel keeps the last song without buttons.
    assert panel.embeds[0].author.name == EN.panel_ended
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
    cog: MediaCog, url: str, *, play_next: bool = False
) -> tuple[MagicMock, list[str]]:
    interaction = make_interaction(user=member_in_voice())
    interaction.channel = MagicMock(spec=discord.TextChannel)
    cog.bot.voice_presence.connect = AsyncMock()  # type: ignore[method-assign]
    await cog.play.callback(cog, interaction, url, None, play_next)  # type: ignore[arg-type]
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

    _, messages = await run_play(cog, "https://youtu.be/n", play_next=True)

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

    _, messages = await run_play(
        cog, "https://open.spotify.com/album/x", play_next=True
    )

    assert messages == [
        EN.queued_many.format(
            count=2,
            source="[Spotify](<https://open.spotify.com/album/x>)",
            position=1,
            user="Ada",
        )
    ]
    assert [t.title for t in list(player.queue)[:2]] == ["One", "Two"]


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

    await cog.play.callback(cog, interaction, "b", source, False)  # type: ignore[arg-type]

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
    return interaction, voice_client


async def test_previous_plays_the_last_song_and_then_the_current_one_again() -> None:
    _, cog = await media_cog()
    player = queued_player(cog, 1)
    player.history.append(song("Earlier"))
    player.current = song("Current")
    interaction, voice_client = playing_guild()

    await cog.previous.callback(cog, interaction)  # type: ignore[arg-type]

    assert titles(player) == ["Earlier", "Current", "Song 1"]
    assert player.going_back
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


async def test_going_back_leaves_the_stopped_song_out_of_the_history() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.going_back = True

    player._after(song("Current"), finished=False)

    assert not player.history
    assert not player.going_back


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


async def test_nowplaying_shows_the_song_and_its_progress_privately() -> None:
    _, cog = await media_cog()
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = replace(song("Current"), source="Spotify")
    player.now_playing = "Current"
    player.started_at = time.monotonic() - 75
    interaction = make_interaction()

    await cog.now_playing.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [
        EN.nowplaying_text.format(
            title="[Current](<https://youtu.be/Current>)",
            source="Spotify",
            user="Ada",
            elapsed="1:15",
            duration="3:30",
        )
    ]
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_nowplaying_without_music() -> None:
    _, cog = await media_cog()
    interaction = make_interaction()

    await cog.now_playing.callback(cog, interaction)  # type: ignore[arg-type]

    assert sent_messages(interaction) == [EN.nothing_playing]


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

    cog.client.get_lyrics.assert_awaited_once_with("Eagles - Hotel California", 391)
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
    ends = int(time.time()) + 300
    assert progress in {
        EN.panel_ends.format(duration="6:31", ends=f"<t:{ends + d}:R>")
        for d in (-1, 0, 1)
    }
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
    assert embed.description.splitlines()[1] == EN.panel_paused_at.format(
        progress="1:15 / 6:31"
    )
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


async def test_the_silent_locale_posts_no_panel() -> None:
    bot, cog = await media_cog()
    bot.config = replace(bot.config, locale="silent")
    player = cog.player(MagicMock(id=GUILD_ID))
    player.current = panel_track()

    await cog.refresh_panel(MagicMock(id=GUILD_ID))

    player.current.channel.send.assert_not_awaited()


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

    await view.stop_button.callback(interaction)  # type: ignore[call-arg]
    assert not player.queue
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
        ["media:stop", "media:queue", "media:lyrics"],
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
