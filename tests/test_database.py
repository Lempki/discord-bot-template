"""Tests for utils/database.py — all CRUD helpers against an in-memory DB."""
from __future__ import annotations

import pytest

from utils import database

GUILD = "111111111111111111"
GUILD_B = "222222222222222222"
USER = "333333333333333333"
USER_B = "444444444444444444"
MOD = "555555555555555555"


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

async def test_get_settings_unknown_guild_returns_none(db: None) -> None:
    result = await database.get_settings(GUILD)
    assert result is None


async def test_upsert_settings_inserts_new_row(db: None) -> None:
    await database.upsert_settings(GUILD, bot_channel_id=123456789)
    result = await database.get_settings(GUILD)
    assert result is not None
    assert result["bot_channel_id"] == 123456789


async def test_upsert_settings_updates_existing_row(db: None) -> None:
    await database.upsert_settings(GUILD, bot_channel_id=100)
    await database.upsert_settings(GUILD, bot_channel_id=200)
    result = await database.get_settings(GUILD)
    assert result["bot_channel_id"] == 200


async def test_upsert_settings_leaves_other_fields_at_schema_defaults(db: None) -> None:
    await database.upsert_settings(GUILD, bot_channel_id=100)
    result = await database.get_settings(GUILD)
    assert result["warn_threshold"] == 3
    assert result["warn_action"] == "kick"
    assert result["auto_role_name"] is None


async def test_upsert_settings_partial_update_preserves_other_fields(db: None) -> None:
    await database.upsert_settings(GUILD, warn_threshold=5, warn_action="ban")
    await database.upsert_settings(GUILD, bot_channel_id=999)
    result = await database.get_settings(GUILD)
    assert result["warn_threshold"] == 5
    assert result["warn_action"] == "ban"
    assert result["bot_channel_id"] == 999


async def test_upsert_settings_auto_role_name_round_trips(db: None) -> None:
    await database.upsert_settings(GUILD, auto_role_name="Member")
    result = await database.get_settings(GUILD)
    assert result["auto_role_name"] == "Member"


async def test_upsert_settings_can_clear_auto_role_name(db: None) -> None:
    await database.upsert_settings(GUILD, auto_role_name="Member")
    await database.upsert_settings(GUILD, auto_role_name=None)
    result = await database.get_settings(GUILD)
    assert result["auto_role_name"] is None


async def test_upsert_settings_can_clear_bot_channel_id(db: None) -> None:
    await database.upsert_settings(GUILD, bot_channel_id=777)
    await database.upsert_settings(GUILD, bot_channel_id=None)
    result = await database.get_settings(GUILD)
    assert result["bot_channel_id"] is None


# ---------------------------------------------------------------------------
# Warning helpers
# ---------------------------------------------------------------------------

async def test_get_warnings_empty_for_fresh_guild_user(db: None) -> None:
    rows = await database.get_warnings(GUILD, USER)
    assert rows == []


async def test_count_warnings_zero_for_fresh_guild_user(db: None) -> None:
    count = await database.count_warnings(GUILD, USER)
    assert count == 0


async def test_add_warning_returns_integer_id(db: None) -> None:
    warn_id = await database.add_warning(GUILD, USER, MOD, "spamming")
    assert isinstance(warn_id, int)
    assert warn_id > 0


async def test_add_warning_ids_are_unique(db: None) -> None:
    id_1 = await database.add_warning(GUILD, USER, MOD, "first")
    id_2 = await database.add_warning(GUILD, USER, MOD, "second")
    assert id_1 != id_2


async def test_count_warnings_increments_after_add(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "first offence")
    await database.add_warning(GUILD, USER, MOD, "second offence")
    count = await database.count_warnings(GUILD, USER)
    assert count == 2


async def test_get_warnings_returns_added_warnings(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "bad behaviour")
    rows = await database.get_warnings(GUILD, USER)
    assert len(rows) == 1
    assert rows[0]["reason"] == "bad behaviour"
    assert rows[0]["guild_id"] == GUILD
    assert rows[0]["user_id"] == USER
    assert rows[0]["moderator_id"] == MOD


async def test_get_warnings_ordered_by_created_at(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "first")
    await database.add_warning(GUILD, USER, MOD, "second")
    rows = await database.get_warnings(GUILD, USER)
    assert rows[0]["reason"] == "first"
    assert rows[1]["reason"] == "second"


async def test_add_warning_with_none_reason(db: None) -> None:
    warn_id = await database.add_warning(GUILD, USER, MOD, None)
    rows = await database.get_warnings(GUILD, USER)
    assert isinstance(warn_id, int)
    assert rows[0]["reason"] is None


async def test_delete_warning_returns_true_on_success(db: None) -> None:
    warn_id = await database.add_warning(GUILD, USER, MOD, "test")
    deleted = await database.delete_warning(warn_id)
    assert deleted is True


async def test_delete_warning_returns_false_for_nonexistent_id(db: None) -> None:
    deleted = await database.delete_warning(99999)
    assert deleted is False


async def test_delete_warning_removes_row(db: None) -> None:
    warn_id = await database.add_warning(GUILD, USER, MOD, "test")
    await database.delete_warning(warn_id)
    rows = await database.get_warnings(GUILD, USER)
    assert rows == []


async def test_delete_all_warnings_returns_count(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "one")
    await database.add_warning(GUILD, USER, MOD, "two")
    count = await database.delete_all_warnings(GUILD, USER)
    assert count == 2


async def test_delete_all_warnings_clears_rows(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "one")
    await database.delete_all_warnings(GUILD, USER)
    rows = await database.get_warnings(GUILD, USER)
    assert rows == []


async def test_delete_all_warnings_returns_zero_when_none_exist(db: None) -> None:
    count = await database.delete_all_warnings(GUILD, USER)
    assert count == 0


async def test_warnings_isolated_between_guilds(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "guild A warning")
    rows_b = await database.get_warnings(GUILD_B, USER)
    assert rows_b == []


async def test_count_warnings_isolated_between_guilds(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "guild A warning")
    count_b = await database.count_warnings(GUILD_B, USER)
    assert count_b == 0


async def test_warnings_isolated_between_users(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "user A warning")
    rows_b = await database.get_warnings(GUILD, USER_B)
    assert rows_b == []


async def test_delete_all_warnings_only_affects_target_user(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "user A warning")
    await database.add_warning(GUILD, USER_B, MOD, "user B warning")
    await database.delete_all_warnings(GUILD, USER)
    rows_b = await database.get_warnings(GUILD, USER_B)
    assert len(rows_b) == 1
