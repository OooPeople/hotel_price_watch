"""SQLite repository 與 schema 的整合測試。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    NotificationThrottleState,
    PriceHistoryEntry,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.db import (
    CURRENT_SCHEMA_VERSION,
    SQLITE_BUSY_TIMEOUT_MS,
    SchemaVersionMismatchError,
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)


def test_initialize_schema_persists_version_and_is_idempotent(tmp_path) -> None:
    """驗證 schema 初始化會寫入版本，且重複執行不會失敗。"""
    database = SqliteDatabase(tmp_path / "watcher.db")

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        version_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'",
        ).fetchone()

    assert version_row is not None
    assert version_row["value"] == str(CURRENT_SCHEMA_VERSION)


def test_watch_item_repository_round_trip_and_keeps_draft_separate(tmp_path) -> None:
    """驗證 watch item 與 UI draft 會分開保存。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    repository = SqliteWatchItemRepository(database)

    watch_item = _build_watch_item()
    draft = SearchDraft(
        seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        check_in_date=date(2026, 9, 18),
        check_out_date=date(2026, 9, 19),
        people_count=2,
        room_count=1,
        hotel_id="00082173",
        browser_tab_id="target-123",
        browser_page_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
    )

    repository.save(watch_item)
    repository.save_draft(watch_item.id, draft)

    loaded_item = repository.get(watch_item.id)
    loaded_draft = repository.get_draft(watch_item.id)

    assert loaded_item is not None
    assert loaded_item.id == watch_item.id
    assert loaded_item.target == watch_item.target
    assert loaded_item.notification_rule == watch_item.notification_rule
    assert loaded_item.created_at is not None
    assert loaded_item.updated_at is not None
    assert loaded_draft == draft


def test_initialize_schema_rejects_version_mismatch(tmp_path) -> None:
    """驗證既有資料庫版本不符時會明確報錯，而不是靜默覆寫。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()

    with database.connect() as connection:
        connection.execute(
            "UPDATE metadata SET value = '999' WHERE key = 'schema_version'",
        )

    try:
        database.initialize()
    except SchemaVersionMismatchError as exc:
        assert "expected schema version" in str(exc)
    else:
        raise AssertionError("expected schema version mismatch to raise")


def test_initialize_schema_migrates_from_v2_to_latest_via_chain(tmp_path) -> None:
    """驗證既有 v2 資料庫會依鏈式 migration 升到最新版。"""
    database = SqliteDatabase(tmp_path / "watcher.db")

    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO metadata (key, value) VALUES ('schema_version', '2')"
        )
        connection.execute(
            """
            CREATE TABLE watch_item_drafts (
                watch_item_id TEXT PRIMARY KEY,
                seed_url TEXT NOT NULL,
                check_in_date TEXT,
                check_out_date TEXT,
                people_count INTEGER,
                room_count INTEGER,
                hotel_id TEXT,
                room_id TEXT,
                plan_id TEXT,
                updated_at_utc TEXT NOT NULL
            )
            """
        )

    database.initialize()

    with database.connect() as connection:
        version_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        draft_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(watch_item_drafts)"
            ).fetchall()
        }
        throttle_table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'notification_throttle_states'
            """
        ).fetchone()

    assert version_row is not None
    assert version_row["value"] == str(CURRENT_SCHEMA_VERSION)
    assert "browser_tab_id" in draft_columns
    assert "browser_page_url" in draft_columns
    assert throttle_table is not None


def test_initialize_schema_migrates_from_v3_to_latest_via_chain(tmp_path) -> None:
    """驗證既有 v3 資料庫會經過 `3 -> 4 -> 5` 鏈式升版。"""
    database = SqliteDatabase(tmp_path / "watcher.db")

    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO metadata (key, value) VALUES ('schema_version', '3')"
        )
        connection.execute(
            """
            CREATE TABLE watch_item_drafts (
                watch_item_id TEXT PRIMARY KEY,
                seed_url TEXT NOT NULL,
                check_in_date TEXT,
                check_out_date TEXT,
                people_count INTEGER,
                room_count INTEGER,
                hotel_id TEXT,
                room_id TEXT,
                plan_id TEXT,
                updated_at_utc TEXT NOT NULL
            )
            """
        )

    database.initialize()

    with database.connect() as connection:
        version_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        draft_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(watch_item_drafts)"
            ).fetchall()
        }
        throttle_table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'notification_throttle_states'
            """
        ).fetchone()

    assert version_row is not None
    assert version_row["value"] == str(CURRENT_SCHEMA_VERSION)
    assert "browser_tab_id" in draft_columns
    assert "browser_page_url" in draft_columns
    assert throttle_table is not None


def test_watch_items_table_does_not_mix_runtime_columns(tmp_path) -> None:
    """驗證 watch_items table 沒有混入最新價格與錯誤欄位。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()

    with database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(watch_items)").fetchall()
        }

    assert "normalized_price_amount" not in columns
    assert "last_error_code" not in columns
    assert "last_checked_at" not in columns
    assert "display_price_text" not in columns


