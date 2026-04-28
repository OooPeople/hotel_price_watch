"""runtime 寫入路徑使用的 SQLite record helper。"""

from __future__ import annotations

import json
from sqlite3 import Connection

from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    PriceHistoryEntry,
    RuntimeStateEvent,
)
from app.infrastructure.db.sqlite_serializers import datetime_to_text, decimal_to_text


def write_latest_check_snapshot(
    connection: Connection,
    snapshot: LatestCheckSnapshot,
) -> None:
    """在既有 connection 上保存最新檢查摘要。"""
    connection.execute(
        """
        INSERT INTO latest_check_snapshots (
            watch_item_id, checked_at_utc, availability,
            normalized_price_amount, currency, backoff_until_utc,
            is_degraded, consecutive_failures, last_error_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(watch_item_id) DO UPDATE SET
            checked_at_utc = excluded.checked_at_utc,
            availability = excluded.availability,
            normalized_price_amount = excluded.normalized_price_amount,
            currency = excluded.currency,
            backoff_until_utc = excluded.backoff_until_utc,
            is_degraded = excluded.is_degraded,
            consecutive_failures = excluded.consecutive_failures,
            last_error_code = excluded.last_error_code
        """,
        (
            snapshot.watch_item_id,
            datetime_to_text(snapshot.checked_at),
            snapshot.availability.value,
            decimal_to_text(snapshot.normalized_price_amount),
            snapshot.currency,
            datetime_to_text(snapshot.backoff_until),
            int(snapshot.is_degraded),
            snapshot.consecutive_failures,
            snapshot.last_error_code,
        ),
    )


def write_check_event(connection: Connection, event: CheckEvent) -> None:
    """在既有 connection 上追加單次檢查事件。"""
    connection.execute(
        """
        INSERT INTO check_events (
            watch_item_id, checked_at_utc, availability, event_kinds_json,
            normalized_price_amount, currency, error_code, notification_status,
            sent_channels_json, throttled_channels_json, failed_channels_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.watch_item_id,
            datetime_to_text(event.checked_at),
            event.availability.value,
            json.dumps(list(event.event_kinds)),
            decimal_to_text(event.normalized_price_amount),
            event.currency,
            event.error_code,
            event.notification_status.value,
            json.dumps(list(event.sent_channels)),
            json.dumps(list(event.throttled_channels)),
            json.dumps(list(event.failed_channels)),
        ),
    )


def write_price_history(connection: Connection, entry: PriceHistoryEntry) -> None:
    """在既有 connection 上追加成功價格歷史。"""
    connection.execute(
        """
        INSERT INTO price_history (
            watch_item_id, captured_at_utc, display_price_text,
            normalized_price_amount, currency, source_kind
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            entry.watch_item_id,
            datetime_to_text(entry.captured_at),
            entry.display_price_text,
            str(entry.normalized_price_amount),
            entry.currency,
            entry.source_kind.value,
        ),
    )


def write_notification_state(
    connection: Connection,
    state: NotificationState,
) -> None:
    """在既有 connection 上保存通知去重狀態。"""
    connection.execute(
        """
        INSERT INTO notification_states (
            watch_item_id, last_notified_price, last_notified_availability,
            last_notified_at_utc, consecutive_failures,
            consecutive_parse_failures, degraded_notified_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(watch_item_id) DO UPDATE SET
            last_notified_price = excluded.last_notified_price,
            last_notified_availability = excluded.last_notified_availability,
            last_notified_at_utc = excluded.last_notified_at_utc,
            consecutive_failures = excluded.consecutive_failures,
            consecutive_parse_failures = excluded.consecutive_parse_failures,
            degraded_notified_at_utc = excluded.degraded_notified_at_utc
        """,
        (
            state.watch_item_id,
            decimal_to_text(state.last_notified_price),
            None
            if state.last_notified_availability is None
            else state.last_notified_availability.value,
            datetime_to_text(state.last_notified_at),
            state.consecutive_failures,
            state.consecutive_parse_failures,
            datetime_to_text(state.degraded_notified_at),
        ),
    )


def write_debug_artifact(
    connection: Connection,
    artifact: DebugArtifact,
    *,
    retention_limit: int,
) -> None:
    """在既有 connection 上追加 debug artifact 並套用保留上限。"""
    connection.execute(
        """
        INSERT INTO debug_artifacts (
            watch_item_id, captured_at_utc, reason, payload_text, source_url, http_status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            artifact.watch_item_id,
            datetime_to_text(artifact.captured_at),
            artifact.reason,
            artifact.payload_text,
            artifact.source_url,
            artifact.http_status,
        ),
    )
    if retention_limit > 0:
        connection.execute(
            """
            DELETE FROM debug_artifacts
            WHERE watch_item_id = ?
              AND id NOT IN (
                SELECT id FROM debug_artifacts
                WHERE watch_item_id = ?
                ORDER BY captured_at_utc DESC, id DESC
                LIMIT ?
              )
            """,
            (artifact.watch_item_id, artifact.watch_item_id, retention_limit),
        )


def write_runtime_state_event(
    connection: Connection,
    event: RuntimeStateEvent,
) -> None:
    """在既有 connection 上追加 runtime 狀態轉移事件。"""
    connection.execute(
        """
        INSERT INTO runtime_state_events (
            watch_item_id, occurred_at_utc, event_kind, from_state, to_state, detail_text
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event.watch_item_id,
            datetime_to_text(event.occurred_at),
            event.event_kind.value,
            None if event.from_state is None else event.from_state.value,
            None if event.to_state is None else event.to_state.value,
            event.detail_text,
        ),
    )
