"""background runtime 的 watch definition 與 scheduler 同步協調器。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta

from app.domain.entities import WatchItem
from app.monitor.policies import should_trigger_wakeup_rescan
from app.monitor.scheduler import MonitorScheduler


class WatchDefinitionSyncCoordinator:
    """把 DB 內 watch 定義同步到 scheduler，避免 runtime 直接持有同步細節。"""

    def __init__(
        self,
        *,
        watch_item_reader,
        latest_snapshot_reader,
        scheduler: MonitorScheduler,
        now: Callable[[], datetime],
    ) -> None:
        """保存同步 watch definition 需要的 repository 與 scheduler 依賴。"""
        self._watch_item_reader = watch_item_reader
        self._latest_snapshot_reader = latest_snapshot_reader
        self._scheduler = scheduler
        self._now = now

    async def sync_watch_definitions(
        self,
        *,
        resumed_after_sleep: bool = False,
        now: datetime | None = None,
    ) -> tuple[dict[str, WatchItem], datetime]:
        """同步 enabled watches 到 scheduler，並回傳 active watches 與同步時間。"""
        now = now or self._now()
        watch_items = await asyncio.to_thread(self._watch_item_reader.list_all)
        active_watch_items = {
            watch_item.id: watch_item
            for watch_item in watch_items
            if watch_item.enabled and watch_item.paused_reason is None
        }
        registered_ids = set(self._scheduler.list_registered_ids())

        for watch_item_id in tuple(registered_ids - set(active_watch_items.keys())):
            self._scheduler.remove_watch(watch_item_id)

        for watch_item in active_watch_items.values():
            latest_snapshot = await asyncio.to_thread(
                self._latest_snapshot_reader.get_latest_check_snapshot,
                watch_item.id,
            )
            if resumed_after_sleep and should_trigger_wakeup_rescan(
                resumed_at=now,
                last_checked_at=(
                    latest_snapshot.checked_at if latest_snapshot is not None else None
                ),
                backoff_until=(
                    latest_snapshot.backoff_until if latest_snapshot is not None else None
                ),
            ):
                self._scheduler.reschedule_now(
                    watch_item_id=watch_item.id,
                    now=now,
                )
            desired_next_run_at = compute_next_run_at(
                latest_snapshot=latest_snapshot,
                interval_seconds=watch_item.scheduler_interval_seconds,
                now=now,
            )
            if watch_item.id not in registered_ids:
                self._scheduler.register_watch(
                    watch_item_id=watch_item.id,
                    interval_seconds=watch_item.scheduler_interval_seconds,
                    now=now,
                    next_run_at=desired_next_run_at,
                )
                continue
            self._scheduler.update_interval(
                watch_item_id=watch_item.id,
                interval_seconds=watch_item.scheduler_interval_seconds,
            )
        return active_watch_items, now


def compute_next_run_at(
    *,
    latest_snapshot,
    interval_seconds: int,
    now: datetime,
) -> datetime:
    """依最新檢查摘要決定 runtime 啟動後的下一次執行時間。"""
    if latest_snapshot is None:
        return now
    if latest_snapshot.backoff_until is not None and latest_snapshot.backoff_until > now:
        return latest_snapshot.backoff_until
    due_at = latest_snapshot.checked_at + timedelta(seconds=interval_seconds)
    return due_at if due_at > now else now
