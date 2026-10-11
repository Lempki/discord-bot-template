"""Shows that the bot is online, both to Docker and to an outside heartbeat service.

While the bot is connected to Discord, it refreshes a health file every 30 seconds.
The Docker image's health check reads the file's age.
So Docker and the run script notice a stuck bot or a lost connection, not only a crash.

With HEARTBEAT_URL set, the bot also reports to a service such as healthchecks.io.
When the reports stop, the service alerts the owner by email or in Discord.
That covers a crashed or stuck bot, and also a computer that shut down.
Nothing on a computer that is off can report that itself.
"""

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from discord.ext import commands

__all__ = [
    "HEALTH_FILE",
    "HEALTH_INTERVAL_SECONDS",
    "HEARTBEAT_INTERVAL_SECONDS",
    "Heartbeat",
]

log = logging.getLogger(__name__)

# The Dockerfile's health check reads this file, which is /tmp/bot-healthy in the image.
HEALTH_FILE = Path(tempfile.gettempdir()) / "bot-healthy"

# The health check counts the file as stale after 90 seconds, which leaves room for two misses.
HEALTH_INTERVAL_SECONDS = 30

# The service's expected period should be this long, with a grace time of a few minutes on top.
HEARTBEAT_INTERVAL_SECONDS = 300

REQUEST_TIMEOUT_SECONDS = 10


class Heartbeat:
    """Refreshes the health file and reports to the heartbeat service while the bot is connected.

    The bot tracks its gateway connection through Discord's connect, resume, and disconnect events.
    A bot that lost its connection therefore stops both signals, just like one that crashed.

    Args:
        bot: The bot whose connection decides whether the signals are sent.
        url: The service's URL for this bot, or None without a service.
            It works like a password, so it is never logged.
        health_file: The file that the health check reads.
        interval: The seconds between requests to the service.
        health_interval: The seconds between refreshes of the health file.
    """

    def __init__(
        self,
        bot: commands.Bot,
        url: str | None,
        *,
        health_file: Path = HEALTH_FILE,
        interval: float = HEARTBEAT_INTERVAL_SECONDS,
        health_interval: float = HEALTH_INTERVAL_SECONDS,
    ) -> None:
        self._bot = bot
        self._url = url
        self._health_file = health_file
        self._interval = interval
        self._health_interval = health_interval
        self._task: asyncio.Task[None] | None = None
        self.connected = False
        bot.add_listener(self._on_connected, "on_connect")
        bot.add_listener(self._on_connected, "on_resumed")
        bot.add_listener(self._on_disconnected, "on_disconnect")

    async def _on_connected(self) -> None:
        self.connected = True

    async def _on_disconnected(self) -> None:
        self.connected = False

    def start(self) -> None:
        """Starts the signals in the background."""
        if self._url:
            host = urlsplit(self._url).hostname or "the heartbeat service"
            log.info(
                f"Reporting to {host} every {self._interval // 60:g} minutes while online."
            )
        self._task = asyncio.create_task(self._run(), name="heartbeat")

    async def stop(self) -> None:
        """Stops the signals. The service then alerts after its grace time, as for any outage."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        await self._bot.wait_until_ready()
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            reported_at: float | None = None
            while True:
                if self.connected:
                    self.refresh_health_file()
                    now = time.monotonic()
                    due = reported_at is None or now - reported_at >= self._interval
                    if self._url and due:
                        # A failed request waits for the next interval too, so it never floods.
                        await self.report(session)
                        reported_at = now
                await asyncio.sleep(self._health_interval)

    def refresh_health_file(self) -> None:
        """Sets the health file's time to now, creating the file when needed."""
        try:
            self._health_file.touch()
        except OSError as error:
            log.warning(
                f"Could not refresh the health file {self._health_file}: {error}"
            )

    async def report(self, session: aiohttp.ClientSession) -> bool:
        """Sends one request to the heartbeat service when the bot is connected.

        A failed request is only logged, because the next one may work.

        Returns:
            Whether the service received the request.
        """
        if not self.connected or not self._url:
            return False
        try:
            async with session.get(self._url) as response:
                if response.status < 400:
                    return True
                log.warning(f"The heartbeat service answered {response.status}.")
        except (aiohttp.ClientError, TimeoutError) as error:
            # Some errors quote the whole URL, which must stay out of the log.
            # So only the kind of error shows.
            log.warning(
                f"Could not reach the heartbeat service: {type(error).__name__}"
            )
        return False
