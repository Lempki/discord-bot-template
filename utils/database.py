"""Per-guild persistent storage for bot settings and moderation data.

The schema is versioned with SQLite's user_version pragma.
init() applies every migration the database has not seen yet, so existing files upgrade in place.
Discord snowflakes are stored as INTEGER.
SQLite integers are 64-bit, so every snowflake fits.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

__all__ = [
    "GuildSettings",
    "WarningRecord",
    "add_warning",
    "close",
    "count_warnings",
    "delete_all_warnings",
    "delete_warning",
    "get_settings",
    "get_warnings",
    "init",
    "upsert_settings",
]

_conn: aiosqlite.Connection | None = None

# Columns that upsert_settings may write.
# Column names are interpolated into SQL, so only these are allowed.
_SETTINGS_COLUMNS = frozenset(
    {
        "bot_channel_id",
        "auto_role_id",
        "auto_role_name",
        "warn_threshold",
        "warn_action",
        "warn_timeout_minutes",
        "automod_escalation",
        "automod_alert_channel_id",
    }
)


@dataclass(frozen=True)
class GuildSettings:
    """The configuration of one guild, with defaults for guilds that never changed anything.

    Attributes:
        guild_id: The guild's snowflake.
        bot_channel_id: The only channel that accepts bot commands, or None for any channel.
        auto_role_id: The role given to new members, or None for no role.
        auto_role_name: A role name from before roles were stored by ID.
            It is resolved to auto_role_id on the next member join.
        warn_threshold: How many warnings trigger warn_action.
        warn_action: "kick", "ban", or "timeout".
        warn_timeout_minutes: How long the timeout warn action lasts, in minutes.
        automod_escalation: "warn" turns every message AutoMod blocks into a warning.
            "none" leaves blocked messages to AutoMod alone.
        automod_alert_channel_id: The channel for AutoMod alerts and escalation reports, or None.
    """

    guild_id: int
    bot_channel_id: int | None = None
    auto_role_id: int | None = None
    auto_role_name: str | None = None
    warn_threshold: int = 3
    warn_action: str = "kick"
    warn_timeout_minutes: int = 60
    automod_escalation: str = "none"
    automod_alert_channel_id: int | None = None


@dataclass(frozen=True)
class WarningRecord:
    """One warning issued to a member.

    Attributes:
        id: The warning's number, unique across all guilds.
        guild_id: The guild the warning belongs to.
        user_id: The warned member.
        moderator_id: The member or bot that issued the warning.
        reason: The reason given, or None.
        created_at: When the warning was issued, in UTC.
    """

    id: int
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str | None
    created_at: datetime


# --- Migrations ---


async def _table_exists(db: aiosqlite.Connection, name: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ) as cur:
        return await cur.fetchone() is not None


async def _migrate_to_1(db: aiosqlite.Connection) -> None:
    """Creates the versioned schema, converting a Phase 1 database if one exists.

    Phase 1 stored guild and user IDs as TEXT and the auto-role by name.
    The tables are rebuilt with INTEGER IDs.
    The role name is kept until a member join resolves it to an ID.
    """
    legacy = await _table_exists(db, "guild_settings")
    if legacy:
        await db.execute("ALTER TABLE guild_settings RENAME TO guild_settings_v0")
        await db.execute("ALTER TABLE warnings RENAME TO warnings_v0")
        await db.execute("DROP INDEX IF EXISTS idx_warnings_guild_user")

    await db.execute(
        """
        CREATE TABLE guild_settings (
            guild_id        INTEGER PRIMARY KEY,
            bot_channel_id  INTEGER,
            auto_role_id    INTEGER,
            auto_role_name  TEXT,
            warn_threshold  INTEGER NOT NULL DEFAULT 3,
            warn_action     TEXT    NOT NULL DEFAULT 'kick'
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE warnings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id        INTEGER NOT NULL,
            user_id         INTEGER NOT NULL,
            moderator_id    INTEGER NOT NULL,
            reason          TEXT,
            created_at      TEXT    NOT NULL
        )
        """
    )
    await db.execute(
        "CREATE INDEX idx_warnings_guild_user ON warnings (guild_id, user_id)"
    )

    if legacy:
        await db.execute(
            """
            INSERT INTO guild_settings
                (guild_id, bot_channel_id, auto_role_name, warn_threshold, warn_action)
            SELECT CAST(guild_id AS INTEGER), bot_channel_id, auto_role_name,
                   warn_threshold, warn_action
            FROM guild_settings_v0
            """
        )
        await db.execute(
            """
            INSERT INTO warnings (id, guild_id, user_id, moderator_id, reason, created_at)
            SELECT id, CAST(guild_id AS INTEGER), CAST(user_id AS INTEGER),
                   CAST(moderator_id AS INTEGER), reason, created_at
            FROM warnings_v0
            """
        )
        await db.execute("DROP TABLE guild_settings_v0")
        await db.execute("DROP TABLE warnings_v0")


async def _migrate_to_2(db: aiosqlite.Connection) -> None:
    """Adds the timeout warn action and the AutoMod settings."""
    await db.execute(
        "ALTER TABLE guild_settings "
        "ADD COLUMN warn_timeout_minutes INTEGER NOT NULL DEFAULT 60"
    )
    await db.execute(
        "ALTER TABLE guild_settings "
        "ADD COLUMN automod_escalation TEXT NOT NULL DEFAULT 'none'"
    )
    await db.execute(
        "ALTER TABLE guild_settings ADD COLUMN automod_alert_channel_id INTEGER"
    )


# Each entry upgrades the schema by one version. Append new migrations and never edit old ones.
_MIGRATIONS: list[Callable[[aiosqlite.Connection], Awaitable[None]]] = [
    _migrate_to_1,
    _migrate_to_2,
]


async def _migrate(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA user_version") as cur:
        row = await cur.fetchone()
    version = row[0] if row else 0
    for target, migration in enumerate(_MIGRATIONS[version:], start=version + 1):
        # Each migration commits together with its version bump.
        # A crash therefore never leaves a half-applied step behind.
        await db.execute("BEGIN")
        try:
            await migration(db)
            await db.execute(f"PRAGMA user_version = {target}")
        except BaseException:
            await db.rollback()
            raise
        await db.commit()


# --- Lifecycle ---


async def init(db_path: str | Path) -> None:
    """Opens the database, creating its directory if needed, and applies pending migrations.

    Args:
        db_path: The SQLite file, or ":memory:" for a throwaway database.
    """
    global _conn
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(db_path, isolation_level=None)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _migrate(_conn)


async def close() -> None:
    """Closes the database connection if one is open."""
    global _conn
    if _conn:
        await _conn.close()
        _conn = None


def _conn_or_raise() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("The database is not initialised. Call init() first.")
    return _conn


# --- Settings ---


async def get_settings(guild_id: int) -> GuildSettings:
    """Returns a guild's settings, or the defaults when the guild has none stored."""
    async with _conn_or_raise().execute(
        "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
    ) as cur:
        row = await cur.fetchone()
    return GuildSettings(**dict(row)) if row else GuildSettings(guild_id=guild_id)


