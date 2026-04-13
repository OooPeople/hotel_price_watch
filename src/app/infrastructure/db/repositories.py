"""SQLite repositories 與序列化 helpers。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlite3 import Row

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
    LogicalOperator,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import CompositeRule, NotificationRule, RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.db.schema import SqliteDatabase


class SqliteWatchItemRepository:
    """負責 `watch_items` 與 `watch_item_drafts` 的持久化。"""

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def save(self, watch_item: WatchItem) -> None:
        """新增或更新 watch item，不把 runtime 狀態混進資料表。"""
        target = watch_item.target
        created_at_text = _datetime_to_text(watch_item.created_at) or _datetime_to_text(
            datetime.now(UTC)
        )
        updated_at_text = _datetime_to_text(watch_item.updated_at) or _datetime_to_text(
            datetime.now(UTC)
        )
        with self._database.connect() as connection:
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
                    json.dumps(_serialize_notification_rule(watch_item.notification_rule)),
                    watch_item.scheduler_interval_seconds,
                    int(watch_item.enabled),
                    watch_item.paused_reason,
                    created_at_text,
                    updated_at_text,
                ),
            )

    def get(self, watch_item_id: str) -> WatchItem | None:
        """依 id 載入單一 watch item。"""
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM watch_items WHERE id = ?",
                (watch_item_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_watch_item(row)

    def list_all(self) -> list[WatchItem]:
        """依建立順序列出所有 watch item。"""
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM watch_items ORDER BY created_at_utc, id",
            ).fetchall()
        return [_row_to_watch_item(row) for row in rows]

    def delete(self, watch_item_id: str) -> None:
        """刪除 watch item，依 foreign key 一併清掉附屬資料。"""
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM watch_items WHERE id = ?",
                (watch_item_id,),
            )

    def save_draft(self, watch_item_id: str, draft: SearchDraft) -> None:
        """分開保存 UI 草稿，避免與正式 watch target 混在一起。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO watch_item_drafts (
                    watch_item_id, seed_url, check_in_date, check_out_date,
                    people_count, room_count, hotel_id, room_id, plan_id,
                    browser_tab_id, browser_page_url, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(watch_item_id) DO UPDATE SET
                    seed_url = excluded.seed_url,
                    check_in_date = excluded.check_in_date,
                    check_out_date = excluded.check_out_date,
                    people_count = excluded.people_count,
                    room_count = excluded.room_count,
                    hotel_id = excluded.hotel_id,
                    room_id = excluded.room_id,
                    plan_id = excluded.plan_id,
                    browser_tab_id = excluded.browser_tab_id,
                    browser_page_url = excluded.browser_page_url,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    watch_item_id,
                    draft.seed_url,
                    _date_to_text(draft.check_in_date),
                    _date_to_text(draft.check_out_date),
                    draft.people_count,
                    draft.room_count,
                    draft.hotel_id,
                    draft.room_id,
                    draft.plan_id,
                    draft.browser_tab_id,
                    draft.browser_page_url,
                    _datetime_to_text(datetime.now(UTC)),
                ),
            )

    def get_draft(self, watch_item_id: str) -> SearchDraft | None:
        """讀出與 watch item 分離保存的 UI 草稿。"""
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM watch_item_drafts WHERE watch_item_id = ?",
                (watch_item_id,),
            ).fetchone()
        if row is None:
            return None
        return SearchDraft(
            seed_url=row["seed_url"],
            check_in_date=_text_to_date(row["check_in_date"]),
            check_out_date=_text_to_date(row["check_out_date"]),
            people_count=row["people_count"],
            room_count=row["room_count"],
            hotel_id=row["hotel_id"],
            room_id=row["room_id"],
            plan_id=row["plan_id"],
            browser_tab_id=row["browser_tab_id"],
            browser_page_url=row["browser_page_url"],
        )


