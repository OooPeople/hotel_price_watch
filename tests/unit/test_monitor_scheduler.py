from datetime import datetime, timedelta

import pytest

from app.monitor.scheduler import MonitorScheduler


def test_register_watch_can_run_immediately() -> None:
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


def test_reschedule_now_moves_next_run_to_current_time() -> None:
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
