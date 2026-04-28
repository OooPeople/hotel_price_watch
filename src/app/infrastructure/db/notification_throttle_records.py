"""notification throttle state 的 SQLite record helper。"""

from __future__ import annotations

from sqlite3 import Connection

from app.domain.entities import NotificationThrottleState
from app.infrastructure.db.sqlite_serializers import datetime_to_text, text_to_datetime


def save_notification_throttle_state(
    connection: Connection,
    state: NotificationThrottleState,
) -> None:
    """在既有 connection 上保存通知通道節流狀態。"""
    connection.execute(
        """
        INSERT INTO notification_throttle_states (
            channel_name, dedupe_key, last_sent_at_utc
        ) VALUES (?, ?, ?)
        ON CONFLICT(channel_name, dedupe_key) DO UPDATE SET
            last_sent_at_utc = excluded.last_sent_at_utc
        """,
        (
            state.channel_name,
            state.dedupe_key,
            datetime_to_text(state.last_sent_at),
        ),
    )


def get_notification_throttle_state(
    connection: Connection,
    *,
    channel_name: str,
    dedupe_key: str,
) -> NotificationThrottleState | None:
    """在既有 connection 上讀出通知通道節流狀態。"""
    row = connection.execute(
        """
        SELECT * FROM notification_throttle_states
        WHERE channel_name = ? AND dedupe_key = ?
        """,
        (channel_name, dedupe_key),
    ).fetchone()
    if row is None:
        return None
    last_sent_at = text_to_datetime(row["last_sent_at_utc"])
    assert last_sent_at is not None
    return NotificationThrottleState(
        channel_name=row["channel_name"],
        dedupe_key=row["dedupe_key"],
        last_sent_at=last_sent_at,
    )
