"""in-memory scheduler 與 worker 指派邏輯。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from random import Random

from app.monitor.models import ScheduledWatch, WorkerAssignment, WorkerState


class MonitorScheduler:
    """管理 watch item 的下一次執行時間與 worker 指派。"""

    def __init__(
        self,
        *,
        jitter_ratio: float = 0.1,
        random_seed: int = 0,
    ) -> None:
        """建立 scheduler，並固定 jitter 來源以利測試。"""
        if jitter_ratio < 0:
            raise ValueError("jitter_ratio must be non-negative")
        self._jitter_ratio = jitter_ratio
        self._random = Random(random_seed)
        self._scheduled: dict[str, ScheduledWatch] = {}
        self._workers: dict[str, WorkerState] = {}
        self._removed_while_running: set[str] = set()

    def register_watch(
        self,
        *,
        watch_item_id: str,
        interval_seconds: int,
        now: datetime,
        run_immediately: bool = True,
        next_run_at: datetime | None = None,
    ) -> None:
        """把 watch item 加入 scheduler，並建立初始執行時間。"""
        resolved_next_run_at = next_run_at
        if resolved_next_run_at is None:
            resolved_next_run_at = (
                now if run_immediately else self._next_due_time(now, interval_seconds)
            )
        self._scheduled[watch_item_id] = ScheduledWatch(
            watch_item_id=watch_item_id,
            interval_seconds=interval_seconds,
            next_run_at=resolved_next_run_at,
        )

    def remove_watch(self, watch_item_id: str) -> None:
        """從 scheduler 與 worker 狀態中移除指定監看項。"""
        self._scheduled.pop(watch_item_id, None)
        if watch_item_id in self._workers:
            self._removed_while_running.add(watch_item_id)
        else:
            self._workers.pop(watch_item_id, None)

    def dequeue_due_work(
        self,
        *,
        now: datetime,
        max_workers: int,
    ) -> tuple[WorkerAssignment, ...]:
        """取出目前到期且可分派給 worker 的工作。"""
        if max_workers <= 0:
            return ()

        available_slots = max_workers - len(self._workers)
        if available_slots <= 0:
            return ()

        due_items = sorted(
            (
                scheduled
                for watch_item_id, scheduled in self._scheduled.items()
                if scheduled.next_run_at <= now and watch_item_id not in self._workers
            ),
            key=lambda item: item.next_run_at,
        )

        assignments: list[WorkerAssignment] = []
        for scheduled in due_items[:available_slots]:
            assignment = WorkerAssignment(
                watch_item_id=scheduled.watch_item_id,
                scheduled_at=scheduled.next_run_at,
                started_at=now,
            )
            self._workers[scheduled.watch_item_id] = WorkerState(
                watch_item_id=scheduled.watch_item_id,
                started_at=now,
                scheduled_at=scheduled.next_run_at,
            )
            assignments.append(assignment)
        return tuple(assignments)

    def mark_finished(
        self,
        *,
        watch_item_id: str,
        finished_at: datetime,
        backoff_until: datetime | None = None,
    ) -> ScheduledWatch:
        """在工作完成後更新下一次執行時間，並釋放 worker 佔用。"""
        self._workers.pop(watch_item_id, None)
        if watch_item_id in self._removed_while_running:
            self._removed_while_running.remove(watch_item_id)
            raise LookupError(f"watch item was removed while worker was running: {watch_item_id}")

        scheduled = self._scheduled[watch_item_id]

        next_run_at = backoff_until or self._next_due_time(
            finished_at,
            scheduled.interval_seconds,
        )
        updated = replace(scheduled, next_run_at=next_run_at)
        self._scheduled[watch_item_id] = updated
        return updated

    def mark_check_completed(
        self,
        *,
        watch_item_id: str,
        completed_at: datetime,
        backoff_until: datetime | None = None,
    ) -> ScheduledWatch:
        """在非 worker 流程完成檢查後，依相同規則更新下一次執行時間。"""
        scheduled = self._scheduled[watch_item_id]
        next_run_at = backoff_until or self._next_due_time(
            completed_at,
            scheduled.interval_seconds,
        )
        updated = replace(scheduled, next_run_at=next_run_at)
        self._scheduled[watch_item_id] = updated
        return updated

    def reschedule_now(
        self,
        *,
        watch_item_id: str,
        now: datetime,
    ) -> ScheduledWatch:
        """把指定 watch item 的下一次執行時間提前到現在。"""
        scheduled = self._scheduled[watch_item_id]
        updated = replace(scheduled, next_run_at=now)
        self._scheduled[watch_item_id] = updated
        return updated

    def get_schedule(self, watch_item_id: str) -> ScheduledWatch:
        """讀取指定監看項目前的排程狀態。"""
        return self._scheduled[watch_item_id]

    def get_worker_state(self, watch_item_id: str) -> WorkerState | None:
        """讀取指定監看項目前的 worker 狀態。"""
        return self._workers.get(watch_item_id)

    def list_registered_ids(self) -> tuple[str, ...]:
        """列出目前 scheduler 已註冊的所有 watch item id。"""
        return tuple(self._scheduled.keys())

    def clear(self) -> None:
        """清空所有排程與 worker 狀態。"""
        self._scheduled.clear()
        self._workers.clear()
        self._removed_while_running.clear()

    def update_interval(
        self,
        *,
        watch_item_id: str,
        interval_seconds: int,
    ) -> ScheduledWatch:
        """更新既有監看項的 interval，同時保留目前 next_run_at。"""
        scheduled = self._scheduled[watch_item_id]
        updated = replace(scheduled, interval_seconds=interval_seconds)
        self._scheduled[watch_item_id] = updated
        return updated

    def _next_due_time(
        self,
        base_time: datetime,
        interval_seconds: int,
    ) -> datetime:
        """依固定 interval 與 jitter 計算下一次執行時間。"""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        jitter_bound = interval_seconds * self._jitter_ratio
        jitter_seconds = self._random.uniform(-jitter_bound, jitter_bound)
        delay = max(interval_seconds + jitter_seconds, 0)
        return base_time + timedelta(seconds=delay)
