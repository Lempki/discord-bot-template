"""Shared fixtures and fakes for the test suite.

Tests use a real BotApp, which builds without connecting to Discord.
Interactions are mocks that record every reply.
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot import BotApp
from config import Config
from utils import database

GUILD_ID = 111111111111111111


@pytest.fixture
async def db() -> AsyncIterator[None]:
    """Initialise a fresh in-memory database for each test, then tear it down."""
    await database.init(":memory:")
    yield
    await database.close()


@pytest.fixture
def bot() -> BotApp:
    """An offline bot whose fallback language is English."""
    return BotApp(Config(discord_token="test-token", locale="en"))


def make_interaction(
    *,
    guild_id: int | None = GUILD_ID,
    user: Any = None,
    locale: discord.Locale = discord.Locale.american_english,
    deferred: bool = False,
) -> MagicMock:
    """Builds an interaction whose replies are recorded by AsyncMocks.

    Args:
        guild_id: The guild, or None for a direct message.
        user: The member who ran the command. Defaults to a plain mock.
        locale: The user's Discord language.
        deferred: Whether the response counts as already sent, as after defer().
    """
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.guild = None if guild_id is None else MagicMock(id=guild_id)
    interaction.user = user if user is not None else MagicMock(id=555555555555555555)
    interaction.locale = locale
    interaction.extras = {}
    interaction.response.is_done.return_value = deferred
    interaction.response.defer = AsyncMock(
        side_effect=lambda **_: interaction.response.is_done.configure_mock(
            return_value=True
        )
    )
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    return interaction


def sent_messages(interaction: MagicMock) -> list[str]:
    """Returns every message text an interaction sent, as replies or follow-ups, in order."""
    messages: list[str] = []
    for mock in (interaction.response.send_message, interaction.followup.send):
        messages += [call.args[0] for call in mock.call_args_list if call.args]
    return messages
