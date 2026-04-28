"""runtime history 與頁面 read model 使用的 SQLite 查詢 helper。"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    PriceHistoryEntry,
    RuntimeStateEvent,
)
from app.domain.enums import (
    Availability,
    NotificationDeliveryStatus,
    RuntimeStateEventKind,
    SourceKind,
    WatchRuntimeState,
)
from app.infrastructure.db.schema import SqliteDatabase
from app.infrastructure.db.sqlite_serializers import (
    datetime_to_text,
    text_to_datetime,
    text_to_decimal,
)


def get_latest_check_snapshot(
    database: SqliteDatabase,
    watch_item_id: str,
) -> LatestCheckSnapshot | None:
    """讀出單一 watch item 的最新檢查摘要。"""
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM latest_check_snapshots WHERE watch_item_id = ?",
            (watch_item_id,),
        ).fetchone()
    if row is None:
        return None
    return LatestCheckSnapshot(
        watch_item_id=row["watch_item_id"],
        checked_at=text_to_datetime(row["checked_at_utc"]),
        availability=Availability(row["availability"]),
        normalized_price_amount=text_to_decimal(row["normalized_price_amount"]),
        currency=row["currency"],
        backoff_until=text_to_datetime(row["backoff_until_utc"]),
        is_degraded=bool(row["is_degraded"]),
        consecutive_failures=row["consecutive_failures"],
        last_error_code=row["last_error_code"],
    )


def get_last_effective_availability(
    database: SqliteDatabase,
    watch_item_id: str,
) -> Availability | None:
    """回溯最近一次明確可判定的 availability，只接受 available/sold_out。"""
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT availability
            FROM check_events
            WHERE watch_item_id = ?
              AND availability IN (?, ?)
            ORDER BY checked_at_utc DESC, id DESC
            LIMIT 1
            """,
            (
                watch_item_id,
                Availability.AVAILABLE.value,
                Availability.SOLD_OUT.value,
            ),
        ).fetchone()
    if row is None:
        return None
    return Availability(row["availability"])


def list_check_events(database: SqliteDatabase, watch_item_id: str) -> list[CheckEvent]:
    """依時間列出某個 watch item 的檢查歷史。"""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM check_events
            WHERE watch_item_id = ?
            ORDER BY checked_at_utc, id
            """,
            (watch_item_id,),
        ).fetchall()
    return [
        CheckEvent(
            watch_item_id=row["watch_item_id"],
            checked_at=text_to_datetime(row["checked_at_utc"]),
            availability=Availability(row["availability"]),
            event_kinds=tuple(json.loads(row["event_kinds_json"])),
            normalized_price_amount=text_to_decimal(row["normalized_price_amount"]),
            currency=row["currency"],
            error_code=row["error_code"],
            notification_status=NotificationDeliveryStatus(row["notification_status"]),
            sent_channels=tuple(json.loads(row["sent_channels_json"])),
            throttled_channels=tuple(json.loads(row["throttled_channels_json"])),
            failed_channels=tuple(json.loads(row["failed_channels_json"])),
        )
        for row in rows
    ]


def list_price_history(
    database: SqliteDatabase,
    watch_item_id: str,
) -> list[PriceHistoryEntry]:
    """依時間列出某個 watch item 的成功價格歷史。"""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM price_history
            WHERE watch_item_id = ?
            ORDER BY captured_at_utc, id
            """,
            (watch_item_id,),
        ).fetchall()
    return [_row_to_price_history_entry(row) for row in rows]


