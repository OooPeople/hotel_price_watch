from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.monitor.assignment_coordinator import WatchAssignmentCoordinator
from app.monitor.scheduler import MonitorScheduler


def test_assignment_coordinator_reuses_inflight_task_for_same_watch() -> None:
    """同一 watch 的手動檢查重疊時，coordinator 應只建立一個實際 task。"""
    scheduler = MonitorScheduler(jitter_ratio=0)
    snapshot_reader = _FakeLatestSnapshotReader()
    runner = _BlockingCheckRunner()
    coordinator = WatchAssignmentCoordinator(
        scheduler=scheduler,
        check_runner=runner,
        latest_snapshot_reader=snapshot_reader,
        now=lambda: datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )

    async def _scenario() -> None:
        """並行觸發兩次 check-now，確認底層 runner 只被呼叫一次。"""
        first = asyncio.create_task(coordinator.request_check_now("watch-1"))
        await runner.started.wait()
        second = asyncio.create_task(coordinator.request_check_now("watch-1"))
        await asyncio.sleep(0)
        assert runner.calls == ["watch-1"]
        runner.release.set()
        await asyncio.gather(first, second)

    asyncio.run(_scenario())

    assert runner.calls == ["watch-1"]
    assert coordinator.inflight_tasks == {}


def test_assignment_coordinator_marks_finished_with_backoff() -> None:
    """assignment 完成後應讀 latest snapshot，並用 backoff 時間更新 scheduler。"""
    now = datetime(2026, 4, 13, 10, 0, tzinfo=UTC)
    backoff_until = datetime(2026, 4, 13, 10, 8, tzinfo=UTC)
    scheduler = MonitorScheduler(jitter_ratio=0)
    scheduler.register_watch(
        watch_item_id="watch-1",
        interval_seconds=600,
        now=now,
        next_run_at=now,
    )
    scheduler.dequeue_due_work(now=now, max_workers=1)
    snapshot_reader = _FakeLatestSnapshotReader(backoff_until=backoff_until)
    runner = _RecordingCheckRunner()
    coordinator = WatchAssignmentCoordinator(
        scheduler=scheduler,
        check_runner=runner,
        latest_snapshot_reader=snapshot_reader,
        now=lambda: now,
    )

    asyncio.run(coordinator.run_assignment("watch-1"))

    assert runner.calls == ["watch-1"]
    assert scheduler.get_schedule("watch-1").next_run_at == backoff_until
    assert scheduler.get_worker_state("watch-1") is None


class _RecordingCheckRunner:
    """記錄 coordinator 呼叫的 watch id。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, watch_item_id: str) -> None:
        """記錄一次 watch check 呼叫。"""
        self.calls.append(watch_item_id)


class _BlockingCheckRunner:
    """可由測試控制釋放時機的 watch check runner。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, watch_item_id: str) -> None:
        """記錄呼叫後等待測試釋放。"""
        self.calls.append(watch_item_id)
        self.started.set()
        await self.release.wait()


class _FakeLatestSnapshotReader:
    """提供 assignment coordinator 測試用的 latest snapshot reader。"""

    def __init__(self, backoff_until: datetime | None = None) -> None:
        self.backoff_until = backoff_until

    def get_latest_check_snapshot(self, watch_item_id: str):
        """回傳帶有 backoff_until 的簡化 snapshot。"""
        del watch_item_id
        return SimpleNamespace(backoff_until=self.backoff_until)
