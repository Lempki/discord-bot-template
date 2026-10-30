"""Tests for utils/request_ids.py, which ties the bot's log lines to the services' lines."""

import contextvars

import httpx

from utils.request_ids import HEADER, current_request_id, start_request, tag_request


def test_a_request_takes_a_given_id_or_makes_one() -> None:
    def run() -> tuple[str | None, str, str, str | None]:
        before = current_request_id()
        given = start_request("1234567890")
        made = start_request()
        return before, given, made, current_request_id()

    # A copy of the context keeps the IDs out of the other tests.
    before, given, made, now = contextvars.copy_context().run(run)

    assert before is None
    assert given == "1234567890"
    assert len(made) == 12 and made != given
    assert now == made


async def test_a_call_to_a_service_sends_the_current_id() -> None:
    start_request("1234567890")
    request = httpx.Request("GET", "http://media.test/media/info")

    await tag_request(request)

    assert request.headers[HEADER] == "1234567890"


async def test_a_call_outside_a_request_sends_no_id() -> None:
    # Each async test runs in its own task, which starts without an ID.
    assert current_request_id() is None
    request = httpx.Request("GET", "http://media.test/media/info")

    await tag_request(request)

    assert HEADER not in request.headers
