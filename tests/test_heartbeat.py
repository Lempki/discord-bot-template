"""Tests for utils/heartbeat.py, using a fake HTTP session instead of a real service."""

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from bot import BotApp
from config import Config
from utils.heartbeat import Heartbeat

URL = "https://hc-ping.com/00000000-0000-0000-0000-000000000000"


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


class FakeSession:
    """Answers every request with a fixed status or raises a fixed error."""

    def __init__(self, status: int = 200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.urls: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return FakeResponse(self.status)


def heartbeat(*, connected: bool) -> Heartbeat:
    beat = Heartbeat(MagicMock(), URL)
    beat.connected = connected
    return beat


async def test_report_reaches_the_service_while_connected() -> None:
    session = FakeSession()

    assert await heartbeat(connected=True).report(session)  # type: ignore[arg-type]
    assert session.urls == [URL]


async def test_no_report_while_disconnected() -> None:
    session = FakeSession()

    assert not await heartbeat(connected=False).report(session)  # type: ignore[arg-type]
    assert session.urls == []


@pytest.mark.parametrize(
    "session",
    [
        FakeSession(status=404),
        FakeSession(error=aiohttp.ClientConnectionError("no route")),
        FakeSession(error=TimeoutError()),
    ],
    ids=["error-status", "connection-error", "timeout"],
)
async def test_failed_report_is_logged_and_survived(
    session: FakeSession, caplog: pytest.LogCaptureFixture
) -> None:
    assert not await heartbeat(connected=True).report(session)  # type: ignore[arg-type]
    assert "heartbeat service" in caplog.text
    # The URL works like a password, so it must never reach the log.
    assert URL not in caplog.text


async def test_gateway_events_switch_the_connection_state() -> None:
    bot = MagicMock()
    listeners: dict[str, Any] = {}
    bot.add_listener.side_effect = lambda func, name: listeners.setdefault(name, func)
    beat = Heartbeat(bot, URL)

    await listeners["on_connect"]()
    assert beat.connected
    await listeners["on_disconnect"]()
    assert not beat.connected
    await listeners["on_resumed"]()
    assert beat.connected


async def test_stop_ends_the_background_task() -> None:
    bot = MagicMock()

    async def never_ready() -> None:
        await asyncio.Event().wait()

    # The bot never becomes ready, so the task waits until it is stopped.
    bot.wait_until_ready = never_ready
    beat = Heartbeat(bot, URL)

    beat.start()
    await asyncio.sleep(0)
    await beat.stop()

    assert beat._task is None


async def test_no_report_without_a_url() -> None:
    session = FakeSession()
    beat = Heartbeat(MagicMock(), None)
    beat.connected = True

    assert not await beat.report(session)  # type: ignore[arg-type]
    assert session.urls == []


async def test_loop_refreshes_the_health_file_only_while_connected(
    tmp_path: Path,
) -> None:
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    health_file = tmp_path / "bot-healthy"
    beat = Heartbeat(bot, None, health_file=health_file, health_interval=0.01)

    beat.start()
    await asyncio.sleep(0.05)
    assert not health_file.exists()

    beat.connected = True
    await asyncio.sleep(0.05)
    await beat.stop()
    assert health_file.exists()


def test_refresh_moves_the_health_file_time_forward(tmp_path: Path) -> None:
    health_file = tmp_path / "bot-healthy"
    health_file.touch()
    os.utime(health_file, (0, 0))
    beat = Heartbeat(MagicMock(), None, health_file=health_file)

    beat.refresh_health_file()

    assert health_file.stat().st_mtime > 0


def test_every_bot_has_a_heartbeat() -> None:
    assert isinstance(BotApp(Config(discord_token="t")).heartbeat, Heartbeat)
