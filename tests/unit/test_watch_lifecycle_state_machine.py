"""watch lifecycle state machine 的單元測試。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.entities import LatestCheckSnapshot, WatchItem
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationLeafKind,
    RuntimeStateEventKind,
    WatchRuntimeState,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.domain.watch_lifecycle_state_machine import (
    InFlightTaskPolicy,
    LifecycleSchedulerAction,
    WatchLifecycleCommand,
    WatchLifecycleContext,
    build_runtime_lifecycle_events,
    decide_watch_lifecycle,
)


def test_manual_disable_returns_scheduler_and_inflight_policy() -> None:
    """manual disable 應由 state machine 同時決定 control state 與 side effect。"""
    occurred_at = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)

    decision = decide_watch_lifecycle(
        context=WatchLifecycleContext(watch_item=_watch_item()),
        command=WatchLifecycleCommand.MANUAL_DISABLE,
        occurred_at=occurred_at,
    )

    assert decision.allowed is True
    assert decision.watch_item is not None
    assert decision.watch_item.enabled is False
    assert decision.watch_item.paused_reason == "manually_disabled"
    assert decision.scheduler_action is LifecycleSchedulerAction.REMOVE
    assert decision.in_flight_policy is InFlightTaskPolicy.CONTINUE_AND_GATE
    assert decision.runtime_state_event is not None
    assert decision.runtime_state_event.event_kind is RuntimeStateEventKind.MANUAL_DISABLE
    assert decision.runtime_state_event.from_state is WatchRuntimeState.ACTIVE
    assert decision.runtime_state_event.to_state is WatchRuntimeState.MANUALLY_DISABLED


def test_check_now_rejects_paused_watch() -> None:
    """check-now gate 應由 state machine 判定，避免繞過 control state。"""
    decision = decide_watch_lifecycle(
        context=WatchLifecycleContext(
            watch_item=_watch_item(paused_reason="manually_paused"),
        ),
        command=WatchLifecycleCommand.CHECK_NOW,
        occurred_at=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.rejection_reason is not None
    assert "manually_paused" in decision.rejection_reason


def test_runtime_blocked_pause_builds_control_transition() -> None:
    """runtime blocked pause 應產生 watch 更新、event 與 scheduler 移除建議。"""
    occurred_at = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    decision = decide_watch_lifecycle(
        context=WatchLifecycleContext(
            watch_item=_watch_item(),
            next_snapshot=_latest_snapshot(
                checked_at=occurred_at,
                last_error_code=CheckErrorCode.FORBIDDEN_403.value,
            ),
        ),
        command=WatchLifecycleCommand.RUNTIME_PAUSE_BLOCKED,
        occurred_at=occurred_at,
        detail_text="kind=blocked",
    )

    assert decision.watch_item is not None
    assert decision.watch_item.paused_reason == CheckErrorCode.FORBIDDEN_403.value
    assert decision.scheduler_action is LifecycleSchedulerAction.REMOVE
    assert decision.runtime_state_event is not None
    assert decision.runtime_state_event.event_kind is RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING
    assert decision.runtime_state_event.to_state is WatchRuntimeState.PAUSED_BLOCKED
    assert decision.runtime_state_event.detail_text == "kind=blocked"


def test_runtime_lifecycle_events_include_control_transition() -> None:
    """runtime event builder 應納入 state machine 產生的 control event。"""
    occurred_at = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    next_snapshot = _latest_snapshot(
        checked_at=occurred_at,
        last_error_code=CheckErrorCode.FORBIDDEN_403.value,
    )
    decision = decide_watch_lifecycle(
        context=WatchLifecycleContext(
            watch_item=_watch_item(),
            next_snapshot=next_snapshot,
        ),
        command=WatchLifecycleCommand.RUNTIME_PAUSE_BLOCKED,
        occurred_at=occurred_at,
    )

    events = build_runtime_lifecycle_events(
        context=WatchLifecycleContext(
            watch_item=_watch_item(),
            next_snapshot=next_snapshot,
        ),
        control_decision=decision,
        error_code=CheckErrorCode.FORBIDDEN_403,
        occurred_at=occurred_at,
    )

    assert len(events) == 1
    assert events[0].event_kind is RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING


def test_runtime_lifecycle_events_record_recovery_without_control_pause() -> None:
    """403 後成功恢復時，應在沒有 control pause 的情境下記錄 recovered。"""
    occurred_at = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    previous_snapshot = _latest_snapshot(
        checked_at=occurred_at - timedelta(minutes=10),
        last_error_code=CheckErrorCode.FORBIDDEN_403.value,
    )
    next_snapshot = _latest_snapshot(
        checked_at=occurred_at,
        last_error_code=None,
        availability=Availability.AVAILABLE,
    )

    events = build_runtime_lifecycle_events(
        context=WatchLifecycleContext(
            watch_item=_watch_item(),
            latest_snapshot=previous_snapshot,
            next_snapshot=next_snapshot,
        ),
        control_decision=None,
        error_code=None,
        occurred_at=occurred_at,
    )

    assert len(events) == 1
    assert events[0].event_kind is RuntimeStateEventKind.RECOVERED_AFTER_SUCCESS


def _latest_snapshot(
    *,
    checked_at: datetime,
    last_error_code: str | None,
    availability: Availability = Availability.UNKNOWN,
) -> LatestCheckSnapshot:
    """建立 state machine 測試用的最新檢查摘要。"""
    return LatestCheckSnapshot(
        watch_item_id="watch-1",
        checked_at=checked_at,
        availability=availability,
        normalized_price_amount=None,
        currency=None,
        last_error_code=last_error_code,
    )


def _watch_item(*, paused_reason: str | None = None) -> WatchItem:
    """建立 state machine 測試用的 watch item。"""
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
