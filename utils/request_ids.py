"""Request IDs, which tie the bot's log lines to the api-* services' lines about the same work.

Each command and panel button runs under its interaction's ID, and each song gets a new one.
The bot's log lines name the ID, and each call to an api-* service sends it as X-Request-ID.
The services log it with each of their lines about that call.
"""

import uuid
from contextvars import ContextVar

import httpx

__all__ = ["HEADER", "current_request_id", "start_request", "tag_request"]

HEADER = "X-Request-ID"

# Each asyncio task gets a copy of this when it starts, so an ID stays with the work that set it.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    """Returns the ID of the work that runs now, or None outside a command or song."""
    return _request_id.get()


def start_request(request_id: str | None = None) -> str:
    """Names the work that runs now, and the tasks that it starts from here on.

    Args:
        request_id: The ID to use, such as an interaction's ID. Without one, a new ID is made.

    Returns:
        The ID now in use.
    """
    value = request_id or uuid.uuid4().hex[:12]
    _request_id.set(value)
    return value


async def tag_request(request: httpx.Request) -> None:
    """An httpx request hook that sends the current request ID to the service."""
    if (request_id := _request_id.get()) is not None:
        request.headers[HEADER] = request_id
