"""SQLite schema 與版本初始化。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

CURRENT_SCHEMA_VERSION = 5
SQLITE_BUSY_TIMEOUT_MS = 5_000
MIN_SUPPORTED_SCHEMA_VERSION = 2


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
        _configure_connection(connection)
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

        CREATE INDEX IF NOT EXISTS idx_check_events_watch_checked_at
        ON check_events(watch_item_id, checked_at_utc DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_price_history_watch_captured_at
        ON price_history(watch_item_id, captured_at_utc DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_debug_artifacts_watch_captured_at
        ON debug_artifacts(watch_item_id, captured_at_utc DESC, id DESC);
        """
    )
    _persist_schema_version_if_missing(connection)


def _configure_connection(connection: sqlite3.Connection) -> None:
    """套用 SQLite 背景長駐執行所需的連線層設定。"""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")


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
    """依版本鏈逐步執行目前程式可接受的 schema 升級。"""
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'",
    ).fetchone()
    if row is None:
        return

    try:
        current_version = int(row["value"])
    except ValueError as exc:
        raise SchemaVersionMismatchError(
            f"expected integer schema version, got {row['value']}"
        ) from exc

    if current_version < MIN_SUPPORTED_SCHEMA_VERSION:
        raise SchemaVersionMismatchError(
            f"expected schema version between {MIN_SUPPORTED_SCHEMA_VERSION} and "
            f"{CURRENT_SCHEMA_VERSION}, got {current_version}"
        )

    migration_chain = _build_migration_chain()
    while current_version < CURRENT_SCHEMA_VERSION:
        migrate = migration_chain.get(current_version)
        if migrate is None:
            raise SchemaVersionMismatchError(
                f"no migration path from schema version {current_version} to "
                f"{CURRENT_SCHEMA_VERSION}"
            )
        next_version = migrate(connection)
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            (str(next_version),),
        )
        current_version = next_version


def _persist_schema_version_if_missing(connection: sqlite3.Connection) -> None:
    """只在新資料庫尚未寫入版本時保存目前 schema version。"""
    connection.execute(
        """
        INSERT OR IGNORE INTO metadata (key, value)
        VALUES ('schema_version', ?)
        """,
        (str(CURRENT_SCHEMA_VERSION),),
    )


def _build_migration_chain() -> dict[int, Callable[[sqlite3.Connection], int]]:
    """建立 `n -> n+1` 的明確 migration 對應表。"""
    return {
        2: _migrate_2_to_3,
        3: _migrate_3_to_4,
        4: _migrate_4_to_5,
    }


def _migrate_2_to_3(connection: sqlite3.Connection) -> int:
    """執行 schema `2 -> 3` 升版。"""
    del connection
    return 3


def _migrate_3_to_4(connection: sqlite3.Connection) -> int:
    """執行 schema `3 -> 4` 升版。"""
    connection.execute("ALTER TABLE watch_item_drafts ADD COLUMN browser_tab_id TEXT")
    connection.execute("ALTER TABLE watch_item_drafts ADD COLUMN browser_page_url TEXT")
    return 4


def _migrate_4_to_5(connection: sqlite3.Connection) -> int:
    """執行 schema `4 -> 5` 升版。"""
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
    return 5
