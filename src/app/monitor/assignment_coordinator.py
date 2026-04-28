"""background runtime 的排程 assignment 與 in-flight task 協調。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from typing import Protocol

from app.monitor.runtime_logging import compact_log_value
from app.monitor.scheduler import MonitorScheduler


class AssignmentSnapshotReader(Protocol):
    """描述 assignment 完成後讀取最新 snapshot 的最小介面。"""

    def get_latest_check_snapshot(self, watch_item_id: str):
        """讀取指定 watch 的最新檢查摘要。"""
        ...


WatchCheckRunner = Callable[[str], Awaitable[None]]


class WatchAssignmentCoordinator:
    """協調 scheduler due work、同一 watch 互斥與 check-now 共用任務。"""

    def __init__(
        self,
        *,
        scheduler: MonitorScheduler,
        check_runner: WatchCheckRunner,
        latest_snapshot_reader: AssignmentSnapshotReader,
        now: Callable[[], datetime],
    ) -> None:
        """建立 assignment coordinator 所需的 scheduler 與查詢依賴。"""
        self._scheduler = scheduler
        self._check_runner = check_runner
        self._latest_snapshot_reader = latest_snapshot_reader
        self._now = now
        self.inflight_tasks: dict[str, asyncio.Task[None]] = {}
        self.assignment_tasks: set[asyncio.Task[None]] = set()

    async def request_check_now(self, watch_item_id: str) -> None:
        """提供立即檢查入口，並與背景排程共用同一個 in-flight task。"""
        task = self._get_or_create_watch_check_task(watch_item_id)
        await asyncio.shield(task)

    async def run_assignment(self, watch_item_id: str) -> None:
        """執行單次排程工作，並在完成後更新 scheduler 的下一次執行時間。"""
        task = self._get_or_create_watch_check_task(watch_item_id)
        try:
            await asyncio.shield(task)
        finally:
            latest_snapshot = self._latest_snapshot_reader.get_latest_check_snapshot(
                watch_item_id
            )
            backoff_until = latest_snapshot.backoff_until if latest_snapshot is not None else None
            with suppress(LookupError):
                self._scheduler.mark_finished(
                    watch_item_id=watch_item_id,
                    finished_at=self._now(),
                    backoff_until=backoff_until,
                )

    def dispatch_due_assignments(
        self,
        *,
        now: datetime,
        max_workers: int,
    ) -> None:
        """從 scheduler 取出到期工作並建立背景 assignment task。"""
        assignments = self._scheduler.dequeue_due_work(
            now=now,
            max_workers=max_workers,
        )
        for assignment in assignments:
            task = asyncio.create_task(
                self.run_assignment(assignment.watch_item_id),
                name=f"watch-assignment:{assignment.watch_item_id}",
            )
            self.assignment_tasks.add(task)
            task.add_done_callback(
                _build_forget_assignment_task_callback(
                    assignment_tasks=self.assignment_tasks,
                    assignment_task=task,
                    watch_item_id=assignment.watch_item_id,
                )
            )

    async def cancel_assignment_tasks(self) -> None:
        """取消所有已建立但尚未完成的 assignment task。"""
        assignment_tasks = tuple(self.assignment_tasks)
        for task in assignment_tasks:
            task.cancel()
        for task in assignment_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.assignment_tasks.clear()

    async def cancel_inflight_tasks(self) -> None:
        """取消所有目前執行中的 watch check task。"""
        inflight_tasks = tuple(self.inflight_tasks.values())
        for task in inflight_tasks:
            task.cancel()
        for task in inflight_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.inflight_tasks.clear()

    def _get_or_create_watch_check_task(
        self,
        watch_item_id: str,
    ) -> asyncio.Task[None]:
        """回傳同一個 watch 共用的檢查 task，避免背景與手動檢查並行。"""
        existing_task = self.inflight_tasks.get(watch_item_id)
        if existing_task is not None and not existing_task.done():
            return existing_task

        task = asyncio.create_task(
            self._check_runner(watch_item_id),
            name=f"watch-check:{watch_item_id}",
        )
        self.inflight_tasks[watch_item_id] = task

        def _forget_inflight_task(completed: asyncio.Task[None]) -> None:
            """在單次 watch 檢查結束後清理 in-flight 追蹤。"""
            del completed
            self.inflight_tasks.pop(watch_item_id, None)

        task.add_done_callback(_forget_inflight_task)
        return task


def _build_forget_assignment_task_callback(
    *,
    assignment_tasks: set[asyncio.Task[None]],
    assignment_task: asyncio.Task[None],
    watch_item_id: str,
) -> Callable[[asyncio.Task[None]], None]:
    """建立 assignment task 完成後的清理 callback。"""

    def _forget_assignment_task(completed: asyncio.Task[None]) -> None:
        """在 assignment task 結束後清理背景 worker 追蹤並輸出錯誤。"""
        if not completed.cancelled():
            exc = completed.exception()
            if exc is not None:
                print(
                    "背景監視工作失敗："
                    f"watch_id={watch_item_id}；"
                    f"error={compact_log_value(f'{exc.__class__.__name__}: {exc}')}"
                )
        assignment_tasks.discard(assignment_task)

    return _forget_assignment_task
