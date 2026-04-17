"""watch lifecycle 的正式狀態機與 transition 決策。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.domain.entities import (
    LatestCheckSnapshot,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import CheckErrorCode, RuntimeStateEventKind
from app.domain.watch_runtime_state import derive_watch_runtime_state


class WatchLifecycleCommand(StrEnum):
    """表示 lifecycle state machine 支援的控制命令。"""

    MANUAL_ENABLE = "manual_enable"
    MANUAL_DISABLE = "manual_disable"
    MANUAL_PAUSE = "manual_pause"
    MANUAL_RESUME = "manual_resume"
    CHECK_NOW = "check_now"
    RUNTIME_PAUSE_BLOCKED = "runtime_pause_blocked"


class LifecycleSchedulerAction(StrEnum):
    """表示 lifecycle transition 對 scheduler active set 的建議。"""

    NONE = "none"
    REMOVE = "remove"


class InFlightTaskPolicy(StrEnum):
    """表示 control command 對已執行中 task 的正式處理語意。"""

    NONE = "none"
    CONTINUE_AND_GATE = "continue_and_gate"


@dataclass(frozen=True, slots=True)
class WatchLifecycleContext:
    """保存 state machine 判斷單次 transition 所需的狀態快照。"""

    watch_item: WatchItem
    latest_snapshot: LatestCheckSnapshot | None = None
    next_snapshot: LatestCheckSnapshot | None = None


@dataclass(frozen=True, slots=True)
class WatchLifecycleDecision:
    """描述 state machine 對單次 command 做出的完整決策。"""

    command: WatchLifecycleCommand
    allowed: bool
    watch_item: WatchItem | None = None
    runtime_state_event: RuntimeStateEvent | None = None
    scheduler_action: LifecycleSchedulerAction = LifecycleSchedulerAction.NONE
    in_flight_policy: InFlightTaskPolicy = InFlightTaskPolicy.NONE
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WatchLifecycleTransitionResult:
    """描述已套用 lifecycle transition 後的輸出結果。"""

    watch_item: WatchItem
    event: RuntimeStateEvent


def decide_watch_lifecycle(
    *,
    context: WatchLifecycleContext,
    command: WatchLifecycleCommand,
    occurred_at: datetime,
    detail_text: str | None = None,
) -> WatchLifecycleDecision:
    """依目前 watch 狀態與 command 產生唯一 lifecycle transition 決策。"""
    if command is WatchLifecycleCommand.CHECK_NOW:
        return _decide_check_now(context=context)

    if command is WatchLifecycleCommand.MANUAL_ENABLE:
        return _build_transition_decision(
            context=context,
            command=command,
            occurred_at=occurred_at,
            next_watch_item=replace(
                context.watch_item,
                enabled=True,
                paused_reason=None,
            ),
            event_kind=RuntimeStateEventKind.MANUAL_ENABLE,
            in_flight_policy=InFlightTaskPolicy.CONTINUE_AND_GATE,
        )

    if command is WatchLifecycleCommand.MANUAL_DISABLE:
        return _build_transition_decision(
            context=context,
            command=command,
            occurred_at=occurred_at,
            next_watch_item=replace(
                context.watch_item,
                enabled=False,
                paused_reason="manually_disabled",
            ),
            event_kind=RuntimeStateEventKind.MANUAL_DISABLE,
            scheduler_action=LifecycleSchedulerAction.REMOVE,
            in_flight_policy=InFlightTaskPolicy.CONTINUE_AND_GATE,
        )

    if command is WatchLifecycleCommand.MANUAL_PAUSE:
        return _build_transition_decision(
            context=context,
            command=command,
            occurred_at=occurred_at,
            next_watch_item=replace(
                context.watch_item,
                enabled=True,
                paused_reason="manually_paused",
            ),
            event_kind=RuntimeStateEventKind.MANUAL_PAUSE,
            scheduler_action=LifecycleSchedulerAction.REMOVE,
            in_flight_policy=InFlightTaskPolicy.CONTINUE_AND_GATE,
        )

    if command is WatchLifecycleCommand.MANUAL_RESUME:
        return _build_transition_decision(
            context=context,
            command=command,
            occurred_at=occurred_at,
            next_watch_item=replace(
                context.watch_item,
                enabled=True,
                paused_reason=None,
            ),
            event_kind=RuntimeStateEventKind.MANUAL_RESUME,
            in_flight_policy=InFlightTaskPolicy.CONTINUE_AND_GATE,
        )

    if command is WatchLifecycleCommand.RUNTIME_PAUSE_BLOCKED:
        return _build_transition_decision(
            context=context,
            command=command,
            occurred_at=occurred_at,
            next_watch_item=replace(
                context.watch_item,
                enabled=True,
                paused_reason=CheckErrorCode.FORBIDDEN_403.value,
            ),
            event_kind=RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING,
            scheduler_action=LifecycleSchedulerAction.REMOVE,
            in_flight_policy=InFlightTaskPolicy.CONTINUE_AND_GATE,
            detail_text=detail_text,
        )

    raise ValueError(f"unsupported lifecycle command: {command}")


def build_runtime_lifecycle_events(
    *,
    context: WatchLifecycleContext,
    control_decision: WatchLifecycleDecision | None,
    error_code: CheckErrorCode | None,
    occurred_at: datetime,
) -> tuple[RuntimeStateEvent, ...]:
    """依 state machine 決策與 runtime snapshot 差異建立正式 lifecycle events。"""
    events: list[RuntimeStateEvent] = []
    if control_decision is not None and control_decision.runtime_state_event is not None:
        events.append(control_decision.runtime_state_event)

    next_watch_item = (
        control_decision.watch_item
        if control_decision is not None and control_decision.watch_item is not None
        else context.watch_item
    )
    previous_state = derive_watch_runtime_state(
        watch_item=context.watch_item,
        latest_snapshot=context.latest_snapshot,
        now=occurred_at,
    )
    current_state = derive_watch_runtime_state(
        watch_item=next_watch_item,
        latest_snapshot=context.next_snapshot,
        now=occurred_at,
    )

    previous_backoff = (
        context.latest_snapshot.backoff_until
        if context.latest_snapshot is not None
        else None
    )
    next_backoff = (
        context.next_snapshot.backoff_until
        if context.next_snapshot is not None
        else None
    )
    if previous_backoff is None and next_backoff is not None:
        events.append(
            RuntimeStateEvent(
                watch_item_id=context.watch_item.id,
                occurred_at=occurred_at,
                event_kind=RuntimeStateEventKind.ENTERED_BACKOFF,
                from_state=previous_state,
                to_state=current_state,
            )
        )
    elif previous_backoff is not None and next_backoff is None:
        events.append(
            RuntimeStateEvent(
                watch_item_id=context.watch_item.id,
                occurred_at=occurred_at,
                event_kind=RuntimeStateEventKind.CLEARED_BACKOFF,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    previous_degraded = (
        context.latest_snapshot.is_degraded
        if context.latest_snapshot is not None
        else False
    )
    next_degraded = (
        context.next_snapshot.is_degraded
        if context.next_snapshot is not None
        else False
    )
    if not previous_degraded and next_degraded:
        events.append(
            RuntimeStateEvent(
                watch_item_id=context.watch_item.id,
                occurred_at=occurred_at,
                event_kind=RuntimeStateEventKind.ENTERED_DEGRADED,
                from_state=previous_state,
                to_state=current_state,
            )
        )
    elif previous_degraded and not next_degraded:
        events.append(
            RuntimeStateEvent(
                watch_item_id=context.watch_item.id,
                occurred_at=occurred_at,
                event_kind=RuntimeStateEventKind.CLEARED_DEGRADED,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    if (
        context.latest_snapshot is not None
        and context.latest_snapshot.last_error_code == CheckErrorCode.FORBIDDEN_403.value
        and error_code is None
    ):
        events.append(
            RuntimeStateEvent(
                watch_item_id=context.watch_item.id,
                occurred_at=occurred_at,
                event_kind=RuntimeStateEventKind.RECOVERED_AFTER_SUCCESS,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    return tuple(events)


def _decide_check_now(
    *,
    context: WatchLifecycleContext,
) -> WatchLifecycleDecision:
    """判斷目前 watch 是否允許立即檢查。"""
    current_state = derive_watch_runtime_state(
        watch_item=context.watch_item,
        latest_snapshot=context.latest_snapshot,
    )
    if not context.watch_item.enabled or context.watch_item.paused_reason is not None:
        return WatchLifecycleDecision(
            command=WatchLifecycleCommand.CHECK_NOW,
            allowed=False,
            rejection_reason=f"watch is not checkable in state {current_state.value}",
        )
    return WatchLifecycleDecision(
        command=WatchLifecycleCommand.CHECK_NOW,
        allowed=True,
    )


def _build_transition_decision(
    *,
    context: WatchLifecycleContext,
    command: WatchLifecycleCommand,
    occurred_at: datetime,
    next_watch_item: WatchItem,
    event_kind: RuntimeStateEventKind,
    scheduler_action: LifecycleSchedulerAction = LifecycleSchedulerAction.NONE,
    in_flight_policy: InFlightTaskPolicy = InFlightTaskPolicy.NONE,
    detail_text: str | None = None,
) -> WatchLifecycleDecision:
    """建立包含 watch 更新、event 與 side effect 建議的 transition decision。"""
    latest_for_to_state = context.next_snapshot or context.latest_snapshot
    event = RuntimeStateEvent(
        watch_item_id=context.watch_item.id,
        occurred_at=occurred_at,
        event_kind=event_kind,
        from_state=derive_watch_runtime_state(
            watch_item=context.watch_item,
            latest_snapshot=context.latest_snapshot,
        ),
        to_state=derive_watch_runtime_state(
            watch_item=next_watch_item,
            latest_snapshot=latest_for_to_state,
        ),
        detail_text=detail_text,
    )
    return WatchLifecycleDecision(
        command=command,
        allowed=True,
        watch_item=next_watch_item,
        runtime_state_event=event,
        scheduler_action=scheduler_action,
        in_flight_policy=in_flight_policy,
    )
