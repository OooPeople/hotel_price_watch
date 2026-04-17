"""monitor 層的純政策邏輯。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.domain.entities import (
    CheckEvent,
    CheckResult,
    ErrorHandlingDecision,
    LatestCheckSnapshot,
    MonitorCheckArtifacts,
    NotificationDecision,
    NotificationDispatchResult,
    NotificationState,
    PriceHistoryEntry,
    WatchItem,
)
from app.domain.enums import CheckErrorCode, NotificationDeliveryStatus
from app.domain.watch_lifecycle_state_machine import (
    LifecycleSchedulerAction,
    WatchLifecycleCommand,
    WatchLifecycleContext,
    WatchLifecycleDecision,
    decide_watch_lifecycle,
)


@dataclass(frozen=True, slots=True)
class RuntimeControlRecommendation:
    """描述 runtime 本次檢查後建議套用的 control state 變更。"""

    lifecycle_decision: WatchLifecycleDecision | None = None
    remove_from_scheduler: bool = False

    @property
    def watch_item(self) -> WatchItem | None:
        """回傳 state machine 建議套用的 watch control state。"""
        if self.lifecycle_decision is None:
            return None
        return self.lifecycle_decision.watch_item


def decide_error_handling(
    *,
    checked_at: datetime,
    error_code: CheckErrorCode | None,
    consecutive_failures: int,
) -> ErrorHandlingDecision:
    """依錯誤類型與連續失敗次數決定退避或暫停策略。"""
    if error_code is None:
        return ErrorHandlingDecision()

    if error_code is CheckErrorCode.FORBIDDEN_403:
        return ErrorHandlingDecision(
            should_pause=True,
            paused_reason=error_code,
        )

    if error_code is CheckErrorCode.RATE_LIMITED_429:
        minutes = min(15 * (2 ** max(consecutive_failures - 1, 0)), 120)
        return ErrorHandlingDecision(
            backoff_until=checked_at + timedelta(minutes=minutes),
        )

    if error_code in {CheckErrorCode.NETWORK_TIMEOUT, CheckErrorCode.NETWORK_ERROR}:
        minutes = min(5 * (2 ** max(consecutive_failures - 1, 0)), 30)
        return ErrorHandlingDecision(
            backoff_until=checked_at + timedelta(minutes=minutes),
        )

    if error_code is CheckErrorCode.PARSE_FAILED:
        minutes = min(5 * (2 ** max(consecutive_failures - 1, 0)), 30)
        return ErrorHandlingDecision(
            backoff_until=checked_at + timedelta(minutes=minutes),
        )

    return ErrorHandlingDecision()


def should_trigger_wakeup_rescan(
    *,
    resumed_at: datetime,
    last_checked_at: datetime | None,
    backoff_until: datetime | None,
) -> bool:
    """判斷系統從睡眠恢復後是否應立即補掃一次。"""
    if backoff_until is not None and resumed_at < backoff_until:
        return False
    if last_checked_at is None:
        return True
    return resumed_at > last_checked_at


def build_runtime_control_recommendation(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    next_snapshot: LatestCheckSnapshot,
    error_handling: ErrorHandlingDecision,
    error_code: CheckErrorCode | None,
    occurred_at: datetime,
    detail_text: str | None = None,
) -> RuntimeControlRecommendation:
    """依錯誤處理決策建立 runtime control state 建議。"""
    if not error_handling.should_pause:
        return RuntimeControlRecommendation()

    if (
        error_handling.paused_reason is not CheckErrorCode.FORBIDDEN_403
        and error_code is not CheckErrorCode.FORBIDDEN_403
    ):
        return RuntimeControlRecommendation()

    decision = decide_watch_lifecycle(
        context=WatchLifecycleContext(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            next_snapshot=next_snapshot,
        ),
        command=WatchLifecycleCommand.RUNTIME_PAUSE_BLOCKED,
        occurred_at=occurred_at,
        detail_text=detail_text,
    )
    return RuntimeControlRecommendation(
        lifecycle_decision=decision,
        remove_from_scheduler=decision.scheduler_action is LifecycleSchedulerAction.REMOVE,
    )


def build_monitor_check_artifacts(
    *,
    watch_item_id: str,
    check_result: CheckResult,
    notification_decision: NotificationDecision,
    error_code: CheckErrorCode | None,
    error_handling: ErrorHandlingDecision,
    dispatch_result: NotificationDispatchResult | None = None,
) -> MonitorCheckArtifacts:
    """把比較結果整理成 monitor/persistence 層要保存的資料。"""
    current_snapshot = check_result.current_snapshot
    next_state = notification_decision.next_state

    latest_check_snapshot = LatestCheckSnapshot(
        watch_item_id=watch_item_id,
        checked_at=check_result.checked_at,
        availability=current_snapshot.availability,
        normalized_price_amount=current_snapshot.normalized_price_amount,
        currency=current_snapshot.currency,
        backoff_until=error_handling.backoff_until,
        is_degraded=next_state.consecutive_parse_failures >= 3,
        consecutive_failures=next_state.consecutive_failures,
        last_error_code=None if error_code is None else error_code.value,
    )
    check_event = CheckEvent(
        watch_item_id=watch_item_id,
        checked_at=check_result.checked_at,
        availability=current_snapshot.availability,
        event_kinds=_determine_check_event_kinds(
            check_result=check_result,
            notification_decision=notification_decision,
        ),
        normalized_price_amount=current_snapshot.normalized_price_amount,
        currency=current_snapshot.currency,
        error_code=None if error_code is None else error_code.value,
        notification_status=_determine_notification_status(
            should_notify=notification_decision.should_notify,
            dispatch_result=dispatch_result,
        ),
        sent_channels=() if dispatch_result is None else dispatch_result.sent_channels,
        throttled_channels=() if dispatch_result is None else dispatch_result.throttled_channels,
        failed_channels=() if dispatch_result is None else dispatch_result.failed_channels,
    )

    price_history_entry = _build_price_history_entry(
        watch_item_id=watch_item_id,
        check_result=check_result,
    )

    return MonitorCheckArtifacts(
        latest_check_snapshot=latest_check_snapshot,
        check_event=check_event,
        price_history_entry=price_history_entry,
    )


def reset_notification_state_after_success(
    state: NotificationState,
) -> NotificationState:
    """在成功檢查後清理 parse failure streak 與 degraded 狀態。"""
    return replace(
        state,
        consecutive_failures=0,
        consecutive_parse_failures=0,
        degraded_notified_at=None,
    )


def _determine_check_event_kinds(
    *,
    check_result: CheckResult,
    notification_decision: NotificationDecision,
) -> tuple[str, ...]:
    """整理歷史頁應保存的事件列表。"""
    if notification_decision.event_kinds:
        return tuple(event.value for event in notification_decision.event_kinds)
    if check_result.parse_failed:
        return ("parse_failed",)
    if check_result.previous_snapshot is None:
        return ("checked",)
    if check_result.became_available:
        return ("became_available",)
    if check_result.price_dropped:
        return ("price_drop",)
    if check_result.price_changed:
        return ("price_changed",)
    if check_result.availability_changed:
        return ("availability_changed",)
    return ("checked",)


def _determine_notification_status(
    *,
    should_notify: bool,
    dispatch_result: NotificationDispatchResult | None,
) -> NotificationDeliveryStatus:
    """依通知需求與實際 dispatch 結果整理歷史頁可用狀態。"""
    if not should_notify:
        return NotificationDeliveryStatus.NOT_REQUESTED
    if dispatch_result is None:
        return NotificationDeliveryStatus.PENDING_DISPATCH

    has_sent = bool(dispatch_result.sent_channels)
    has_throttled = bool(dispatch_result.throttled_channels)
    has_failed = bool(dispatch_result.failed_channels)

    if has_sent and not has_throttled and not has_failed:
        return NotificationDeliveryStatus.SENT
    if has_throttled and not has_sent and not has_failed:
        return NotificationDeliveryStatus.THROTTLED
    if has_failed and not has_sent and not has_throttled:
        return NotificationDeliveryStatus.FAILED
    return NotificationDeliveryStatus.PARTIAL


def _build_price_history_entry(
    *,
    watch_item_id: str,
    check_result: CheckResult,
) -> PriceHistoryEntry | None:
    """只在有有效價格時建立 `price_history` 紀錄。"""
    snapshot = check_result.current_snapshot
    if (
        snapshot.display_price_text is None
        or snapshot.normalized_price_amount is None
        or snapshot.currency is None
    ):
        return None

    return PriceHistoryEntry(
        watch_item_id=watch_item_id,
        captured_at=check_result.checked_at,
        display_price_text=snapshot.display_price_text,
        normalized_price_amount=snapshot.normalized_price_amount,
        currency=snapshot.currency,
        source_kind=snapshot.source_kind,
    )
