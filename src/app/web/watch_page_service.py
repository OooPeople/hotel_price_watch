"""watch list / detail 頁面的 context 與版本組裝服務。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.bootstrap.container import AppContainer
from app.config.models import DisplaySettings
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    PriceHistoryEntry,
    RuntimeStateEvent,
    WatchItem,
)
from app.monitor.runtime import MonitorRuntimeStatus


@dataclass(frozen=True)
class WatchListPageContext:
    """首頁 watch 列表 renderer 所需的資料集合。"""

    watch_items: tuple[WatchItem, ...]
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None]
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]]
    today_notification_count: int
    runtime_status: MonitorRuntimeStatus | None
    display_settings: DisplaySettings


@dataclass(frozen=True)
class WatchDetailPageContext:
    """watch 詳細頁與 fragment renderer 共用的資料集合。"""

    watch_item: WatchItem
    latest_snapshot: LatestCheckSnapshot | None
    check_events: tuple[CheckEvent, ...]
    notification_state: NotificationState | None
    debug_artifacts: tuple[DebugArtifact, ...]
    runtime_state_events: tuple[RuntimeStateEvent, ...]
    display_settings: DisplaySettings


class WatchPageService:
    """集中首頁與詳細頁 route 需要的 page context 與 revision token。"""

    def __init__(self, container: AppContainer) -> None:
        """保存 route 層提供的依賴容器。"""
        self._container = container

    def build_watch_list_context(self) -> WatchListPageContext:
        """集中讀取首頁與首頁 fragment 需要的 watch 列表 context。"""
        watch_items = tuple(self._container.watch_item_repository.list_all())
        now = datetime.now(UTC)
        return WatchListPageContext(
            watch_items=watch_items,
            latest_snapshots_by_watch_id=self._latest_snapshots_by_watch_id(
                watch_items=watch_items,
            ),
            recent_price_history_by_watch_id=(
                self._container.runtime_history_repository.list_price_history_since(
                    watch_item_ids=tuple(watch_item.id for watch_item in watch_items),
                    since=now - timedelta(hours=24),
                )
            ),
            today_notification_count=(
                self._container.runtime_history_repository.count_notifications_since(
                    _local_day_start_as_utc()
                )
            ),
            runtime_status=self._get_runtime_status(),
            display_settings=self._container.app_settings_service.get_display_settings(),
        )

    def build_watch_list_revision(self) -> str:
        """建立首頁可見資料的版本 hash，供前端判斷是否要抓 fragment。"""
        now = datetime.now(UTC)
        runtime_status = self._get_runtime_status()
        return _hash_revision_parts(
            (
                self._container.watch_item_repository.get_collection_revision_token(),
                self._container.runtime_fragment_repository.get_watch_list_revision_token(
                    price_history_since=now - timedelta(hours=24),
                    notification_since=_local_day_start_as_utc(),
                ),
                self._container.app_settings_repository.get_display_settings_revision_token(),
                _runtime_status_revision_token(runtime_status),
            )
        )

    def build_watch_detail_context(
        self,
        watch_item: WatchItem,
    ) -> WatchDetailPageContext:
        """集中讀取 watch 詳細頁與 fragment 需要的 runtime context。"""
        return WatchDetailPageContext(
            watch_item=watch_item,
            latest_snapshot=(
                self._container.runtime_history_repository.get_latest_check_snapshot(
                    watch_item.id
                )
            ),
            check_events=tuple(
                self._container.runtime_history_repository.list_check_events(
                    watch_item.id
                )
            ),
            notification_state=(
                self._container.runtime_history_repository.get_notification_state(
                    watch_item.id
                )
            ),
            debug_artifacts=tuple(
                self._container.runtime_history_repository.list_debug_artifacts(
                    watch_item.id
                )
            ),
            runtime_state_events=tuple(
                self._container.runtime_history_repository.list_runtime_state_events(
                    watch_item.id
                )
            ),
            display_settings=self._container.app_settings_service.get_display_settings(),
        )

    def build_watch_detail_revision(self, watch_item: WatchItem) -> str:
        """建立詳細頁可見資料的版本 hash，供前端判斷是否要抓 fragment。"""
        return _hash_revision_parts(
            (
                self._container.watch_item_repository.get_revision_token(watch_item.id),
                self._container.runtime_fragment_repository.get_watch_detail_revision_token(
                    watch_item.id
                ),
                self._container.app_settings_repository.get_display_settings_revision_token(),
            )
        )

    def _latest_snapshots_by_watch_id(
        self,
        *,
        watch_items: tuple[WatchItem, ...],
    ) -> dict[str, LatestCheckSnapshot | None]:
        """建立首頁與局部更新使用的最新摘要索引。"""
        return {
            watch_item.id: self._container.runtime_history_repository.get_latest_check_snapshot(
                watch_item.id
            )
            for watch_item in watch_items
        }

    def _get_runtime_status(self) -> MonitorRuntimeStatus | None:
        """讀取目前 background monitor runtime 的狀態摘要。"""
        if self._container.monitor_runtime is None:
            return None
        return self._container.monitor_runtime.get_status()


def _runtime_status_revision_token(runtime_status: MonitorRuntimeStatus | None) -> str:
    """把 runtime status 中會影響首頁可見內容的欄位轉成版本 token。"""
    if runtime_status is None:
        return "runtime:none"
    parts = (
        str(runtime_status.is_running),
        str(runtime_status.enabled_watch_count),
        str(runtime_status.registered_watch_count),
        str(runtime_status.inflight_watch_count),
        str(runtime_status.chrome_debuggable),
        runtime_status.last_watch_sync_at.isoformat()
        if runtime_status.last_watch_sync_at is not None
        else "",
    )
    return "|".join(parts)


def _hash_revision_parts(parts: tuple[str, ...]) -> str:
    """把多個資料來源版本合成單一前端可比對版本。"""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def _local_day_start_as_utc() -> datetime:
    """回傳使用者本地日期今天 00:00 對應的 UTC 時間。"""
    local_now = datetime.now().astimezone()
    local_start = datetime.combine(
        local_now.date(),
        time.min,
        tzinfo=local_now.tzinfo,
    )
    return local_start.astimezone(UTC)
