"""watch item SQLite row mapping 與寫入 helper。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from sqlite3 import Connection, Row

from app.domain.entities import WatchItem
from app.domain.value_objects import WatchTarget
from app.infrastructure.db.sqlite_serializers import (
    datetime_to_text,
    deserialize_notification_rule,
    serialize_notification_rule,
    text_to_datetime,
)


def row_to_watch_item(row: Row) -> WatchItem:
    """把 watch_items 資料列轉回 domain 的 watch item。"""
    return WatchItem(
        id=row["id"],
        target=WatchTarget(
            site=row["site"],
            hotel_id=row["hotel_id"],
            room_id=row["room_id"],
            plan_id=row["plan_id"],
            check_in_date=date.fromisoformat(row["check_in_date"]),
            check_out_date=date.fromisoformat(row["check_out_date"]),
            people_count=row["people_count"],
            room_count=row["room_count"],
        ),
        hotel_name=row["hotel_name"],
        room_name=row["room_name"],
        plan_name=row["plan_name"],
        canonical_url=row["canonical_url"],
        notification_rule=deserialize_notification_rule(
            json.loads(row["notification_rule_json"])
        ),
        scheduler_interval_seconds=row["scheduler_interval_seconds"],
        enabled=bool(row["enabled"]),
        paused_reason=row["paused_reason"],
        created_at=text_to_datetime(row["created_at_utc"]),
        updated_at=text_to_datetime(row["updated_at_utc"]),
    )


def save_watch_item(connection: Connection, watch_item: WatchItem) -> None:
    """在既有 transaction 內新增或更新 watch item control state 與設定。"""
    target = watch_item.target
    created_at_text = datetime_to_text(watch_item.created_at) or datetime_to_text(
        datetime.now(UTC)
    )
    updated_at_text = datetime_to_text(watch_item.updated_at) or datetime_to_text(
        datetime.now(UTC)
    )
    connection.execute(
        """
        INSERT INTO watch_items (
            id, site, hotel_id, room_id, plan_id,
            check_in_date, check_out_date, people_count, room_count,
            hotel_name, room_name, plan_name, canonical_url,
            notification_rule_json, scheduler_interval_seconds,
            enabled, paused_reason, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            site = excluded.site,
            hotel_id = excluded.hotel_id,
            room_id = excluded.room_id,
            plan_id = excluded.plan_id,
            check_in_date = excluded.check_in_date,
            check_out_date = excluded.check_out_date,
            people_count = excluded.people_count,
            room_count = excluded.room_count,
            hotel_name = excluded.hotel_name,
            room_name = excluded.room_name,
            plan_name = excluded.plan_name,
            canonical_url = excluded.canonical_url,
            notification_rule_json = excluded.notification_rule_json,
            scheduler_interval_seconds = excluded.scheduler_interval_seconds,
            enabled = excluded.enabled,
            paused_reason = excluded.paused_reason,
            updated_at_utc = COALESCE(excluded.updated_at_utc, CURRENT_TIMESTAMP)
        """,
        (
            watch_item.id,
            target.site,
            target.hotel_id,
            target.room_id,
            target.plan_id,
            target.check_in_date.isoformat(),
            target.check_out_date.isoformat(),
            target.people_count,
            target.room_count,
            watch_item.hotel_name,
            watch_item.room_name,
            watch_item.plan_name,
            watch_item.canonical_url,
            json.dumps(serialize_notification_rule(watch_item.notification_rule)),
            watch_item.scheduler_interval_seconds,
            int(watch_item.enabled),
            watch_item.paused_reason,
            created_at_text,
            updated_at_text,
        ),
    )