def test_database_connection_enables_wal_busy_timeout_and_history_indexes(tmp_path) -> None:
    """驗證 SQLite 連線會套用 WAL、busy_timeout 與歷史查詢 index。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()

    with database.connect() as connection:
        journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
        busy_timeout_row = connection.execute("PRAGMA busy_timeout").fetchone()
        check_event_indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(check_events)").fetchall()
        }
        price_history_indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(price_history)").fetchall()
        }
        debug_artifact_indexes = {
            row["name"]
            for row in connection.execute(
                "PRAGMA index_list(debug_artifacts)"
            ).fetchall()
        }

    assert journal_mode_row is not None
    assert journal_mode_row[0].lower() == "wal"
    assert busy_timeout_row is not None
    assert busy_timeout_row[0] == SQLITE_BUSY_TIMEOUT_MS
    assert "idx_check_events_watch_checked_at" in check_event_indexes
    assert "idx_price_history_watch_captured_at" in price_history_indexes
    assert "idx_debug_artifacts_watch_captured_at" in debug_artifact_indexes


def test_runtime_repository_persists_latest_history_and_notification_state(tmp_path) -> None:
    """驗證最新摘要、檢查歷史、價格歷史與通知狀態可正確往返。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    SqliteWatchItemRepository(database).save(_build_watch_item())
    repository = SqliteRuntimeRepository(database)

    latest = LatestCheckSnapshot(
        watch_item_id="watch-1",
        checked_at=datetime(2026, 4, 11, 12, 0, 0),
        availability=Availability.AVAILABLE,
        normalized_price_amount=Decimal("12000"),
        currency="JPY",
        consecutive_failures=2,
        last_error_code="network_timeout",
    )
    event = CheckEvent(
        watch_item_id="watch-1",
        checked_at=datetime(2026, 4, 11, 12, 0, 0),
        availability=Availability.AVAILABLE,
        event_kinds=("price_drop", "below_target_price"),
        normalized_price_amount=Decimal("12000"),
        currency="JPY",
        notification_status=NotificationDeliveryStatus.SENT,
        sent_channels=("desktop",),
    )
    price_history = PriceHistoryEntry(
        watch_item_id="watch-1",
        captured_at=datetime(2026, 4, 11, 12, 0, 0),
        display_price_text="JPY 12,000",
        normalized_price_amount=Decimal("12000"),
        currency="JPY",
        source_kind=SourceKind.HTTP,
    )
    notification_state = NotificationState(
        watch_item_id="watch-1",
        last_notified_price=Decimal("12000"),
        last_notified_availability=Availability.AVAILABLE,
        last_notified_at=datetime(2026, 4, 11, 12, 0, 0),
        consecutive_failures=2,
        consecutive_parse_failures=1,
    )

    repository.save_latest_check_snapshot(latest)
    repository.append_check_event(event)
    repository.append_price_history(price_history)
    repository.save_notification_state(notification_state)

    assert repository.get_latest_check_snapshot("watch-1") == latest
    assert repository.list_check_events("watch-1") == [event]
    assert repository.list_price_history("watch-1") == [price_history]
    assert repository.get_notification_state("watch-1") == notification_state


