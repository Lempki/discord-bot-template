"""Tests for the media cog's per-guild player, with the service and voice faked out."""

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from bot import BotApp
from cogs.media import (
    QUEUE_SHOWN,
    GuildPlayer,
    MediaCog,
    Track,
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

    player.enqueue(
        [Track(f"https://a/{n}", "Ada", channel, source="SoundCloud") for n in range(3)]
    )
    await asyncio.wait_for(player._task, timeout=1)  # type: ignore[arg-type]

    assert len(played) == 3
    titles = [call.args[0] for call in channel.send.call_args_list]
    assert titles == [
        EN.now_playing.format(
            title=f"[https://a/{n}](<https://a/{n}>)",
            source="SoundCloud",
            channel="General",
            user="Ada",
        )
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
        return_value=[
            {
                "webpage_url": "https://youtu.be/1",
                "title": "One",
                "duration_seconds": 61,
            },
            {"webpage_url": "https://youtu.be/2", "title": "Two"},
            {"title": "No link, left out"},
        ]
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