async def upsert_settings(guild_id: int, **fields: Any) -> None:
    """Creates or updates only the given settings of a guild.

    Args:
        guild_id: The guild to update.
        **fields: Column names and their new values. None clears a nullable setting.

    Raises:
        ValueError: If a field is not a known settings column.
    """
    unknown = set(fields) - _SETTINGS_COLUMNS
    if unknown:
        raise ValueError(f"Unknown settings column(s): {', '.join(sorted(unknown))}.")
    if not fields:
        return
    columns = list(fields)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{column} = excluded.{column}" for column in columns)
    db = _conn_or_raise()
    await db.execute(
        f"INSERT INTO guild_settings (guild_id, {', '.join(columns)}) "
        f"VALUES (?, {placeholders}) "
        f"ON CONFLICT (guild_id) DO UPDATE SET {updates}",
        (guild_id, *fields.values()),
    )


# --- Warnings ---


def _to_warning(row: aiosqlite.Row) -> WarningRecord:
    data = dict(row)
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return WarningRecord(**data)


async def add_warning(
    guild_id: int, user_id: int, moderator_id: int, reason: str | None
) -> int:
    """Records a warning and returns its ID."""
    cur = await _conn_or_raise().execute(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, moderator_id, reason, datetime.now(UTC).isoformat()),
    )
    if cur.lastrowid is None:
        raise RuntimeError("SQLite did not report the new warning's ID.")
    return cur.lastrowid


async def get_warnings(guild_id: int, user_id: int) -> list[WarningRecord]:
    """Returns a member's warnings in one guild, oldest first."""
    async with _conn_or_raise().execute(
        "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at ASC",
        (guild_id, user_id),
    ) as cur:
        rows = await cur.fetchall()
    return [_to_warning(row) for row in rows]


async def count_warnings(guild_id: int, user_id: int) -> int:
    """Returns how many warnings a member has in one guild."""
    async with _conn_or_raise().execute(
        "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def delete_warning(guild_id: int, warning_id: int) -> bool:
    """Deletes one warning, but only if it belongs to the given guild.

    Returns:
        True if a warning was deleted, False if no such warning exists in that guild.
    """
    cur = await _conn_or_raise().execute(
        "DELETE FROM warnings WHERE id = ? AND guild_id = ?", (warning_id, guild_id)
    )
    return cur.rowcount > 0


async def delete_all_warnings(guild_id: int, user_id: int) -> int:
    """Deletes every warning of a member in one guild and returns how many were deleted."""
    cur = await _conn_or_raise().execute(
        "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    )
    return cur.rowcount
