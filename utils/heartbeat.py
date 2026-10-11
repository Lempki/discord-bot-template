"""Tells an outside heartbeat service that the bot is online, so its owner hears when it is not.

A service such as healthchecks.io expects a request every few minutes.
When the requests stop, it alerts the owner by email or in Discord.
That covers a crashed or stuck bot, and also a computer that shut down.
Nothing on a computer that is off can report that itself.
"""

import asyncio
import logging
from urllib.parse import urlsplit

import aiohttp
from discord.ext import commands

__all__ = ["HEARTBEAT_INTERVAL_SECONDS", "Heartbeat"]

log = logging.getLogger(__name__)

# The service's expected period should be this long, with a grace time of a few minutes on top.
HEARTBEAT_INTERVAL_SECONDS = 300

REQUEST_TIMEOUT_SECONDS = 10


class Heartbeat:
    """Sends a request to the heartbeat URL at a fixed interval while the bot is connected.

    The bot tracks its gateway connection through Discord's connect, resume, and disconnect events.
    A bot that lost its connection therefore stops sending, just like one that crashed.

    Args:
        bot: The bot whose connection decides whether a request is sent.
        url: The service's URL for this bot. It works like a password, so it is never logged.
        interval: The seconds between requests.
    """

    def __init__(
        self,
        bot: commands.Bot,
        url: str,
        interval: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._bot = bot
        self._url = url
        self._interval = interval
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
        """Starts sending in the background."""
        host = urlsplit(self._url).hostname or "the heartbeat service"
        log.info(
            f"Reporting to {host} every {self._interval // 60:g} minutes while online."
        )
        self._task = asyncio.create_task(self._run(), name="heartbeat")

    async def stop(self) -> None:
        """Stops sending. The service then alerts after its grace time, as for any outage."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        await self._bot.wait_until_ready()
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                await self.beat(session)
                await asyncio.sleep(self._interval)

    async def beat(self, session: aiohttp.ClientSession) -> bool:
        """Sends one request when the bot is connected.

        A failed request is only logged, because the next one may work.

        Returns:
            Whether the service received the request.
        """
        if not self.connected:
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
