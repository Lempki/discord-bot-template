"""Tests for utils/checks.py — in_bot_channel() predicate logic."""
from __future__ import annotations

from unittest.mock import MagicMock

from utils import database
from utils.checks import in_bot_channel

GUILD_ID = 111111111111111111
CHANNEL_ID = 777777777777777777
OTHER_CHANNEL_ID = 888888888888888888


def _make_interaction(guild_id: int, channel_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.channel_id = channel_id
    return interaction


def _get_predicate():
    """Extract the raw async predicate from the check decorator."""
    return in_bot_channel().predicate


# Every predicate test needs a live DB connection because the predicate calls
# database.get_settings(), which requires _conn to be initialised.

async def test_in_bot_channel_no_settings_returns_true(db: None) -> None:
    interaction = _make_interaction(GUILD_ID, CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True


async def test_in_bot_channel_settings_exist_but_no_channel_configured_returns_true(db: None) -> None:
    # Row exists but bot_channel_id is NULL (only auto_role_name set).
    await database.upsert_settings(str(GUILD_ID), auto_role_name="Member")
    interaction = _make_interaction(GUILD_ID, CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True


async def test_in_bot_channel_matching_channel_returns_true(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), bot_channel_id=CHANNEL_ID)
    interaction = _make_interaction(GUILD_ID, CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True


async def test_in_bot_channel_wrong_channel_returns_false(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), bot_channel_id=CHANNEL_ID)
    interaction = _make_interaction(GUILD_ID, OTHER_CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is False


async def test_in_bot_channel_channel_cleared_returns_true(db: None) -> None:
    # Set a channel, then clear it — should be unrestricted again.
    await database.upsert_settings(str(GUILD_ID), bot_channel_id=CHANNEL_ID)
    await database.upsert_settings(str(GUILD_ID), bot_channel_id=None)
    interaction = _make_interaction(GUILD_ID, OTHER_CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True