class SqliteRuntimeRepository:
    """負責最新狀態、歷史、通知狀態與 debug artifact 的持久化。"""

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def save_latest_check_snapshot(self, snapshot: LatestCheckSnapshot) -> None:
        """新增或更新 watch item 的最新檢查摘要。"""
        with self._database.connect() as connection:
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
                    _datetime_to_text(snapshot.checked_at),
                    snapshot.availability.value,
                    _decimal_to_text(snapshot.normalized_price_amount),
                    snapshot.currency,
                    _datetime_to_text(snapshot.backoff_until),
                    int(snapshot.is_degraded),
                    snapshot.consecutive_failures,
                    snapshot.last_error_code,
                ),
            )

    def get_latest_check_snapshot(self, watch_item_id: str) -> LatestCheckSnapshot | None:
        """讀出單一 watch item 的最新檢查摘要。"""
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM latest_check_snapshots WHERE watch_item_id = ?",
                (watch_item_id,),
            ).fetchone()
        if row is None:
            return None
        return LatestCheckSnapshot(
            watch_item_id=row["watch_item_id"],
            checked_at=_text_to_datetime(row["checked_at_utc"]),
            availability=Availability(row["availability"]),
            normalized_price_amount=_text_to_decimal(row["normalized_price_amount"]),
            currency=row["currency"],
            backoff_until=_text_to_datetime(row["backoff_until_utc"]),
            is_degraded=bool(row["is_degraded"]),
            consecutive_failures=row["consecutive_failures"],
            last_error_code=row["last_error_code"],
        )

    def append_check_event(self, event: CheckEvent) -> None:
        """追加單次檢查事件，保留完整事件列表。"""
        with self._database.connect() as connection:
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
                    _datetime_to_text(event.checked_at),
                    event.availability.value,
                    json.dumps(list(event.event_kinds)),
                    _decimal_to_text(event.normalized_price_amount),
                    event.currency,
                    event.error_code,
                    event.notification_status.value,
                    json.dumps(list(event.sent_channels)),
                    json.dumps(list(event.throttled_channels)),
                    json.dumps(list(event.failed_channels)),
                ),
            )

    def list_check_events(self, watch_item_id: str) -> list[CheckEvent]:
        """依時間列出某個 watch item 的檢查歷史。"""
        with self._database.connect() as connection:
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
                checked_at=_text_to_datetime(row["checked_at_utc"]),
                availability=Availability(row["availability"]),
                event_kinds=tuple(json.loads(row["event_kinds_json"])),
                normalized_price_amount=_text_to_decimal(row["normalized_price_amount"]),
                currency=row["currency"],
                error_code=row["error_code"],
                notification_status=NotificationDeliveryStatus(row["notification_status"]),
                sent_channels=tuple(json.loads(row["sent_channels_json"])),
                throttled_channels=tuple(json.loads(row["throttled_channels_json"])),
                failed_channels=tuple(json.loads(row["failed_channels_json"])),
            )
            for row in rows
        ]

    def append_price_history(self, entry: PriceHistoryEntry) -> None:
        """追加成功價格點，供價格曲線與歷史頁使用。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO price_history (
                    watch_item_id, captured_at_utc, display_price_text,
                    normalized_price_amount, currency, source_kind
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.watch_item_id,
                    _datetime_to_text(entry.captured_at),
                    entry.display_price_text,
                    str(entry.normalized_price_amount),
                    entry.currency,
                    entry.source_kind.value,
                ),
            )

    def list_price_history(self, watch_item_id: str) -> list[PriceHistoryEntry]:
        """依時間列出某個 watch item 的成功價格歷史。"""
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM price_history
                WHERE watch_item_id = ?
                ORDER BY captured_at_utc, id
                """,
                (watch_item_id,),
            ).fetchall()
        return [
            PriceHistoryEntry(
                watch_item_id=row["watch_item_id"],
                captured_at=_text_to_datetime(row["captured_at_utc"]),
                display_price_text=row["display_price_text"],
                normalized_price_amount=Decimal(row["normalized_price_amount"]),
                currency=row["currency"],
                source_kind=SourceKind(row["source_kind"]),
            )
            for row in rows
        ]

    def save_notification_state(self, state: NotificationState) -> None:
        """新增或更新去重用的通知狀態。"""
        with self._database.connect() as connection:
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
                    _decimal_to_text(state.last_notified_price),
                    None
                    if state.last_notified_availability is None
                    else state.last_notified_availability.value,
                    _datetime_to_text(state.last_notified_at),
                    state.consecutive_failures,
                    state.consecutive_parse_failures,
                    _datetime_to_text(state.degraded_notified_at),
                ),
            )

    def get_notification_state(self, watch_item_id: str) -> NotificationState | None:
        """讀出單一 watch item 的通知去重狀態。"""
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM notification_states WHERE watch_item_id = ?",
                (watch_item_id,),
            ).fetchone()
        if row is None:
            return None
        return NotificationState(
            watch_item_id=row["watch_item_id"],
            last_notified_price=_text_to_decimal(row["last_notified_price"]),
            last_notified_availability=None
            if row["last_notified_availability"] is None
            else Availability(row["last_notified_availability"]),
            last_notified_at=_text_to_datetime(row["last_notified_at_utc"]),
            consecutive_failures=row["consecutive_failures"],
            consecutive_parse_failures=row["consecutive_parse_failures"],
            degraded_notified_at=_text_to_datetime(row["degraded_notified_at_utc"]),
        )

    def save_notification_throttle_state(
        self,
        state: NotificationThrottleState,
    ) -> None:
        """保存通道級節流所需的最近成功發送時間。"""
        with self._database.connect() as connection:
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
                    _datetime_to_text(state.last_sent_at),
                ),
            )

    def get_notification_throttle_state(
        self,
        *,
        channel_name: str,
        dedupe_key: str,
    ) -> NotificationThrottleState | None:
        """讀出通道級節流狀態；不存在時回傳 `None`。"""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM notification_throttle_states
                WHERE channel_name = ? AND dedupe_key = ?
                """,
                (channel_name, dedupe_key),
            ).fetchone()
        if row is None:
            return None
        last_sent_at = _text_to_datetime(row["last_sent_at_utc"])
        assert last_sent_at is not None
        return NotificationThrottleState(
            channel_name=row["channel_name"],
            dedupe_key=row["dedupe_key"],
            last_sent_at=last_sent_at,
        )

    def append_debug_artifact(self, artifact: DebugArtifact, *, retention_limit: int) -> None:
        """追加 debug artifact，並依 watch item 套用保留上限。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO debug_artifacts (
                    watch_item_id, captured_at_utc, reason, payload_text, source_url, http_status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.watch_item_id,
                    _datetime_to_text(artifact.captured_at),
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

    def list_debug_artifacts(self, watch_item_id: str) -> list[DebugArtifact]:
        """依時間列出 debug artifact，供錯誤排查使用。"""
        with self._database.connect() as connection:
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
                captured_at=_text_to_datetime(row["captured_at_utc"]),
                reason=row["reason"],
                payload_text=row["payload_text"],
                source_url=row["source_url"],
                http_status=row["http_status"],
            )
            for row in rows
        ]


