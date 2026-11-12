"""SQLite storage for ZENTRA VPN demo users and subscriptions."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent / "data" / "zentra.sqlite3"
ALLOWED_COUNTRIES = frozenset({"de", "nl", "pl"})
ALLOWED_DEVICES = frozenset({"android", "iphone"})


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    """Create the user and demo-subscription tables if they do not exist."""
    with _connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                interaction_count INTEGER NOT NULL DEFAULT 1,
                selected_country TEXT,
                selected_device TEXT
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL
                    REFERENCES users(telegram_id) ON DELETE CASCADE,
                duration_days INTEGER NOT NULL
                    CHECK (duration_days IN (7, 30)),
                granted_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_last_seen
                ON users(last_seen_at DESC);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_expiration
                ON subscriptions(expires_at);
            """
        )
        user_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "selected_country" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN selected_country TEXT")
        if "selected_device" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN selected_device TEXT")


def record_user_activity(user: object | None) -> None:
    """Insert a Telegram user or update their profile and activity timestamp."""
    if user is None:
        return

    telegram_id = int(getattr(user, "id"))
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", "") or ""

    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO users (
                telegram_id, username, first_name,
                created_at, last_seen_at, interaction_count
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen_at = CURRENT_TIMESTAMP,
                interaction_count = users.interaction_count + 1
            """,
            (telegram_id, username, first_name),
        )


def count_users() -> int:
    with _connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"])


def user_exists(telegram_id: int) -> bool:
    with _connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
    return row is not None


def get_user_preferences(telegram_id: int) -> dict[str, str | None] | None:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT selected_country, selected_device
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def set_user_country(telegram_id: int, country: str) -> bool:
    if country not in ALLOWED_COUNTRIES:
        raise ValueError("Unsupported country selection.")

    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET selected_country = ? WHERE telegram_id = ?",
            (country, telegram_id),
        )
    return cursor.rowcount > 0


def set_user_device(telegram_id: int, device: str) -> bool:
    if device not in ALLOWED_DEVICES:
        raise ValueError("Unsupported device selection.")

    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET selected_device = ? WHERE telegram_id = ?",
            (device, telegram_id),
        )
    return cursor.rowcount > 0


def list_users(limit: int = 10) -> list[dict[str, object]]:
    safe_limit = max(1, min(limit, 50))
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT telegram_id, username, first_name, created_at, last_seen_at
            FROM users
            ORDER BY last_seen_at DESC, telegram_id ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_statistics() -> dict[str, int]:
    with _connection() as connection:
        user_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                COALESCE(SUM(
                    CASE WHEN last_seen_at >= datetime('now', '-1 day')
                    THEN 1 ELSE 0 END
                ), 0) AS active_24h,
                COALESCE(SUM(
                    CASE WHEN last_seen_at >= datetime('now', '-7 days')
                    THEN 1 ELSE 0 END
                ), 0) AS active_7d,
                COALESCE(SUM(interaction_count), 0) AS total_interactions
            FROM users
            """
        ).fetchone()
        subscription_row = connection.execute(
            """
            SELECT COUNT(*) AS active_subscriptions
            FROM subscriptions
            WHERE expires_at > CURRENT_TIMESTAMP
            """
        ).fetchone()

    return {
        "total_users": int(user_row["total_users"]),
        "active_24h": int(user_row["active_24h"]),
        "active_7d": int(user_row["active_7d"]),
        "total_interactions": int(user_row["total_interactions"]),
        "active_subscriptions": int(subscription_row["active_subscriptions"]),
    }


def list_recent_subscriptions(limit: int = 5) -> list[dict[str, object]]:
    safe_limit = max(1, min(limit, 25))
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT id, telegram_id, duration_days, granted_by,
                   created_at, expires_at
            FROM subscriptions
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_subscription(telegram_id: int) -> dict[str, object] | None:
    """Return the user's best current demo grant, or their latest expired one."""
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT id, telegram_id, duration_days, created_at, expires_at
            FROM subscriptions
            WHERE telegram_id = ? AND expires_at > CURRENT_TIMESTAMP
            ORDER BY expires_at DESC, id DESC
            LIMIT 1
            """,
            (telegram_id,),
        ).fetchone()
        active = row is not None
        if row is None:
            row = connection.execute(
                """
                SELECT id, telegram_id, duration_days, created_at, expires_at
                FROM subscriptions
                WHERE telegram_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (telegram_id,),
            ).fetchone()

    if row is None:
        return None
    result = dict(row)
    result["is_active"] = active
    return result


def grant_demo_subscription(
    telegram_id: int,
    duration_days: int,
    granted_by: int,
) -> dict[str, object] | None:
    """Create a demo-only grant for a user already stored in SQLite."""
    if duration_days not in (7, 30):
        raise ValueError("Demo subscriptions can only be 7 or 30 days.")

    with _connection() as connection:
        existing_user = connection.execute(
            "SELECT 1 FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if existing_user is None:
            return None

        cursor = connection.execute(
            """
            INSERT INTO subscriptions (
                telegram_id, duration_days, granted_by, expires_at
            )
            VALUES (?, ?, ?, datetime('now', ?))
            """,
            (
                telegram_id,
                duration_days,
                granted_by,
                f"+{duration_days} days",
            ),
        )
        row = connection.execute(
            """
            SELECT id, telegram_id, duration_days, granted_by,
                   created_at, expires_at
            FROM subscriptions
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row) if row is not None else None
      
