"""Tests for utils/voice.py, using a fake voice client instead of a real connection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from utils.voice import VoicePresence


def fake_voice_client(channel_members: list[MagicMock]) -> MagicMock:
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.guild = MagicMock(id=1)
    voice_client.guild.voice_client = voice_client
    voice_client.channel = MagicMock(members=channel_members)
    voice_client.disconnect = AsyncMock()
    voice_client.is_playing.return_value = False
    return voice_client


async def test_play_waits_until_the_source_finishes() -> None:
    presence = VoicePresence(MagicMock())
    voice_client = fake_voice_client([])
    finished = False

    def fake_play(source: object, *, after: object) -> None:
        # The real player calls after() from its own thread once the audio ends.
        asyncio.get_running_loop().call_later(0.05, after, None)  # type: ignore[arg-type]

    voice_client.play.side_effect = fake_play

    async def run() -> None:
        nonlocal finished
        await presence.play(voice_client, MagicMock())
        finished = True

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    assert not finished
    await asyncio.wait_for(task, timeout=1)
    assert finished


async def test_play_raises_the_players_error() -> None:
    presence = VoicePresence(MagicMock())
    voice_client = fake_voice_client([])
    voice_client.play.side_effect = lambda source, *, after: after(
        RuntimeError("ffmpeg died")
    )

    with pytest.raises(RuntimeError, match="ffmpeg died"):
        await presence.play(voice_client, MagicMock())


async def test_leaves_when_the_last_human_leaves() -> None:
    bot_member = MagicMock(bot=True)
    voice_client = fake_voice_client([bot_member])
    presence = VoicePresence(MagicMock())
    leaving = MagicMock(bot=False)
    leaving.guild = voice_client.guild

    await presence._on_voice_state_update(
        leaving, MagicMock(channel=voice_client.channel), MagicMock(channel=None)
    )

    voice_client.disconnect.assert_awaited_once()


async def test_stays_while_a_human_remains() -> None:
    voice_client = fake_voice_client([MagicMock(bot=True), MagicMock(bot=False)])
    presence = VoicePresence(MagicMock())
    leaving = MagicMock(bot=False)
    leaving.guild = voice_client.guild

    await presence._on_voice_state_update(
        leaving, MagicMock(channel=voice_client.channel), MagicMock(channel=None)
    )

    voice_client.disconnect.assert_not_awaited()


async def test_idle_check_leaves_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("utils.voice._CHECK_INTERVAL", 0.01)
    voice_client = fake_voice_client([MagicMock(bot=False)])
    bot = MagicMock(voice_clients=[voice_client])
    presence = VoicePresence(bot, idle_timeout=0.03)
    presence.touch(1)

    task = asyncio.create_task(presence._idle_loop())
    await asyncio.sleep(0.1)
    task.cancel()

    voice_client.disconnect.assert_awaited()
