"""Per-guild persistent storage for bot settings and moderation data."""
from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone

_conn: aiosqlite.Connection | None = None


async def init(db_path: str) -> None:
    global _conn
    _conn = await aiosqlite.connect(db_path)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.executescript("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id        TEXT PRIMARY KEY,
            bot_channel_id  INTEGER,
            auto_role_name  TEXT,
            warn_threshold  INTEGER NOT NULL DEFAULT 3,
            warn_action     TEXT    NOT NULL DEFAULT 'kick'
        );
        CREATE TABLE IF NOT EXISTS warnings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id        TEXT    NOT NULL,
            user_id         TEXT    NOT NULL,
            moderator_id    TEXT    NOT NULL,
            reason          TEXT,
            created_at      TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_warnings_guild_user
            ON warnings (guild_id, user_id);
    """)
    await _conn.commit()


async def close() -> None:
    global _conn
    if _conn:
        await _conn.close()
        _conn = None


def _conn_or_raise() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("database not initialised — call init() first")
    return _conn


# --- Settings ---

async def get_settings(guild_id: str) -> dict | None:
    async with _conn_or_raise().execute(
        "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_settings(guild_id: str, **fields) -> None:
    """Create or update only the provided fields for a guild."""
    db = _conn_or_raise()
    existing = await get_settings(guild_id)
    if existing is None:
        await db.execute(
            "INSERT INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
        )
    for key, value in fields.items():
        await db.execute(
            f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?",
            (value, guild_id),
        )
    await db.commit()


# --- Warnings ---

async def add_warning(guild_id: str, user_id: str, moderator_id: str, reason: str | None) -> int:
    db = _conn_or_raise()
    cur = await db.execute(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?,?,?,?,?)",
        (guild_id, user_id, moderator_id, reason, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()
    return cur.lastrowid


async def get_warnings(guild_id: str, user_id: str) -> list[dict]:
    async with _conn_or_raise().execute(
        "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at ASC",
        (guild_id, user_id),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def count_warnings(guild_id: str, user_id: str) -> int:
    async with _conn_or_raise().execute(
        "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ) as cur:
        return (await cur.fetchone())[0]


async def delete_warning(warning_id: int) -> bool:
    db = _conn_or_raise()
    cur = await db.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
    await db.commit()
    return cur.rowcount > 0


async def delete_all_warnings(guild_id: str, user_id: str) -> int:
    db = _conn_or_raise()
    cur = await db.execute(
        "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    )
    await db.commit()
    return cur.rowcount
