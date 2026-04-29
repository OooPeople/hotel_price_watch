"""runtime 相關 SQLite repository façade。"""

from __future__ import annotations

from datetime import datetime

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
from app.domain.enums import Availability
from app.infrastructure.db import runtime_history_queries
from app.infrastructure.db.notification_throttle_records import (
    get_notification_throttle_state,
    save_notification_throttle_state,
)
from app.infrastructure.db.runtime_fragment_queries import (
    watch_detail_revision_token,
    watch_list_revision_token,
)
from app.infrastructure.db.runtime_write_records import (
    write_check_event,
    write_debug_artifact,
    write_latest_check_snapshot,
    write_notification_state,
    write_price_history,
    write_runtime_state_event,
)
from app.infrastructure.db.schema import SqliteDatabase
from app.infrastructure.db.watch_item_records import save_watch_item


class SqliteRuntimeWriteRepository:
    """提供 runtime 寫入路徑需要的最小 SQLite façade。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立 runtime write façade，直接持有 SQLite database。"""
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
        """以單一 transaction 保存單次 runtime 檢查結果。"""
        with self._database.connect() as connection:
            write_latest_check_snapshot(connection, latest_snapshot)
            write_check_event(connection, check_event)
            if price_history_entry is not None:
                write_price_history(connection, price_history_entry)
            write_notification_state(connection, notification_state)
            for runtime_state_event in runtime_state_events:
                write_runtime_state_event(connection, runtime_state_event)
            if control_watch_item is not None:
                save_watch_item(connection, control_watch_item)
            if debug_artifact is not None:
                write_debug_artifact(
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
        """保存建立 watch 時從 preview 取得的初始價格資料。"""
        with self._database.connect() as connection:
            write_latest_check_snapshot(connection, latest_snapshot)
            write_check_event(connection, check_event)
            write_price_history(connection, price_history_entry)

    def save_latest_check_snapshot(self, snapshot: LatestCheckSnapshot) -> None:
        """保存最新檢查摘要，供測試或 application service 使用。"""
        with self._database.connect() as connection:
            write_latest_check_snapshot(connection, snapshot)

    def append_check_event(self, event: CheckEvent) -> None:
        """追加單次檢查事件。"""
        with self._database.connect() as connection:
            write_check_event(connection, event)

    def append_price_history(self, entry: PriceHistoryEntry) -> None:
        """追加成功價格歷史。"""
        with self._database.connect() as connection:
            write_price_history(connection, entry)

    def save_notification_state(self, state: NotificationState) -> None:
        """保存通知去重狀態。"""
        with self._database.connect() as connection:
            write_notification_state(connection, state)

    def save_notification_throttle_state(
        self,
        state: NotificationThrottleState,
    ) -> None:
        """保存通道級節流所需的最近成功發送時間。"""
        with self._database.connect() as connection:
            save_notification_throttle_state(connection, state)

    def get_notification_throttle_state(
        self,
        *,
        channel_name: str,
        dedupe_key: str,
    ) -> NotificationThrottleState | None:
        """讀出通道級節流狀態；不存在時回傳 `None`。"""
        with self._database.connect() as connection:
            return get_notification_throttle_state(
                connection,
                channel_name=channel_name,
                dedupe_key=dedupe_key,
            )

    def append_debug_artifact(
        self,
        artifact: DebugArtifact,
        *,
        retention_limit: int,
    ) -> None:
        """追加 runtime debug artifact 並套用保留上限。"""
        with self._database.connect() as connection:
            write_debug_artifact(
                connection,
                artifact,
                retention_limit=retention_limit,
            )

    def append_runtime_state_event(self, event: RuntimeStateEvent) -> None:
        """追加 runtime 狀態轉移事件。"""
        with self._database.connect() as connection:
            write_runtime_state_event(connection, event)


class SqliteRuntimeHistoryQueryRepository:
    """提供 runtime 與頁面 read model 需要的歷史查詢 façade。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立 runtime history query façade，直接持有 SQLite database。"""
        self._database = database

    def get_latest_check_snapshot(
        self,
        watch_item_id: str,
    ) -> LatestCheckSnapshot | None:
        """讀出單一 watch item 的最新檢查摘要。"""
        return runtime_history_queries.get_latest_check_snapshot(
            self._database,
            watch_item_id,
        )

    def get_last_effective_availability(self, watch_item_id: str) -> Availability | None:
        """回溯最近一次明確可判定的 availability。"""
        return runtime_history_queries.get_last_effective_availability(
            self._database,
            watch_item_id,
        )

    def list_check_events(self, watch_item_id: str) -> list[CheckEvent]:
        """列出單一 watch item 的檢查歷史。"""
        return runtime_history_queries.list_check_events(self._database, watch_item_id)

    def list_price_history(self, watch_item_id: str) -> list[PriceHistoryEntry]:
        """列出單一 watch item 的成功價格歷史。"""
        return runtime_history_queries.list_price_history(
            self._database,
            watch_item_id,
        )

    def list_price_history_since(
        self,
        *,
        watch_item_ids: tuple[str, ...],
        since: datetime,
    ) -> dict[str, tuple[PriceHistoryEntry, ...]]:
        """批次讀取多個 watch item 在指定時間後的成功價格歷史。"""
        return runtime_history_queries.list_price_history_since(
            self._database,
            watch_item_ids=watch_item_ids,
            since=since,
        )

    def count_notifications_since(self, since: datetime) -> int:
        """統計指定時間後已送出或部分成功的通知事件數。"""
        return runtime_history_queries.count_notifications_since(self._database, since)

    def get_notification_state(self, watch_item_id: str) -> NotificationState | None:
        """讀出單一 watch item 的通知去重狀態。"""
        return runtime_history_queries.get_notification_state(
            self._database,
            watch_item_id,
        )

    def list_runtime_state_events(self, watch_item_id: str) -> list[RuntimeStateEvent]:
        """依時間倒序列出 watch 的 runtime 狀態轉移事件。"""
        return runtime_history_queries.list_runtime_state_events(
            self._database,
            watch_item_id,
        )

    def list_debug_artifacts(self, watch_item_id: str) -> list[DebugArtifact]:
        """依時間列出 watch 的 debug artifacts。"""
        return runtime_history_queries.list_debug_artifacts(
            self._database,
            watch_item_id,
        )


class SqliteRuntimeFragmentQueryRepository:
    """提供前端 fragment polling 版本 token 的 SQLite façade。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立 fragment query façade，直接持有 SQLite database。"""
        self._database = database

    def get_watch_list_revision_token(
        self,
        *,
        price_history_since: datetime,
        notification_since: datetime,
    ) -> str:
        """回傳首頁可見 runtime 資料目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return watch_list_revision_token(
                connection,
                price_history_since=price_history_since,
                notification_since=notification_since,
            )

    def get_watch_detail_revision_token(self, watch_item_id: str) -> str:
        """回傳 watch 詳細頁可見 runtime 資料目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return watch_detail_revision_token(connection, watch_item_id)


class SqliteNotificationThrottleStateRepository:
    """提供通知通道節流狀態需要的最小 SQLite façade。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立 notification throttle state façade。"""
        self._database = database

    def save_notification_throttle_state(
        self,
        state: NotificationThrottleState,
    ) -> None:
        """保存通道級節流所需的最近成功發送時間。"""
        with self._database.connect() as connection:
            save_notification_throttle_state(connection, state)

    def get_notification_throttle_state(
        self,
        *,
        channel_name: str,
        dedupe_key: str,
    ) -> NotificationThrottleState | None:
        """讀出通道級節流狀態；不存在時回傳 `None`。"""
        with self._database.connect() as connection:
            return get_notification_throttle_state(
                connection,
                channel_name=channel_name,
                dedupe_key=dedupe_key,
            )
