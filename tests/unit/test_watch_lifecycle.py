"""watch lifecycle coordinator 的單元測試。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.watch_lifecycle import WatchLifecycleCoordinator, WatchLifecycleError
from app.domain.entities import LatestCheckSnapshot, WatchItem
from app.domain.enums import (
    Availability,
    NotificationLeafKind,
    RuntimeStateEventKind,
    WatchRuntimeState,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.infrastructure.db import (
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)


class _RecordingRuntime:
    """記錄 check-now 與 scheduler 移除呼叫的 runtime 測試替身。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.removed_ids: list[str] = []

    async def request_check_now(self, watch_item_id: str) -> None:
        """記錄被要求立即檢查的 watch id。"""
        self.calls.append(watch_item_id)

    def remove_watch_from_schedule(self, watch_item_id: str) -> None:
        """記錄 lifecycle transition 要求移除的 scheduler id。"""
        self.removed_ids.append(watch_item_id)


def test_lifecycle_coordinator_owns_manual_disable_transition(tmp_path) -> None:
    """disable 應由 lifecycle coordinator 更新 watch 並寫入 transition event。"""
    watch_repository, runtime_repository = _build_repositories(tmp_path)
    watch_repository.save(_build_watch_item())
    coordinator = WatchLifecycleCoordinator(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        monitor_runtime=None,
    )

    updated_watch = coordinator.disable_watch("watch-1")

    assert updated_watch.enabled is False
    assert updated_watch.paused_reason == "manually_disabled"
    events = runtime_repository.list_runtime_state_events("watch-1")
    assert len(events) == 1
    assert events[0].event_kind is RuntimeStateEventKind.MANUAL_DISABLE
    assert events[0].from_state is WatchRuntimeState.ACTIVE
    assert events[0].to_state is WatchRuntimeState.MANUALLY_DISABLED


def test_lifecycle_coordinator_preserves_recover_pending_on_resume(tmp_path) -> None:
    """從 blocked pause 恢復時，to_state 應保留 recover pending 語意。"""
    watch_repository, runtime_repository = _build_repositories(tmp_path)
    watch_repository.save(
        _build_watch_item(paused_reason="http_403")
    )
    runtime_repository.save_latest_check_snapshot(
        LatestCheckSnapshot(
            watch_item_id="watch-1",
            checked_at=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
            availability=Availability.UNKNOWN,
            normalized_price_amount=None,
            currency=None,
            last_error_code="http_403",
            consecutive_failures=1,
        )
    )
    coordinator = WatchLifecycleCoordinator(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        monitor_runtime=None,
    )

    updated_watch = coordinator.resume_watch("watch-1")

    assert updated_watch.enabled is True
    assert updated_watch.paused_reason is None
    events = runtime_repository.list_runtime_state_events("watch-1")
    assert events[0].event_kind is RuntimeStateEventKind.MANUAL_RESUME
    assert events[0].from_state is WatchRuntimeState.PAUSED_BLOCKED
    assert events[0].to_state is WatchRuntimeState.RECOVER_PENDING


def test_lifecycle_coordinator_gates_check_now_by_control_state(tmp_path) -> None:
    """check-now 應拒絕已暫停 watch，避免繞過 control state。"""
    watch_repository, runtime_repository = _build_repositories(tmp_path)
    watch_repository.save(_build_watch_item(paused_reason="manually_paused"))
    runtime = _RecordingRuntime()
    coordinator = WatchLifecycleCoordinator(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        monitor_runtime=runtime,
    )

    with pytest.raises(WatchLifecycleError, match="not checkable"):
        import asyncio

        asyncio.run(coordinator.request_check_now("watch-1"))

    assert runtime.calls == []


def test_lifecycle_coordinator_applies_scheduler_side_effect(tmp_path) -> None:
    """pause transition 應由 coordinator 套用 state machine 的 scheduler side effect。"""
    watch_repository, runtime_repository = _build_repositories(tmp_path)
    watch_repository.save(_build_watch_item())
    runtime = _RecordingRuntime()
    coordinator = WatchLifecycleCoordinator(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        monitor_runtime=runtime,
    )

    coordinator.pause_watch("watch-1")

    assert runtime.removed_ids == ["watch-1"]


def _build_repositories(tmp_path):
    """建立 watch / runtime repository 測試組合。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    return SqliteWatchItemRepository(database), SqliteRuntimeRepository(database)


def _build_watch_item(*, paused_reason: str | None = None) -> WatchItem:
    """建立 lifecycle 測試使用的最小 watch item。"""
    return WatchItem(
        id="watch-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="Room",
        plan_name="Plan",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("20000"),
        ),
        scheduler_interval_seconds=600,
        enabled=True,
        paused_reason=paused_reason,
    )