def test_runtime_repository_persists_notification_throttle_state(tmp_path) -> None:
    """驗證通道級節流狀態可正確往返保存。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    repository = SqliteRuntimeRepository(database)
    state = NotificationThrottleState(
        channel_name="discord",
        dedupe_key="watch-1:price_drop:available:22000",
        last_sent_at=datetime(2026, 4, 12, 10, 0, 0),
    )

    repository.save_notification_throttle_state(state)

    assert (
        repository.get_notification_throttle_state(
            channel_name="discord",
            dedupe_key="watch-1:price_drop:available:22000",
        )
        == state
    )


def test_persist_check_outcome_rolls_back_when_midway_write_fails(tmp_path) -> None:
    """驗證單次 check 寫入若中途失敗，不會留下部分成功的資料。"""

    class _FailOnCheckEventConnection(sqlite3.Connection):
        """在寫入 check_events 時故意失敗，驗證 transaction rollback。"""

        def execute(self, sql: str, parameters=(), /):  # type: ignore[override]
            if "INSERT INTO check_events" in sql:
                raise sqlite3.OperationalError("forced check_events failure")
            return super().execute(sql, parameters)

    class _FailOnCheckEventDatabase(SqliteDatabase):
        """回傳故障注入 connection 的測試資料庫。"""

        def connect(self) -> sqlite3.Connection:
            connection = sqlite3.connect(
                self.db_path,
                factory=_FailOnCheckEventConnection,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            return connection

    database = _FailOnCheckEventDatabase(tmp_path / "watcher.db")
    database.initialize()
    SqliteWatchItemRepository(database).save(_build_watch_item())
    repository = SqliteRuntimeRepository(database)

    try:
        repository.persist_check_outcome(
            latest_snapshot=LatestCheckSnapshot(
                watch_item_id="watch-1",
                checked_at=datetime(2026, 4, 11, 12, 0, 0),
                availability=Availability.AVAILABLE,
                normalized_price_amount=Decimal("12000"),
                currency="JPY",
            ),
            check_event=CheckEvent(
                watch_item_id="watch-1",
                checked_at=datetime(2026, 4, 11, 12, 0, 0),
                availability=Availability.AVAILABLE,
                event_kinds=("checked",),
            ),
            notification_state=NotificationState(
                watch_item_id="watch-1",
                consecutive_failures=1,
                consecutive_parse_failures=0,
            ),
            price_history_entry=PriceHistoryEntry(
                watch_item_id="watch-1",
                captured_at=datetime(2026, 4, 11, 12, 0, 0),
                display_price_text="JPY 12,000",
                normalized_price_amount=Decimal("12000"),
                currency="JPY",
                source_kind=SourceKind.BROWSER,
            ),
        )
    except sqlite3.OperationalError as exc:
        assert "forced check_events failure" in str(exc)
    else:
        raise AssertionError("expected persist_check_outcome to raise")

    assert repository.get_latest_check_snapshot("watch-1") is None
    assert repository.list_check_events("watch-1") == []
    assert repository.list_price_history("watch-1") == []
    assert repository.get_notification_state("watch-1") is None


def test_debug_artifact_retention_keeps_only_latest_items(tmp_path) -> None:
    """驗證 debug artifact 會依 watch item 套用保留上限。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    SqliteWatchItemRepository(database).save(_build_watch_item())
    repository = SqliteRuntimeRepository(database)

    repository.append_debug_artifact(
        DebugArtifact(
            watch_item_id="watch-1",
            captured_at=datetime(2026, 4, 11, 12, 0, 0),
            reason="parse_failed",
            payload_text="payload-1",
        ),
        retention_limit=2,
    )
    repository.append_debug_artifact(
        DebugArtifact(
            watch_item_id="watch-1",
            captured_at=datetime(2026, 4, 11, 12, 5, 0),
            reason="parse_failed",
            payload_text="payload-2",
        ),
        retention_limit=2,
    )
    repository.append_debug_artifact(
        DebugArtifact(
            watch_item_id="watch-1",
            captured_at=datetime(2026, 4, 11, 12, 10, 0),
            reason="parse_failed",
            payload_text="payload-3",
        ),
        retention_limit=2,
    )

    artifacts = repository.list_debug_artifacts("watch-1")

    assert [artifact.payload_text for artifact in artifacts] == ["payload-3", "payload-2"]


def test_delete_watch_item_cascades_runtime_records(tmp_path) -> None:
    """驗證刪除 watch item 後，附屬 runtime 資料會一併清理。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    watch_item = _build_watch_item()
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        SearchDraft(seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms"),
    )
    runtime_repository.save_latest_check_snapshot(
        LatestCheckSnapshot(
            watch_item_id="watch-1",
            checked_at=datetime(2026, 4, 11, 12, 0, 0),
            availability=Availability.AVAILABLE,
            normalized_price_amount=Decimal("12000"),
            currency="JPY",
        )
    )
    runtime_repository.append_check_event(
        CheckEvent(
            watch_item_id="watch-1",
            checked_at=datetime(2026, 4, 11, 12, 0, 0),
            availability=Availability.AVAILABLE,
            event_kinds=("checked",),
        )
    )
    runtime_repository.save_notification_state(
        NotificationState(
            watch_item_id="watch-1",
            consecutive_failures=1,
            consecutive_parse_failures=1,
        )
    )

    watch_repository.delete("watch-1")

    assert watch_repository.get("watch-1") is None
    assert watch_repository.get_draft("watch-1") is None
    assert runtime_repository.get_latest_check_snapshot("watch-1") is None
    assert runtime_repository.list_check_events("watch-1") == []
    assert runtime_repository.get_notification_state("watch-1") is None


def test_app_settings_repository_round_trip_notification_channels(tmp_path) -> None:
    """驗證全域通知通道設定可正確往返保存。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    repository = SqliteAppSettingsRepository(database)

    settings = NotificationChannelSettings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_server_url="https://ntfy.example.com",
        ntfy_topic="hotel-watch",
        discord_enabled=True,
        discord_webhook_url="https://discord.example.com/webhook",
    )

    repository.save_notification_channel_settings(settings)

    assert repository.get_notification_channel_settings() == settings


def _build_watch_item() -> WatchItem:
    """建立整合測試共用的 watch item 樣本。"""
    return WatchItem(
        id="watch-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="sample hotel",
        room_name="standard twin",
        plan_name="room only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("13000"),
        ),
        scheduler_interval_seconds=600,
        enabled=True,
        created_at=datetime(2026, 4, 11, 12, 0, 0),
        updated_at=datetime(2026, 4, 11, 12, 0, 0),
    )
