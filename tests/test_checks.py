"""Tests for the in_bot_channel() check in utils/checks.py."""

from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock

import discord

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


def _get_predicate() -> Callable[[discord.Interaction], Awaitable[bool]]:
    """Extracts the raw async predicate from the in_bot_channel() check.

    app_commands.check() stores predicates in __discord_app_commands_checks__ on the callable.
    Unlike ext.commands.check, it sets no .predicate attribute.
    Decorating a throwaway coroutine lets the test pull the predicate back out.
    """

    async def _dummy(interaction: discord.Interaction) -> bool: ...  # noqa: E704

    in_bot_channel()(_dummy)
    return _dummy.__discord_app_commands_checks__[0]


# Every predicate test needs the db fixture, because the predicate reads the guild's settings.


async def test_in_bot_channel_no_settings_returns_true(db: None) -> None:
    interaction = _make_interaction(GUILD_ID, CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True


async def test_in_bot_channel_settings_exist_but_no_channel_configured_returns_true(
    db: None,
) -> None:
    # Row exists but bot_channel_id is NULL (only auto_role_name set).
    await database.upsert_settings(GUILD_ID, auto_role_name="Member")
    interaction = _make_interaction(GUILD_ID, CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True


async def test_in_bot_channel_matching_channel_returns_true(db: None) -> None:
    await database.upsert_settings(GUILD_ID, bot_channel_id=CHANNEL_ID)
    interaction = _make_interaction(GUILD_ID, CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True


async def test_in_bot_channel_wrong_channel_returns_false(db: None) -> None:
    await database.upsert_settings(GUILD_ID, bot_channel_id=CHANNEL_ID)
    interaction = _make_interaction(GUILD_ID, OTHER_CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is False


async def test_in_bot_channel_channel_cleared_returns_true(db: None) -> None:
    # Setting a channel and then clearing it leaves every channel allowed again.
    await database.upsert_settings(GUILD_ID, bot_channel_id=CHANNEL_ID)
    await database.upsert_settings(GUILD_ID, bot_channel_id=None)
    interaction = _make_interaction(GUILD_ID, OTHER_CHANNEL_ID)
    result = await _get_predicate()(interaction)
    assert result is True
