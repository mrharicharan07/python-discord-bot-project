"""
database.py - shared storage for all per-server bot data.
"""

import sqlite3

from config import (
    DEFAULT_MAX_WARNINGS,
    DEFAULT_MUTE_MINUTES,
    DEFAULT_PREFIX,
    DEFAULT_WARN_THRESHOLD,
)


DB_FILE = "zoro.db"


DEFAULT_GUILD_CONFIG = {
    "log_channel_id": None,
    "prefix": DEFAULT_PREFIX,
    "warn_threshold": DEFAULT_WARN_THRESHOLD,
    "mute_minutes": DEFAULT_MUTE_MINUTES,
    "max_warnings": DEFAULT_MAX_WARNINGS,
    "automod_enabled": True,
    "ai_replies": True,
    "anti_raid_enabled": True,
    "anti_nuke_enabled": True,
    "anti_link_enabled": True,
    "security_logs_enabled": True,
    "raid_limit": 5,
    "raid_window_seconds": 10,
    "nuke_limit": 2,
    "channel_create_limit": 4,
    "role_create_limit": 3,
}


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns(cursor: sqlite3.Cursor, table: str, columns: dict[str, str]):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def setup_database():
    conn = get_connection()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id              TEXT PRIMARY KEY,
            log_channel_id        TEXT,
            prefix                TEXT DEFAULT '!',
            warn_threshold        INTEGER DEFAULT 60,
            mute_minutes          INTEGER DEFAULT 5,
            max_warnings          INTEGER DEFAULT 3,
            automod_enabled       INTEGER DEFAULT 1,
            ai_replies            INTEGER DEFAULT 1,
            anti_raid_enabled     INTEGER DEFAULT 1,
            anti_nuke_enabled     INTEGER DEFAULT 1,
            anti_link_enabled     INTEGER DEFAULT 1,
            security_logs_enabled INTEGER DEFAULT 1,
            raid_limit            INTEGER DEFAULT 5,
            raid_window_seconds   INTEGER DEFAULT 10,
            nuke_limit            INTEGER DEFAULT 2,
            channel_create_limit  INTEGER DEFAULT 4,
            role_create_limit     INTEGER DEFAULT 3
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS whitelist (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id  TEXT NOT NULL,
            UNIQUE(guild_id, user_id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS warnings (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id  TEXT NOT NULL,
            count    INTEGER DEFAULT 0,
            UNIQUE(guild_id, user_id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_words (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            word     TEXT NOT NULL,
            UNIQUE(guild_id, word)
        )
        """
    )

    _ensure_columns(
        c,
        "guild_config",
        {
            "max_warnings": "INTEGER DEFAULT 3",
            "automod_enabled": "INTEGER DEFAULT 1",
            "ai_replies": "INTEGER DEFAULT 1",
            "anti_raid_enabled": "INTEGER DEFAULT 1",
            "anti_nuke_enabled": "INTEGER DEFAULT 1",
            "anti_link_enabled": "INTEGER DEFAULT 1",
            "security_logs_enabled": "INTEGER DEFAULT 1",
            "raid_limit": "INTEGER DEFAULT 5",
            "raid_window_seconds": "INTEGER DEFAULT 10",
            "nuke_limit": "INTEGER DEFAULT 2",
            "channel_create_limit": "INTEGER DEFAULT 4",
            "role_create_limit": "INTEGER DEFAULT 3",
        },
    )
    conn.commit()
    conn.close()
    print("[DB] Tables ready.")


def _normalize_config(data: dict) -> dict:
    for key in (
        "automod_enabled",
        "ai_replies",
        "anti_raid_enabled",
        "anti_nuke_enabled",
        "anti_link_enabled",
        "security_logs_enabled",
    ):
        data[key] = bool(data.get(key, 1))
    return data


def get_guild_config(guild_id: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return _normalize_config(dict(row))
    return _normalize_config({"guild_id": guild_id, **DEFAULT_GUILD_CONFIG})


def ensure_guild(guild_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR IGNORE INTO guild_config (
            guild_id,
            log_channel_id,
            prefix,
            warn_threshold,
            mute_minutes,
            max_warnings,
            automod_enabled,
            ai_replies,
            anti_raid_enabled,
            anti_nuke_enabled,
            anti_link_enabled,
            security_logs_enabled,
            raid_limit,
            raid_window_seconds,
            nuke_limit,
            channel_create_limit,
            role_create_limit
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            DEFAULT_GUILD_CONFIG["log_channel_id"],
            DEFAULT_GUILD_CONFIG["prefix"],
            DEFAULT_GUILD_CONFIG["warn_threshold"],
            DEFAULT_GUILD_CONFIG["mute_minutes"],
            DEFAULT_GUILD_CONFIG["max_warnings"],
            1,
            1,
            1,
            1,
            1,
            1,
            DEFAULT_GUILD_CONFIG["raid_limit"],
            DEFAULT_GUILD_CONFIG["raid_window_seconds"],
            DEFAULT_GUILD_CONFIG["nuke_limit"],
            DEFAULT_GUILD_CONFIG["channel_create_limit"],
            DEFAULT_GUILD_CONFIG["role_create_limit"],
        ),
    )
    conn.commit()
    conn.close()


def _update_guild_config(guild_id: str, field: str, value):
    ensure_guild(guild_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE guild_config SET {field} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()


def set_log_channel(guild_id: str, channel_id: str):
    _update_guild_config(guild_id, "log_channel_id", channel_id)


def set_prefix(guild_id: str, prefix: str):
    _update_guild_config(guild_id, "prefix", prefix)


def set_warn_threshold(guild_id: str, threshold: int):
    _update_guild_config(guild_id, "warn_threshold", threshold)


def set_mute_minutes(guild_id: str, minutes: int):
    _update_guild_config(guild_id, "mute_minutes", minutes)


def set_max_warnings(guild_id: str, total: int):
    _update_guild_config(guild_id, "max_warnings", total)


def set_automod_enabled(guild_id: str, enabled: bool):
    _update_guild_config(guild_id, "automod_enabled", 1 if enabled else 0)


def set_ai_replies_enabled(guild_id: str, enabled: bool):
    _update_guild_config(guild_id, "ai_replies", 1 if enabled else 0)


def set_anti_raid_enabled(guild_id: str, enabled: bool):
    _update_guild_config(guild_id, "anti_raid_enabled", 1 if enabled else 0)


def set_anti_nuke_enabled(guild_id: str, enabled: bool):
    _update_guild_config(guild_id, "anti_nuke_enabled", 1 if enabled else 0)


def set_anti_link_enabled(guild_id: str, enabled: bool):
    _update_guild_config(guild_id, "anti_link_enabled", 1 if enabled else 0)


def set_security_logs_enabled(guild_id: str, enabled: bool):
    _update_guild_config(guild_id, "security_logs_enabled", 1 if enabled else 0)


def set_raid_limit(guild_id: str, total: int):
    _update_guild_config(guild_id, "raid_limit", total)


def set_raid_window_seconds(guild_id: str, seconds: int):
    _update_guild_config(guild_id, "raid_window_seconds", seconds)


def set_nuke_limit(guild_id: str, total: int):
    _update_guild_config(guild_id, "nuke_limit", total)


def set_channel_create_limit(guild_id: str, total: int):
    _update_guild_config(guild_id, "channel_create_limit", total)


def set_role_create_limit(guild_id: str, total: int):
    _update_guild_config(guild_id, "role_create_limit", total)


def add_whitelist(guild_id: str, user_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO whitelist (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def remove_whitelist(guild_id: str, user_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM whitelist WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def is_whitelisted(guild_id: str, user_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM whitelist WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    result = c.fetchone() is not None
    conn.close()
    return result


def get_whitelist(guild_id: str) -> list[str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM whitelist WHERE guild_id = ?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_warnings(guild_id: str, user_id: str) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT count FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = c.fetchone()
    conn.close()
    return row["count"] if row else 0


def add_warning(guild_id: str, user_id: str) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO warnings (guild_id, user_id, count) VALUES (?, ?, 1)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id),
    )
    conn.commit()
    c.execute(
        "SELECT count FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    total = c.fetchone()["count"]
    conn.close()
    return total


def reset_warnings(guild_id: str, user_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE warnings SET count = 0 WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    conn.commit()
    conn.close()


def add_custom_word(guild_id: str, word: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO custom_words (guild_id, word) VALUES (?, ?)",
            (guild_id, word.lower().strip()),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def remove_custom_word(guild_id: str, word: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM custom_words WHERE guild_id = ? AND word = ?",
        (guild_id, word.lower().strip()),
    )
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_custom_words(guild_id: str) -> set[str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT word FROM custom_words WHERE guild_id = ?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    return {r["word"] for r in rows}
