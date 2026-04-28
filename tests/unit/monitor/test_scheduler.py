from datetime import datetime, timedelta

import pytest

from app.monitor.scheduler import MonitorScheduler


def test_register_watch_can_run_immediately() -> None:
    """驗證註冊 watch 時可設定為立即進入 due work。"""
    scheduler = MonitorScheduler(random_seed=1)
    now = datetime(2026, 4, 12, 10, 0, 0)

    scheduler.register_watch(
        watch_item_id="watch-1",
        interval_seconds=600,
        now=now,
    )

    scheduled = scheduler.get_schedule("watch-1")
    assert scheduled.next_run_at == now


def test_dequeue_due_work_respects_worker_limit() -> None:
    """驗證取出 due work 時會遵守 worker 數量上限。"""
    scheduler = MonitorScheduler(random_seed=1)
    now = datetime(2026, 4, 12, 10, 0, 0)

    scheduler.register_watch(watch_item_id="watch-1", interval_seconds=600, now=now)
    scheduler.register_watch(watch_item_id="watch-2", interval_seconds=600, now=now)

    assignments = scheduler.dequeue_due_work(now=now, max_workers=1)

    assert len(assignments) == 1
    assert assignments[0].watch_item_id == "watch-1"
    assert scheduler.get_worker_state("watch-1") is not None
    assert scheduler.get_worker_state("watch-2") is None


def test_mark_finished_reschedules_with_backoff_override() -> None:
    """驗證任務完成時若帶 backoff，下一次執行時間會改用 backoff。"""
    scheduler = MonitorScheduler(random_seed=1)
    now = datetime(2026, 4, 12, 10, 0, 0)
    backoff_until = now + timedelta(minutes=30)

    scheduler.register_watch(watch_item_id="watch-1", interval_seconds=600, now=now)
    scheduler.dequeue_due_work(now=now, max_workers=1)

    updated = scheduler.mark_finished(
        watch_item_id="watch-1",
        finished_at=now,
        backoff_until=backoff_until,
    )

    assert updated.next_run_at == backoff_until
    assert scheduler.get_worker_state("watch-1") is None


def test_mark_check_completed_reschedules_without_worker_assignment() -> None:
    """驗證啟動恢復等非 worker 檢查完成後，也能推進下一次執行時間。"""
    scheduler = MonitorScheduler(random_seed=1)
    now = datetime(2026, 4, 12, 10, 0, 0)

    scheduler.register_watch(watch_item_id="watch-1", interval_seconds=600, now=now)

    updated = scheduler.mark_check_completed(
        watch_item_id="watch-1",
        completed_at=now,
    )

    assert updated.next_run_at > now
    assert scheduler.get_worker_state("watch-1") is None


def test_reschedule_now_moves_next_run_to_current_time() -> None:
    """驗證手動喚醒會把下一次執行時間移到目前時間。"""
    scheduler = MonitorScheduler(random_seed=1)
    initial_now = datetime(2026, 4, 12, 10, 0, 0)
    resumed_at = datetime(2026, 4, 12, 11, 0, 0)

    scheduler.register_watch(
        watch_item_id="watch-1",
        interval_seconds=600,
        now=initial_now,
        run_immediately=False,
    )
    updated = scheduler.reschedule_now(
        watch_item_id="watch-1",
        now=resumed_at,
    )

    assert updated.next_run_at == resumed_at


def test_mark_finished_after_remove_watch_returns_lookup_error() -> None:
    """驗證 watch 已移除後再標記完成會回 LookupError。"""
    scheduler = MonitorScheduler(random_seed=1)
    now = datetime(2026, 4, 12, 10, 0, 0)

    scheduler.register_watch(watch_item_id="watch-1", interval_seconds=600, now=now)
    scheduler.dequeue_due_work(now=now, max_workers=1)
    scheduler.remove_watch("watch-1")

    with pytest.raises(LookupError):
        scheduler.mark_finished(
            watch_item_id="watch-1",
            finished_at=now,
        )
