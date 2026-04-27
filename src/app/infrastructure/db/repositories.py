"""SQLite repositories 與序列化 helpers。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from sqlite3 import Connection, Row

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    NotificationThrottleState,
    PriceHistoryEntry,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    LogicalOperator,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    RuntimeStateEventKind,
    SourceKind,
    WatchRuntimeState,
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
        with self._database.connect() as connection:
            _save_watch_item(connection, watch_item)

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

    def get_collection_revision_token(self) -> str:
        """回傳 watch item 集合目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return _rows_revision_token(
                connection,
                """
                SELECT
                    id, site, hotel_id, room_id, plan_id, check_in_date,
                    check_out_date, people_count, room_count, hotel_name,
                    room_name, plan_name, canonical_url, notification_rule_json,
                    scheduler_interval_seconds, enabled, paused_reason,
                    created_at_utc, updated_at_utc
                FROM watch_items
                ORDER BY id
                """,
            )

    def get_revision_token(self, watch_item_id: str) -> str:
        """回傳單一 watch item 定義目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return _rows_revision_token(
                connection,
                """
                SELECT
                    id, site, hotel_id, room_id, plan_id, check_in_date,
                    check_out_date, people_count, room_count, hotel_name,
                    room_name, plan_name, canonical_url, notification_rule_json,
                    scheduler_interval_seconds, enabled, paused_reason,
                    created_at_utc, updated_at_utc
                FROM watch_items
                WHERE id = ?
                """,
                (watch_item_id,),
            )

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

    def persist_check_outcome(
        self,
        *,
        latest_snapshot: LatestCheckSnapshot,
        check_event: CheckEvent,
        notification_state: NotificationState,
        control_watch_item: WatchItem | None = None,
        price_history_entry: PriceHistoryEntry | None = None,
        debug_artifact: DebugArtifact | None = None,
        runtime_state_events: tuple[RuntimeStateEvent, ...] = (),
        debug_retention_limit: int = 20,
    ) -> None:
        """以單一 transaction 保存單次檢查的所有持久化結果。"""
        with self._database.connect() as connection:
            self._save_latest_check_snapshot(connection, latest_snapshot)
            self._append_check_event(connection, check_event)
            if price_history_entry is not None:
                self._append_price_history(connection, price_history_entry)
            self._save_notification_state(connection, notification_state)
            for runtime_state_event in runtime_state_events:
                self._append_runtime_state_event(connection, runtime_state_event)
            if control_watch_item is not None:
                _save_watch_item(connection, control_watch_item)
            if debug_artifact is not None:
                self._append_debug_artifact(
                    connection,
                    debug_artifact,
                    retention_limit=debug_retention_limit,
                )

    def persist_initial_check_snapshot(
        self,
        *,
        latest_snapshot: LatestCheckSnapshot,
        check_event: CheckEvent,
        price_history_entry: PriceHistoryEntry,
    ) -> None:
        """以單一 transaction 保存建立 watch 時已取得的初始價格資料。"""
        with self._database.connect() as connection:
            self._save_latest_check_snapshot(connection, latest_snapshot)
            self._append_check_event(connection, check_event)
            self._append_price_history(connection, price_history_entry)

    def save_latest_check_snapshot(self, snapshot: LatestCheckSnapshot) -> None:
        """新增或更新 watch item 的最新檢查摘要。"""
        with self._database.connect() as connection:
            self._save_latest_check_snapshot(connection, snapshot)

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

    def get_last_effective_availability(self, watch_item_id: str) -> Availability | None:
        """回溯最近一次明確可判定的 availability，只接受 available/sold_out。"""
        with self._database.connect() as connection:
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

    def append_check_event(self, event: CheckEvent) -> None:
        """追加單次檢查事件，保留完整事件列表。"""
        with self._database.connect() as connection:
            self._append_check_event(connection, event)

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
            self._append_price_history(connection, entry)

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

    def list_price_history_since(
        self,
        *,
        watch_item_ids: tuple[str, ...],
        since: datetime,
    ) -> dict[str, tuple[PriceHistoryEntry, ...]]:
        """批次讀取多個 watch item 在指定時間後的成功價格歷史。"""
        if not watch_item_ids:
            return {}
        placeholders = ", ".join("?" for _ in watch_item_ids)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM price_history
                WHERE watch_item_id IN ({placeholders})
                  AND captured_at_utc >= ?
                ORDER BY watch_item_id, captured_at_utc, id
                """,
                (*watch_item_ids, _datetime_to_text(since)),
            ).fetchall()
        grouped: dict[str, list[PriceHistoryEntry]] = {
            watch_item_id: [] for watch_item_id in watch_item_ids
        }
        for row in rows:
            grouped[row["watch_item_id"]].append(
                PriceHistoryEntry(
                    watch_item_id=row["watch_item_id"],
                    captured_at=_text_to_datetime(row["captured_at_utc"]),
                    display_price_text=row["display_price_text"],
                    normalized_price_amount=Decimal(row["normalized_price_amount"]),
                    currency=row["currency"],
                    source_kind=SourceKind(row["source_kind"]),
                )
            )
        return {
            watch_item_id: tuple(entries)
            for watch_item_id, entries in grouped.items()
        }

    def count_notifications_since(self, since: datetime) -> int:
        """統計指定時間後已送出或部分成功的通知事件數。"""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM check_events
                WHERE checked_at_utc >= ?
                  AND notification_status IN (?, ?)
                """,
                (
                    _datetime_to_text(since),
                    NotificationDeliveryStatus.SENT.value,
                    NotificationDeliveryStatus.PARTIAL.value,
                ),
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def get_watch_list_revision_token(
        self,
        *,
        price_history_since: datetime,
        notification_since: datetime,
    ) -> str:
        """回傳首頁可見 runtime 資料目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return _hash_revision_parts(
                (
                    _rows_revision_token(
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
                    _rows_revision_token(
                        connection,
                        """
                        SELECT
                            watch_item_id, captured_at_utc, display_price_text,
                            normalized_price_amount, currency, source_kind
                        FROM price_history
                        WHERE captured_at_utc >= ?
                        ORDER BY watch_item_id, captured_at_utc, id
                        """,
                        (_datetime_to_text(price_history_since),),
                    ),
                    _rows_revision_token(
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
                            _datetime_to_text(notification_since),
                            NotificationDeliveryStatus.SENT.value,
                            NotificationDeliveryStatus.PARTIAL.value,
                        ),
                    ),
                )
            )

    def get_watch_detail_revision_token(self, watch_item_id: str) -> str:
        """回傳 watch 詳細頁可見 runtime 資料目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return _hash_revision_parts(
                (
                    _rows_revision_token(
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
                    _rows_revision_token(
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
                    _rows_revision_token(
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
                    _rows_revision_token(
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
                    _rows_revision_token(
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

    def save_notification_state(self, state: NotificationState) -> None:
        """新增或更新去重用的通知狀態。"""
        with self._database.connect() as connection:
            self._save_notification_state(connection, state)

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
            self._append_debug_artifact(
                connection,
                artifact,
                retention_limit=retention_limit,
            )

    def append_runtime_state_event(self, event: RuntimeStateEvent) -> None:
        """追加單一 runtime 狀態事件。"""
        with self._database.connect() as connection:
            self._append_runtime_state_event(connection, event)

    def list_runtime_state_events(self, watch_item_id: str) -> list[RuntimeStateEvent]:
        """依時間倒序列出 watch 的 runtime 狀態轉移事件。"""
        with self._database.connect() as connection:
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
                occurred_at=_text_to_datetime(row["occurred_at_utc"]),
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

    def _save_latest_check_snapshot(
        self,
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

    def _append_check_event(
        self,
        connection: Connection,
        event: CheckEvent,
    ) -> None:
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

    def _append_price_history(
        self,
        connection: Connection,
        entry: PriceHistoryEntry,
    ) -> None:
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
                _datetime_to_text(entry.captured_at),
                entry.display_price_text,
                str(entry.normalized_price_amount),
                entry.currency,
                entry.source_kind.value,
            ),
        )

    def _save_notification_state(
        self,
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

    def _append_debug_artifact(
        self,
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

    def _append_runtime_state_event(
        self,
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
                _datetime_to_text(event.occurred_at),
                event.event_kind.value,
                None if event.from_state is None else event.from_state.value,
                None if event.to_state is None else event.to_state.value,
                event.detail_text,
            ),
        )


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

    def get_display_settings(self) -> DisplaySettings:
        """讀出 GUI 顯示設定；若尚未保存則回預設值。"""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM display_settings
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return DisplaySettings()
        return DisplaySettings(
            use_24_hour_time=bool(row["use_24_hour_time"]),
        )

    def get_display_settings_revision_token(self) -> str:
        """回傳會影響 GUI 時間格式的顯示設定版本 token。"""
        with self._database.connect() as connection:
            return _rows_revision_token(
                connection,
                """
                SELECT use_24_hour_time, updated_at_utc
                FROM display_settings
                WHERE singleton_id = 1
                """,
            )

    def save_display_settings(self, settings: DisplaySettings) -> DisplaySettings:
        """保存 GUI 顯示設定。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO display_settings (
                    singleton_id, use_24_hour_time, updated_at_utc
                ) VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    use_24_hour_time = excluded.use_24_hour_time,
                    updated_at_utc = CURRENT_TIMESTAMP
                """,
                (int(settings.use_24_hour_time),),
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


def _save_watch_item(connection: Connection, watch_item: WatchItem) -> None:
    """在既有 transaction 內新增或更新 watch item control state 與設定。"""
    target = watch_item.target
    created_at_text = _datetime_to_text(watch_item.created_at) or _datetime_to_text(
        datetime.now(UTC)
    )
    updated_at_text = _datetime_to_text(watch_item.updated_at) or _datetime_to_text(
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
            json.dumps(_serialize_notification_rule(watch_item.notification_rule)),
            watch_item.scheduler_interval_seconds,
            int(watch_item.enabled),
            watch_item.paused_reason,
            created_at_text,
            updated_at_text,
        ),
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


def _rows_revision_token(
    connection: Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> str:
    """把指定查詢結果轉成穩定 hash，供 web fragment 版本判斷。"""
    rows = connection.execute(query, parameters).fetchall()
    digest = hashlib.sha256()
    for row in rows:
        for key in row.keys():
            value = row[key]
            digest.update(str(key).encode("utf-8"))
            digest.update(b"=")
            digest.update(str(value if value is not None else "").encode("utf-8"))
            digest.update(b"\x1f")
        digest.update(b"\x1e")
    return digest.hexdigest()


def _hash_revision_parts(parts: tuple[str, ...]) -> str:
    """合併多個子版本 token，避免上層知道各資料表細節。"""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


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
