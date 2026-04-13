"""SQLite schema 與版本初始化。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

CURRENT_SCHEMA_VERSION = 5


class SchemaVersionMismatchError(RuntimeError):
    """表示資料庫 schema 版本與目前程式不相容。"""


class SqliteDatabase:
    """封裝 SQLite 連線建立與 schema 初始化。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        """建立已啟用 foreign keys 的 SQLite 連線。"""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """初始化或驗證目前資料庫的 schema 版本。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            initialize_schema(connection)


def initialize_schema(connection: sqlite3.Connection) -> None:
    """建立 V1 所需的基礎 schema 與 metadata。"""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    _migrate_schema_if_supported(connection)
    _validate_existing_schema_version(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS watch_items (
            id TEXT PRIMARY KEY,
            site TEXT NOT NULL,
            hotel_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            check_in_date TEXT NOT NULL,
            check_out_date TEXT NOT NULL,
            people_count INTEGER NOT NULL,
            room_count INTEGER NOT NULL,
            hotel_name TEXT NOT NULL,
            room_name TEXT NOT NULL,
            plan_name TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            notification_rule_json TEXT NOT NULL,
            scheduler_interval_seconds INTEGER NOT NULL,
            enabled INTEGER NOT NULL,
            paused_reason TEXT,
            created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watch_item_drafts (
            watch_item_id TEXT PRIMARY KEY,
            seed_url TEXT NOT NULL,
            check_in_date TEXT,
            check_out_date TEXT,
            people_count INTEGER,
            room_count INTEGER,
            hotel_id TEXT,
            room_id TEXT,
            plan_id TEXT,
            browser_tab_id TEXT,
            browser_page_url TEXT,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (watch_item_id) REFERENCES watch_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS latest_check_snapshots (
            watch_item_id TEXT PRIMARY KEY,
            checked_at_utc TEXT NOT NULL,
            availability TEXT NOT NULL,
            normalized_price_amount TEXT,
            currency TEXT,
            backoff_until_utc TEXT,
            is_degraded INTEGER NOT NULL,
            consecutive_failures INTEGER NOT NULL,
            last_error_code TEXT,
            FOREIGN KEY (watch_item_id) REFERENCES watch_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS check_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_item_id TEXT NOT NULL,
            checked_at_utc TEXT NOT NULL,
            availability TEXT NOT NULL,
            event_kinds_json TEXT NOT NULL,
            normalized_price_amount TEXT,
            currency TEXT,
            error_code TEXT,
            notification_status TEXT NOT NULL,
            sent_channels_json TEXT NOT NULL,
            throttled_channels_json TEXT NOT NULL,
            failed_channels_json TEXT NOT NULL,
            FOREIGN KEY (watch_item_id) REFERENCES watch_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_item_id TEXT NOT NULL,
            captured_at_utc TEXT NOT NULL,
            display_price_text TEXT NOT NULL,
            normalized_price_amount TEXT NOT NULL,
            currency TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            FOREIGN KEY (watch_item_id) REFERENCES watch_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notification_states (
            watch_item_id TEXT PRIMARY KEY,
            last_notified_price TEXT,
            last_notified_availability TEXT,
            last_notified_at_utc TEXT,
            consecutive_failures INTEGER NOT NULL,
            consecutive_parse_failures INTEGER NOT NULL,
            degraded_notified_at_utc TEXT,
            FOREIGN KEY (watch_item_id) REFERENCES watch_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notification_throttle_states (
            channel_name TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            last_sent_at_utc TEXT NOT NULL,
            PRIMARY KEY (channel_name, dedupe_key)
        );

        CREATE TABLE IF NOT EXISTS debug_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_item_id TEXT NOT NULL,
            captured_at_utc TEXT NOT NULL,
            reason TEXT NOT NULL,
            payload_text TEXT NOT NULL,
            source_url TEXT,
            http_status INTEGER,
            FOREIGN KEY (watch_item_id) REFERENCES watch_items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notification_channel_settings (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            desktop_enabled INTEGER NOT NULL,
            ntfy_enabled INTEGER NOT NULL,
            ntfy_server_url TEXT NOT NULL,
            ntfy_topic TEXT,
            discord_enabled INTEGER NOT NULL,
            discord_webhook_url TEXT,
            updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _persist_schema_version_if_missing(connection)


def _validate_existing_schema_version(connection: sqlite3.Connection) -> None:
    """驗證既有資料庫的 schema version 是否可被目前程式接受。"""
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'",
    ).fetchone()
    if row is None:
        return

    current_value = row["value"]
    if current_value != str(CURRENT_SCHEMA_VERSION):
        raise SchemaVersionMismatchError(
            f"expected schema version {CURRENT_SCHEMA_VERSION}, got {current_value}"
        )


def _migrate_schema_if_supported(connection: sqlite3.Connection) -> None:
    """處理目前程式可接受的最小 schema 升級。"""
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'",
    ).fetchone()
    if row is None:
        return

    current_value = row["value"]
    if current_value == "2" and CURRENT_SCHEMA_VERSION >= 3:
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            ("3",),
        )
        current_value = "3"

    if current_value == "3" and CURRENT_SCHEMA_VERSION == 4:
        connection.execute(
            "ALTER TABLE watch_item_drafts ADD COLUMN browser_tab_id TEXT"
        )
        connection.execute(
            "ALTER TABLE watch_item_drafts ADD COLUMN browser_page_url TEXT"
        )
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            (str(CURRENT_SCHEMA_VERSION),),
        )
        current_value = "4"

    if current_value == "4" and CURRENT_SCHEMA_VERSION >= 5:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_throttle_states (
                channel_name TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                last_sent_at_utc TEXT NOT NULL,
                PRIMARY KEY (channel_name, dedupe_key)
            )
            """
        )
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            (str(CURRENT_SCHEMA_VERSION),),
        )


def _persist_schema_version_if_missing(connection: sqlite3.Connection) -> None:
    """只在新資料庫尚未寫入版本時保存目前 schema version。"""
    connection.execute(
        """
        INSERT OR IGNORE INTO metadata (key, value)
        VALUES ('schema_version', ?)
        """,
        (str(CURRENT_SCHEMA_VERSION),),
    )
