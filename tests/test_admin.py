"""Tests for cogs/admin.py — AdminCog command handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from cogs.admin import AdminCog
from localization import ENGLISH
from utils import database

GUILD_ID = 111111111111111111


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.strings = ENGLISH
    return bot


def _make_interaction(guild_id: int = GUILD_ID) -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    return interaction


# ---------------------------------------------------------------------------
# set_channel
# ---------------------------------------------------------------------------

async def test_set_channel_with_channel_updates_db(db: None) -> None:
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()
    channel = MagicMock()
    channel.id = 777777777777777777
    channel.mention = "#bot-commands"

    await cog.set_channel.callback(cog, interaction, channel=channel)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings is not None
    assert settings["bot_channel_id"] == channel.id
    interaction.response.send_message.assert_awaited_once()


async def test_set_channel_with_none_clears_bot_channel_id(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), bot_channel_id=777777777777777777)
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()

    await cog.set_channel.callback(cog, interaction, channel=None)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings["bot_channel_id"] is None
    interaction.response.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# set_autorole
# ---------------------------------------------------------------------------

async def test_set_autorole_with_role_updates_db(db: None) -> None:
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()
    role = MagicMock()
    role.name = "Member"

    await cog.set_autorole.callback(cog, interaction, role=role)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings["auto_role_name"] == "Member"
    interaction.response.send_message.assert_awaited_once()


async def test_set_autorole_with_none_clears_auto_role_name(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), auto_role_name="Member")
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()

    await cog.set_autorole.callback(cog, interaction, role=None)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings["auto_role_name"] is None
    interaction.response.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# set_threshold
# ---------------------------------------------------------------------------

async def test_set_threshold_writes_warn_threshold_to_db(db: None) -> None:
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()

    await cog.set_threshold.callback(cog, interaction, count=5)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings["warn_threshold"] == 5
    interaction.response.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# set_action
# ---------------------------------------------------------------------------

async def test_set_action_ban_writes_to_db(db: None) -> None:
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()
    action_choice = MagicMock()
    action_choice.value = "ban"

    await cog.set_action.callback(cog, interaction, action=action_choice)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings["warn_action"] == "ban"
    interaction.response.send_message.assert_awaited_once()


async def test_set_action_kick_writes_to_db(db: None) -> None:
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()
    action_choice = MagicMock()
    action_choice.value = "kick"

    await cog.set_action.callback(cog, interaction, action=action_choice)

    settings = await database.get_settings(str(GUILD_ID))
    assert settings["warn_action"] == "kick"
    interaction.response.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

async def test_status_with_no_guild_settings_sends_defaults(db: None) -> None:
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()

    await cog.status.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    msg: str = interaction.response.send_message.call_args[0][0]
    assert "any channel" in msg
    assert "none" in msg


async def test_status_with_settings_reflects_configured_values(db: None) -> None:
    await database.upsert_settings(
        str(GUILD_ID),
        bot_channel_id=777777777777777777,
        auto_role_name="Member",
        warn_threshold=5,
        warn_action="ban",
    )
    cog = AdminCog(_make_bot())
    interaction = _make_interaction()

    await cog.status.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    msg: str = interaction.response.send_message.call_args[0][0]
    assert "Member" in msg
    assert "5" in msg
    assert "ban" in msg