def list_price_history_since(
    database: SqliteDatabase,
    *,
    watch_item_ids: tuple[str, ...],
    since: datetime,
) -> dict[str, tuple[PriceHistoryEntry, ...]]:
    """批次讀取多個 watch item 在指定時間後的成功價格歷史。"""
    if not watch_item_ids:
        return {}
    placeholders = ", ".join("?" for _ in watch_item_ids)
    with database.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM price_history
            WHERE watch_item_id IN ({placeholders})
              AND captured_at_utc >= ?
            ORDER BY watch_item_id, captured_at_utc, id
            """,
            (*watch_item_ids, datetime_to_text(since)),
        ).fetchall()
    grouped: dict[str, list[PriceHistoryEntry]] = {
        watch_item_id: [] for watch_item_id in watch_item_ids
    }
    for row in rows:
        grouped[row["watch_item_id"]].append(_row_to_price_history_entry(row))
    return {
        watch_item_id: tuple(entries)
        for watch_item_id, entries in grouped.items()
    }


def count_notifications_since(database: SqliteDatabase, since: datetime) -> int:
    """統計指定時間後已送出或部分成功的通知事件數。"""
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM check_events
            WHERE checked_at_utc >= ?
              AND notification_status IN (?, ?)
            """,
            (
                datetime_to_text(since),
                NotificationDeliveryStatus.SENT.value,
                NotificationDeliveryStatus.PARTIAL.value,
            ),
        ).fetchone()
    return int(row["count"] if row is not None else 0)


def get_notification_state(
    database: SqliteDatabase,
    watch_item_id: str,
) -> NotificationState | None:
    """讀出單一 watch item 的通知去重狀態。"""
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM notification_states WHERE watch_item_id = ?",
            (watch_item_id,),
        ).fetchone()
    if row is None:
        return None
    return NotificationState(
        watch_item_id=row["watch_item_id"],
        last_notified_price=text_to_decimal(row["last_notified_price"]),
        last_notified_availability=None
        if row["last_notified_availability"] is None
        else Availability(row["last_notified_availability"]),
        last_notified_at=text_to_datetime(row["last_notified_at_utc"]),
        consecutive_failures=row["consecutive_failures"],
        consecutive_parse_failures=row["consecutive_parse_failures"],
        degraded_notified_at=text_to_datetime(row["degraded_notified_at_utc"]),
    )


def list_runtime_state_events(
    database: SqliteDatabase,
    watch_item_id: str,
) -> list[RuntimeStateEvent]:
    """依時間倒序列出 watch 的 runtime 狀態轉移事件。"""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM runtime_state_events
            WHERE watch_item_id = ?
            ORDER BY occurred_at_utc DESC, id DESC
            """,
            (watch_item_id,),
        ).fetchall()
    return [
        RuntimeStateEvent(
            watch_item_id=row["watch_item_id"],
            occurred_at=text_to_datetime(row["occurred_at_utc"]),
            event_kind=RuntimeStateEventKind(row["event_kind"]),
            from_state=(
                None
                if row["from_state"] is None
                else WatchRuntimeState(row["from_state"])
            ),
            to_state=(
                None
                if row["to_state"] is None
                else WatchRuntimeState(row["to_state"])
            ),
            detail_text=row["detail_text"],
        )
        for row in rows
    ]


def list_debug_artifacts(
    database: SqliteDatabase,
    watch_item_id: str,
) -> list[DebugArtifact]:
    """依時間列出 debug artifact，供錯誤排查使用。"""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM debug_artifacts
            WHERE watch_item_id = ?
            ORDER BY captured_at_utc DESC, id DESC
            """,
            (watch_item_id,),
        ).fetchall()
    return [
        DebugArtifact(
            watch_item_id=row["watch_item_id"],
            captured_at=text_to_datetime(row["captured_at_utc"]),
            reason=row["reason"],
            payload_text=row["payload_text"],
            source_url=row["source_url"],
            http_status=row["http_status"],
        )
        for row in rows
    ]


def _row_to_price_history_entry(row) -> PriceHistoryEntry:
    """把 price_history row 轉成價格歷史 domain entity。"""
    return PriceHistoryEntry(
        watch_item_id=row["watch_item_id"],
        captured_at=text_to_datetime(row["captured_at_utc"]),
        display_price_text=row["display_price_text"],
        normalized_price_amount=Decimal(row["normalized_price_amount"]),
        currency=row["currency"],
        source_kind=SourceKind(row["source_kind"]),
    )
