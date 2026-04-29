"""舊 runtime repository 介面的相容 adapter。

此模組只保留舊測試與舊呼叫點需要的整合入口；正式 app wiring 與新功能
不得依賴此類別。所有實作都委派到專用 repository，避免 read/write 邏輯雙軌
漂移。
"""

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
from app.infrastructure.db.runtime_repositories import (
    SqliteNotificationThrottleStateRepository,
    SqliteRuntimeFragmentQueryRepository,
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
)
from app.infrastructure.db.schema import SqliteDatabase


class SqliteRuntimeRepository:
    """相容舊整合介面的薄 adapter；新程式碼請改用專用 repository。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立相容 adapter，內部組合正式 repository owner。"""
        self._write = SqliteRuntimeWriteRepository(database)
        self._history = SqliteRuntimeHistoryQueryRepository(database)
        self._fragment = SqliteRuntimeFragmentQueryRepository(database)
        self._throttle = SqliteNotificationThrottleStateRepository(database)

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
        """委派單次檢查結果持久化到 write repository。"""
        self._write.persist_check_outcome(
            latest_snapshot=latest_snapshot,
            check_event=check_event,
            notification_state=notification_state,
            control_watch_item=control_watch_item,
            price_history_entry=price_history_entry,
            debug_artifact=debug_artifact,
            runtime_state_events=runtime_state_events,
            debug_retention_limit=debug_retention_limit,
        )

    def persist_initial_check_snapshot(
        self,
        *,
        latest_snapshot: LatestCheckSnapshot,
        check_event: CheckEvent,
        price_history_entry: PriceHistoryEntry,
    ) -> None:
        """委派建立 watch 時的初始價格保存到 write repository。"""
        self._write.persist_initial_check_snapshot(
            latest_snapshot=latest_snapshot,
            check_event=check_event,
            price_history_entry=price_history_entry,
        )

    def save_latest_check_snapshot(self, snapshot: LatestCheckSnapshot) -> None:
        """委派最新檢查摘要寫入到 write repository。"""
        self._write.save_latest_check_snapshot(snapshot)

    def get_latest_check_snapshot(self, watch_item_id: str) -> LatestCheckSnapshot | None:
        """委派最新檢查摘要讀取到 history repository。"""
        return self._history.get_latest_check_snapshot(watch_item_id)

    def get_last_effective_availability(self, watch_item_id: str) -> Availability | None:
        """委派最近有效空房狀態讀取到 history repository。"""
        return self._history.get_last_effective_availability(watch_item_id)

    def append_check_event(self, event: CheckEvent) -> None:
        """委派檢查事件追加到 write repository。"""
        self._write.append_check_event(event)

    def list_check_events(self, watch_item_id: str) -> list[CheckEvent]:
        """委派檢查歷史查詢到 history repository。"""
        return self._history.list_check_events(watch_item_id)

    def append_price_history(self, entry: PriceHistoryEntry) -> None:
        """委派成功價格歷史追加到 write repository。"""
        self._write.append_price_history(entry)

    def list_price_history(self, watch_item_id: str) -> list[PriceHistoryEntry]:
        """委派成功價格歷史查詢到 history repository。"""
        return self._history.list_price_history(watch_item_id)

    def list_price_history_since(
        self,
        *,
        watch_item_ids: tuple[str, ...],
        since: datetime,
    ) -> dict[str, tuple[PriceHistoryEntry, ...]]:
        """委派指定區間價格歷史查詢到 history repository。"""
        return self._history.list_price_history_since(
            watch_item_ids=watch_item_ids,
            since=since,
        )

    def count_notifications_since(self, since: datetime) -> int:
        """委派通知計數查詢到 history repository。"""
        return self._history.count_notifications_since(since)

    def get_watch_list_revision_token(
        self,
        *,
        price_history_since: datetime,
        notification_since: datetime,
    ) -> str:
        """委派首頁 fragment revision 查詢到 fragment repository。"""
        return self._fragment.get_watch_list_revision_token(
            price_history_since=price_history_since,
            notification_since=notification_since,
        )

    def get_watch_detail_revision_token(self, watch_item_id: str) -> str:
        """委派詳細頁 fragment revision 查詢到 fragment repository。"""
        return self._fragment.get_watch_detail_revision_token(watch_item_id)

    def save_notification_state(self, state: NotificationState) -> None:
        """委派通知去重狀態寫入到 write repository。"""
        self._write.save_notification_state(state)

    def get_notification_state(self, watch_item_id: str) -> NotificationState | None:
        """委派通知去重狀態讀取到 history repository。"""
        return self._history.get_notification_state(watch_item_id)

    def save_notification_throttle_state(
        self,
        state: NotificationThrottleState,
    ) -> None:
        """委派通道節流狀態寫入到 throttle repository。"""
        self._throttle.save_notification_throttle_state(state)

    def get_notification_throttle_state(
        self,
        *,
        channel_name: str,
        dedupe_key: str,
    ) -> NotificationThrottleState | None:
        """委派通道節流狀態讀取到 throttle repository。"""
        return self._throttle.get_notification_throttle_state(
            channel_name=channel_name,
            dedupe_key=dedupe_key,
        )

    def append_debug_artifact(self, artifact: DebugArtifact, *, retention_limit: int) -> None:
        """委派 debug artifact 追加到 write repository。"""
        self._write.append_debug_artifact(
            artifact,
            retention_limit=retention_limit,
        )

    def append_runtime_state_event(self, event: RuntimeStateEvent) -> None:
        """委派 runtime 狀態事件追加到 write repository。"""
        self._write.append_runtime_state_event(event)

    def list_runtime_state_events(self, watch_item_id: str) -> list[RuntimeStateEvent]:
        """委派 runtime 狀態事件查詢到 history repository。"""
        return self._history.list_runtime_state_events(watch_item_id)

    def list_debug_artifacts(self, watch_item_id: str) -> list[DebugArtifact]:
        """委派 debug artifacts 查詢到 history repository。"""
        return self._history.list_debug_artifacts(watch_item_id)
