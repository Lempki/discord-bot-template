"""Shared pytest fixtures for the discord-bot-template test suite."""

from collections.abc import AsyncIterator

import pytest

from utils import database


@pytest.fixture
async def db() -> AsyncIterator[None]:
    """Initialise a fresh in-memory database for each test, then tear it down."""
    await database.init(":memory:")
    yield
    await database.close()
