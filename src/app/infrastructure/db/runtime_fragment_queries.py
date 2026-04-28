"""runtime fragment polling 使用的 SQLite revision 查詢。"""

from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection

from app.domain.enums import NotificationDeliveryStatus
from app.infrastructure.db.sqlite_revision import hash_revision_parts, rows_revision_token
from app.infrastructure.db.sqlite_serializers import datetime_to_text


def watch_list_revision_token(
    connection: Connection,
    *,
    price_history_since: datetime,
    notification_since: datetime,
) -> str:
    """在既有 connection 上建立首頁 runtime fragment revision token。"""
    return hash_revision_parts(
        (
            rows_revision_token(
                connection,
                """
                SELECT
                    watch_item_id, checked_at_utc, availability,
                    normalized_price_amount, currency, backoff_until_utc,
                    is_degraded, consecutive_failures, last_error_code
                FROM latest_check_snapshots
                ORDER BY watch_item_id
                """,
            ),
            rows_revision_token(
                connection,
                """
                SELECT
                    watch_item_id, captured_at_utc, display_price_text,
                    normalized_price_amount, currency, source_kind
                FROM price_history
                WHERE captured_at_utc >= ?
                ORDER BY watch_item_id, captured_at_utc, id
                """,
                (datetime_to_text(price_history_since),),
            ),
            rows_revision_token(
                connection,
                """
                SELECT
                    checked_at_utc, notification_status
                FROM check_events
                WHERE checked_at_utc >= ?
                  AND notification_status IN (?, ?)
                ORDER BY checked_at_utc, id
                """,
                (
                    datetime_to_text(notification_since),
                    NotificationDeliveryStatus.SENT.value,
                    NotificationDeliveryStatus.PARTIAL.value,
                ),
            ),
        )
    )


def watch_detail_revision_token(
    connection: Connection,
    watch_item_id: str,
) -> str:
    """在既有 connection 上建立詳細頁 runtime fragment revision token。"""
    return hash_revision_parts(
        (
            rows_revision_token(
                connection,
                """
                SELECT
                    watch_item_id, checked_at_utc, availability,
                    normalized_price_amount, currency, backoff_until_utc,
                    is_degraded, consecutive_failures, last_error_code
                FROM latest_check_snapshots
                WHERE watch_item_id = ?
                """,
                (watch_item_id,),
            ),
            rows_revision_token(
                connection,
                """
                SELECT
                    checked_at_utc, availability, event_kinds_json,
                    normalized_price_amount, currency, error_code,
                    notification_status, sent_channels_json,
                    throttled_channels_json, failed_channels_json
                FROM check_events
                WHERE watch_item_id = ?
                ORDER BY checked_at_utc, id
                """,
                (watch_item_id,),
            ),
            rows_revision_token(
                connection,
                """
                SELECT
                    last_notified_price, last_notified_availability,
                    last_notified_at_utc, consecutive_failures,
                    consecutive_parse_failures, degraded_notified_at_utc
                FROM notification_states
                WHERE watch_item_id = ?
                """,
                (watch_item_id,),
            ),
            rows_revision_token(
                connection,
                """
                SELECT
                    captured_at_utc, reason, payload_text, source_url,
                    http_status
                FROM debug_artifacts
                WHERE watch_item_id = ?
                ORDER BY captured_at_utc, id
                """,
                (watch_item_id,),
            ),
            rows_revision_token(
                connection,
                """
                SELECT
                    occurred_at_utc, event_kind, from_state, to_state,
                    detail_text
                FROM runtime_state_events
                WHERE watch_item_id = ?
                ORDER BY occurred_at_utc, id
                """,
                (watch_item_id,),
            ),
        )
    )