class SqliteAppSettingsRepository:
    """負責全域設定的持久化，與 watch / runtime 狀態分離。"""

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """讀出全域通知通道設定；若尚未保存則回預設值。"""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM notification_channel_settings
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return NotificationChannelSettings()
        return NotificationChannelSettings(
            desktop_enabled=bool(row["desktop_enabled"]),
            ntfy_enabled=bool(row["ntfy_enabled"]),
            ntfy_server_url=row["ntfy_server_url"],
            ntfy_topic=row["ntfy_topic"],
            discord_enabled=bool(row["discord_enabled"]),
            discord_webhook_url=row["discord_webhook_url"],
        )

    def save_notification_channel_settings(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationChannelSettings:
        """保存全域通知通道設定。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_channel_settings (
                    singleton_id, desktop_enabled, ntfy_enabled,
                    ntfy_server_url, ntfy_topic, discord_enabled,
                    discord_webhook_url, updated_at_utc
                ) VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    desktop_enabled = excluded.desktop_enabled,
                    ntfy_enabled = excluded.ntfy_enabled,
                    ntfy_server_url = excluded.ntfy_server_url,
                    ntfy_topic = excluded.ntfy_topic,
                    discord_enabled = excluded.discord_enabled,
                    discord_webhook_url = excluded.discord_webhook_url,
                    updated_at_utc = CURRENT_TIMESTAMP
                """,
                (
                    int(settings.desktop_enabled),
                    int(settings.ntfy_enabled),
                    settings.ntfy_server_url,
                    settings.ntfy_topic,
                    int(settings.discord_enabled),
                    settings.discord_webhook_url,
                ),
            )
        return settings


def _row_to_watch_item(row: Row) -> WatchItem:
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
        notification_rule=_deserialize_notification_rule(json.loads(row["notification_rule_json"])),
        scheduler_interval_seconds=row["scheduler_interval_seconds"],
        enabled=bool(row["enabled"]),
        paused_reason=row["paused_reason"],
        created_at=_text_to_datetime(row["created_at_utc"]),
        updated_at=_text_to_datetime(row["updated_at_utc"]),
    )


def _serialize_notification_rule(rule: NotificationRule) -> dict[str, object]:
    """把 notification rule 轉成可寫入 JSON 的結構。"""
    if isinstance(rule, RuleLeaf):
        return {
            "type": "leaf",
            "kind": rule.kind.value,
            "target_price": _decimal_to_text(rule.target_price),
        }
    return {
        "type": "composite",
        "operator": rule.operator.value,
        "children": [_serialize_notification_rule(child) for child in rule.children],
    }


def _deserialize_notification_rule(payload: dict[str, object]) -> NotificationRule:
    """把 JSON payload 還原成 notification rule。"""
    payload_type = payload["type"]
    if payload_type == "leaf":
        return RuleLeaf(
            kind=NotificationLeafKind(str(payload["kind"])),
            target_price=_text_to_decimal(payload.get("target_price")),
        )
    children = tuple(
        _deserialize_notification_rule(child) for child in payload["children"]  # type: ignore[index]
    )
    return CompositeRule(
        operator=LogicalOperator(str(payload["operator"])),
        children=children,
    )


def _datetime_to_text(value: datetime | None) -> str | None:
    """把 `datetime` 轉成可存入 SQLite 的 ISO 字串。"""
    if value is None:
        return None
    return value.isoformat()


def _text_to_datetime(value: str | None) -> datetime | None:
    """把 SQLite 內的 ISO 字串轉回 `datetime`。"""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _date_to_text(value: date | None) -> str | None:
    """把 `date` 轉成可存入 SQLite 的 ISO 字串。"""
    if value is None:
        return None
    return value.isoformat()


def _text_to_date(value: str | None) -> date | None:
    """把 SQLite 內的 ISO 字串轉回 `date`。"""
    if value is None:
        return None
    return date.fromisoformat(value)


def _decimal_to_text(value: Decimal | str | None) -> str | None:
    """把 `Decimal` 類值轉成 SQLite 內部使用的字串。"""
    if value is None:
        return None
    return str(value)


def _text_to_decimal(value: str | None) -> Decimal | None:
    """把 SQLite 內的字串轉回 `Decimal`。"""
    if value is None:
        return None
    return Decimal(value)
