"""Tests for utils/database.py against in-memory and on-disk SQLite databases."""

import sqlite3
from datetime import UTC
from pathlib import Path

import pytest

from utils import database
from utils.database import GuildSettings

GUILD = 111111111111111111
GUILD_B = 222222222222222222
USER = 333333333333333333
USER_B = 444444444444444444
MOD = 555555555555555555


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


async def test_unknown_guild_gets_default_settings(db: None) -> None:
    assert await database.get_settings(GUILD) == GuildSettings(guild_id=GUILD)


async def test_upsert_inserts_then_updates(db: None) -> None:
    await database.upsert_settings(GUILD, bot_channel_id=1)
    await database.upsert_settings(GUILD, bot_channel_id=2)
    assert (await database.get_settings(GUILD)).bot_channel_id == 2


async def test_upsert_changes_only_given_fields(db: None) -> None:
    await database.upsert_settings(GUILD, warn_threshold=5, warn_action="ban")
    await database.upsert_settings(GUILD, bot_channel_id=7)
    settings = await database.get_settings(GUILD)
    assert (settings.warn_threshold, settings.warn_action, settings.bot_channel_id) == (
        5,
        "ban",
        7,
    )


async def test_upsert_can_clear_nullable_fields(db: None) -> None:
    await database.upsert_settings(GUILD, bot_channel_id=7, auto_role_id=8)
    await database.upsert_settings(GUILD, bot_channel_id=None, auto_role_id=None)
    settings = await database.get_settings(GUILD)
    assert settings.bot_channel_id is None
    assert settings.auto_role_id is None


async def test_upsert_rejects_unknown_columns(db: None) -> None:
    # Column names are interpolated into SQL, so anything outside the whitelist must fail.
    with pytest.raises(ValueError, match="Unknown settings column"):
        await database.upsert_settings(GUILD, **{"guild_id = 0; --": 1})


async def test_snowflakes_round_trip_as_integers(db: None) -> None:
    big = 2**63 - 1
    await database.upsert_settings(big, auto_role_id=big)
    assert (await database.get_settings(big)).auto_role_id == big


async def test_settings_are_isolated_per_guild(db: None) -> None:
    await database.upsert_settings(GUILD, warn_threshold=9)
    assert (await database.get_settings(GUILD_B)).warn_threshold == 3


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


async def test_add_and_get_warnings(db: None) -> None:
    first = await database.add_warning(GUILD, USER, MOD, "spam")
    second = await database.add_warning(GUILD, USER, MOD, None)
    warnings = await database.get_warnings(GUILD, USER)
    assert [w.id for w in warnings] == [first, second]
    assert warnings[0].reason == "spam"
    assert warnings[1].reason is None
    assert warnings[0].moderator_id == MOD
    assert warnings[0].created_at.tzinfo == UTC


async def test_warnings_are_scoped_to_guild_and_user(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "a")
    await database.add_warning(GUILD, USER_B, MOD, "b")
    await database.add_warning(GUILD_B, USER, MOD, "c")
    assert await database.count_warnings(GUILD, USER) == 1
    assert [w.reason for w in await database.get_warnings(GUILD_B, USER)] == ["c"]


async def test_delete_warning_only_within_its_guild(db: None) -> None:
    warning_id = await database.add_warning(GUILD_B, USER, MOD, "elsewhere")
    assert await database.delete_warning(GUILD, warning_id) is False
    assert await database.count_warnings(GUILD_B, USER) == 1
    assert await database.delete_warning(GUILD_B, warning_id) is True
    assert await database.count_warnings(GUILD_B, USER) == 0


async def test_delete_all_warnings_reports_count_and_spares_others(db: None) -> None:
    await database.add_warning(GUILD, USER, MOD, "a")
    await database.add_warning(GUILD, USER, MOD, "b")
    await database.add_warning(GUILD, USER_B, MOD, "c")
    assert await database.delete_all_warnings(GUILD, USER) == 2
    assert await database.count_warnings(GUILD, USER_B) == 1


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


async def test_functions_fail_clearly_before_init() -> None:
    with pytest.raises(RuntimeError, match="init"):
        await database.get_settings(GUILD)


async def test_init_creates_missing_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "bot.db"
    await database.init(path)
    await database.close()
    assert path.is_file()


def _user_version(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


async def test_fresh_database_is_at_latest_version(tmp_path: Path) -> None:
    path = tmp_path / "bot.db"
    await database.init(path)
    await database.close()
    assert _user_version(path) == len(database._MIGRATIONS)


def _create_phase1_database(path: Path) -> None:
    """Writes a database with the original schema, where IDs were TEXT and roles were names."""
    with sqlite3.connect(path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE guild_settings (
                guild_id TEXT PRIMARY KEY, bot_channel_id INTEGER, auto_role_name TEXT,
                warn_threshold INTEGER NOT NULL DEFAULT 3,
                warn_action TEXT NOT NULL DEFAULT 'kick'
            );
            CREATE TABLE warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL, moderator_id TEXT NOT NULL, reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_warnings_guild_user ON warnings (guild_id, user_id);
            INSERT INTO guild_settings VALUES ('{GUILD}', 42, 'Member', 5, 'ban');
            INSERT INTO warnings VALUES
                (7, '{GUILD}', '{USER}', '{MOD}', 'old', '2026-01-02T03:04:05+00:00');
            """
        )


async def test_phase1_database_is_upgraded_in_place(tmp_path: Path) -> None:
    path = tmp_path / "bot.db"
    _create_phase1_database(path)

    await database.init(path)
    try:
        settings = await database.get_settings(GUILD)
        warnings = await database.get_warnings(GUILD, USER)
    finally:
        await database.close()

    assert settings == GuildSettings(
        guild_id=GUILD,
        bot_channel_id=42,
        auto_role_name="Member",
        warn_threshold=5,
        warn_action="ban",
    )
    assert [(w.id, w.user_id, w.moderator_id, w.reason) for w in warnings] == [
        (7, USER, MOD, "old")
    ]
    assert _user_version(path) == len(database._MIGRATIONS)


async def test_reopening_an_upgraded_database_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "bot.db"
    _create_phase1_database(path)
    await database.init(path)
    await database.close()

    await database.init(path)
    try:
        assert await database.count_warnings(GUILD, USER) == 1
    finally:
        await database.close()
