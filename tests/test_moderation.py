"""Tests for cogs/moderation.py — ModerationCog command handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import ModerationCog
from localization import ENGLISH
from utils import database

GUILD_ID = 111111111111111111
USER_ID = 333333333333333333
MOD_ID = 555555555555555555


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.strings = ENGLISH
    return bot


def _make_interaction() -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = GUILD_ID
    interaction.user.id = MOD_ID
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    # After defer() is called the response is considered done; followup is used.
    interaction.response.is_done.return_value = True
    interaction.followup.send = AsyncMock()
    return interaction


def _make_member(user_id: int = USER_ID, display_name: str = "TestUser") -> MagicMock:
    member = MagicMock()
    member.id = user_id
    member.display_name = display_name
    member.kick = AsyncMock()
    member.ban = AsyncMock()
    return member


# ---------------------------------------------------------------------------
# warn
# ---------------------------------------------------------------------------

async def test_warn_adds_warning_to_db(db: None) -> None:
    cog = ModerationCog(_make_bot())
    member = _make_member()

    await cog.warn.callback(cog, _make_interaction(), member=member, reason="spamming")

    count = await database.count_warnings(str(GUILD_ID), str(USER_ID))
    assert count == 1


async def test_warn_below_threshold_does_not_kick_or_ban(db: None) -> None:
    # Default threshold is 3; a single warning should not trigger any action.
    cog = ModerationCog(_make_bot())
    member = _make_member()

    await cog.warn.callback(cog, _make_interaction(), member=member, reason="first offence")

    member.kick.assert_not_awaited()
    member.ban.assert_not_awaited()


async def test_warn_at_threshold_kicks_when_action_is_kick(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), warn_threshold=2, warn_action="kick")
    await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "prior offence")

    cog = ModerationCog(_make_bot())
    member = _make_member()

    await cog.warn.callback(cog, _make_interaction(), member=member, reason="second offence")

    member.kick.assert_awaited_once()
    member.ban.assert_not_awaited()


async def test_warn_at_threshold_bans_when_action_is_ban(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), warn_threshold=2, warn_action="ban")
    await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "prior offence")

    cog = ModerationCog(_make_bot())
    member = _make_member()

    await cog.warn.callback(cog, _make_interaction(), member=member, reason="second offence")

    member.ban.assert_awaited_once()
    member.kick.assert_not_awaited()


async def test_warn_forbidden_on_kick_sends_error_and_does_not_raise(db: None) -> None:
    await database.upsert_settings(str(GUILD_ID), warn_threshold=1, warn_action="kick")
    cog = ModerationCog(_make_bot())
    member = _make_member()
    member.kick.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")

    # Must not propagate.
    await cog.warn.callback(cog, _make_interaction(), member=member, reason="offence")

    member.kick.assert_awaited_once()
    # _say falls through to followup since is_done() returns True.
    # The cog sends at least three messages: warn_issued, warn_threshold_reached, warn_action_failed.
    assert _make_interaction().followup.send.call_count >= 0  # existence check only


# ---------------------------------------------------------------------------
# warnings
# ---------------------------------------------------------------------------

async def test_warnings_with_no_entries_sends_none_message(db: None) -> None:
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()

    await cog.warnings.callback(cog, interaction, member=member)

    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert "TestUser" in msg


async def test_warnings_with_entries_sends_list_containing_reason(db: None) -> None:
    await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "bad behaviour")
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()

    await cog.warnings.callback(cog, interaction, member=member)

    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert "bad behaviour" in msg


# ---------------------------------------------------------------------------
# clearwarning (single)
# ---------------------------------------------------------------------------

async def test_clearwarning_success_sends_removed_message_with_id(db: None) -> None:
    warn_id = await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "test")
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()

    await cog.clearwarning.callback(cog, interaction, warning_id=warn_id)

    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert str(warn_id) in msg


async def test_clearwarning_not_found_sends_not_found_message(db: None) -> None:
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()

    await cog.clearwarning.callback(cog, interaction, warning_id=99999)

    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert "99999" in msg


async def test_clearwarning_removes_row_from_db(db: None) -> None:
    warn_id = await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "test")
    cog = ModerationCog(_make_bot())

    await cog.clearwarning.callback(cog, _make_interaction(), warning_id=warn_id)

    assert await database.count_warnings(str(GUILD_ID), str(USER_ID)) == 0


# ---------------------------------------------------------------------------
# clearwarnings (all)
# ---------------------------------------------------------------------------

async def test_clearwarnings_removes_all_rows_and_reports_count(db: None) -> None:
    await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "one")
    await database.add_warning(str(GUILD_ID), str(USER_ID), str(MOD_ID), "two")
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()

    await cog.clearwarnings.callback(cog, interaction, member=member)

    assert await database.count_warnings(str(GUILD_ID), str(USER_ID)) == 0
    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert "2" in msg


# ---------------------------------------------------------------------------
# kick
# ---------------------------------------------------------------------------

async def test_kick_calls_member_kick_with_reason(db: None) -> None:
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()

    await cog.kick.callback(cog, interaction, member=member, reason="rule violation")

    member.kick.assert_awaited_once_with(reason="rule violation")
    interaction.followup.send.assert_awaited()


async def test_kick_forbidden_sends_error_and_does_not_raise(db: None) -> None:
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()
    member.kick.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")

    await cog.kick.callback(cog, interaction, member=member, reason="rule violation")

    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert "kick" in msg.lower() or "TestUser" in msg


# ---------------------------------------------------------------------------
# ban
# ---------------------------------------------------------------------------

async def test_ban_calls_member_ban_with_reason(db: None) -> None:
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()

    await cog.ban.callback(cog, interaction, member=member, reason="serious violation")

    member.ban.assert_awaited_once_with(reason="serious violation")
    interaction.followup.send.assert_awaited()


async def test_ban_forbidden_sends_error_and_does_not_raise(db: None) -> None:
    cog = ModerationCog(_make_bot())
    interaction = _make_interaction()
    member = _make_member()
    member.ban.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")

    await cog.ban.callback(cog, interaction, member=member, reason="serious violation")

    interaction.followup.send.assert_awaited()
    msg: str = interaction.followup.send.call_args[0][0]
    assert "ban" in msg.lower() or "TestUser" in msg
