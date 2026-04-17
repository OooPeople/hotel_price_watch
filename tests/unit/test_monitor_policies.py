from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.entities import (
    LatestCheckSnapshot,
    NotificationDecision,
    NotificationDispatchResult,
    NotificationState,
    PriceSnapshot,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationDeliveryStatus,
    NotificationEventKind,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_engine import compare_snapshots
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.monitor.policies import (
    TaskDispositionKind,
    TaskLifecycleCheckpoint,
    build_monitor_check_artifacts,
    build_runtime_control_recommendation,
    decide_error_handling,
    evaluate_task_lifecycle_disposition,
    reset_notification_state_after_success,
    should_trigger_wakeup_rescan,
)


def test_rate_limited_backoff_caps_at_two_hours() -> None:
    """驗證 rate limited 連續失敗的退避時間最高限制為兩小時。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.RATE_LIMITED_429,
        consecutive_failures=5,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 12, 0, 0)
    assert decision.should_pause is False


def test_forbidden_pauses_watch_item() -> None:
    """驗證 forbidden 類阻擋會建議暫停 watch 而不是只做 backoff。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.FORBIDDEN_403,
        consecutive_failures=1,
    )

    assert decision.should_pause is True
    assert decision.paused_reason is CheckErrorCode.FORBIDDEN_403
    assert decision.backoff_until is None


def test_network_error_backoff_caps_at_thirty_minutes() -> None:
    """驗證網路錯誤連續失敗的退避時間最高限制為三十分鐘。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.NETWORK_TIMEOUT,
        consecutive_failures=4,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 10, 30, 0)


def test_parse_failed_backoff_matches_short_retry_strategy() -> None:
    """驗證 parse_failed 也會進入短退避，而不是高頻重試。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.PARSE_FAILED,
        consecutive_failures=3,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 10, 20, 0)
    assert decision.should_pause is False


def test_runtime_control_recommendation_pauses_for_forbidden() -> None:
    """runtime control recommendation 應把 forbidden 決策轉成暫停 watch。"""
    watch_item = _watch_item()
    checked_at = datetime(2026, 4, 12, 10, 0, 0)
    recommendation = build_runtime_control_recommendation(
        watch_item=watch_item,
        latest_snapshot=None,
        next_snapshot=_latest_snapshot(checked_at=checked_at),
        error_handling=decide_error_handling(
            checked_at=checked_at,
            error_code=CheckErrorCode.FORBIDDEN_403,
            consecutive_failures=1,
        ),
        error_code=CheckErrorCode.FORBIDDEN_403,
        occurred_at=checked_at,
    )

    assert recommendation.watch_item is not None
    assert recommendation.watch_item.enabled is True
    assert recommendation.watch_item.paused_reason == "http_403"
    assert recommendation.remove_from_scheduler is True


def test_task_lifecycle_policy_allows_active_watch_to_continue() -> None:
    """active watch 在 checkpoint 應可繼續執行下一個 side effect。"""
    disposition = evaluate_task_lifecycle_disposition(
        watch_item=_watch_item(),
        checkpoint=TaskLifecycleCheckpoint.BEFORE_NOTIFICATION_DISPATCH,
    )

    assert disposition.kind is TaskDispositionKind.CONTINUE
    assert disposition.should_continue is True
    assert disposition.reason is None


def test_task_lifecycle_policy_discards_paused_watch() -> None:
    """paused watch 在 checkpoint 應丟棄後續結果。"""
    disposition = evaluate_task_lifecycle_disposition(
        watch_item=replace(_watch_item(), paused_reason="manually_paused"),
        checkpoint=TaskLifecycleCheckpoint.BEFORE_PERSIST_RESULT,
    )

    assert disposition.kind is TaskDispositionKind.DISCARD
    assert disposition.should_discard is True
    assert disposition.reason == "watch_paused:manually_paused"


def test_task_lifecycle_policy_discards_missing_watch() -> None:
    """不存在的 watch 在 checkpoint 應丟棄後續結果。"""
    disposition = evaluate_task_lifecycle_disposition(
        watch_item=None,
        checkpoint=TaskLifecycleCheckpoint.AFTER_CAPTURE,
    )

    assert disposition.kind is TaskDispositionKind.DISCARD
    assert disposition.reason == "watch_missing"


def test_wakeup_rescan_respects_backoff_window() -> None:
    """驗證恢復後喚醒重掃不會繞過尚未結束的 backoff。"""
    resumed_at = datetime(2026, 4, 12, 10, 30, 0)

    assert (
        should_trigger_wakeup_rescan(
            resumed_at=resumed_at,
            last_checked_at=datetime(2026, 4, 12, 9, 0, 0),
            backoff_until=resumed_at + timedelta(minutes=5),
        )
        is False
    )
    assert (
        should_trigger_wakeup_rescan(
            resumed_at=resumed_at,
            last_checked_at=datetime(2026, 4, 12, 9, 0, 0),
            backoff_until=None,
        )
        is True
    )


def test_build_monitor_check_artifacts_creates_history_and_latest_snapshot() -> None:
    """驗證成功降價檢查會建立 latest snapshot、check event 與 price history。"""
    checked_at = datetime(2026, 4, 12, 10, 0, 0)
    result = compare_snapshots(
        checked_at=checked_at,
        previous_snapshot=_snapshot(amount="24000"),
        current_snapshot=_snapshot(amount="22000"),
    )
    decision = NotificationDecision(
        event_kinds=(NotificationEventKind.PRICE_DROP,),
        next_state=NotificationState(
            watch_item_id="watch-1",
            last_notified_price=Decimal("22000"),
            last_notified_availability=Availability.AVAILABLE,
            last_notified_at=checked_at,
        ),
    )

    artifacts = build_monitor_check_artifacts(
        watch_item_id="watch-1",
        check_result=result,
        notification_decision=decision,
        error_code=None,
        error_handling=decide_error_handling(
            checked_at=checked_at,
            error_code=None,
            consecutive_failures=0,
        ),
    )

    assert artifacts.latest_check_snapshot.watch_item_id == "watch-1"
    assert artifacts.latest_check_snapshot.normalized_price_amount == Decimal("22000")
    assert artifacts.check_event.event_kinds == ("price_drop",)
    assert artifacts.check_event.notification_status is NotificationDeliveryStatus.PENDING_DISPATCH
    assert artifacts.price_history_entry is not None
    assert artifacts.price_history_entry.normalized_price_amount == Decimal("22000")


def test_build_monitor_check_artifacts_skips_price_history_without_price() -> None:
    """驗證沒有有效價格的錯誤結果不會寫入 price history。"""
    checked_at = datetime(2026, 4, 12, 10, 0, 0)
    result = compare_snapshots(
        checked_at=checked_at,
        previous_snapshot=None,
        current_snapshot=_snapshot(amount=None, availability=Availability.PARSE_ERROR),
    )

    artifacts = build_monitor_check_artifacts(
        watch_item_id="watch-1",
        check_result=result,
        notification_decision=NotificationDecision(
            event_kinds=(),
            next_state=NotificationState(
                watch_item_id="watch-1",
                consecutive_failures=3,
                consecutive_parse_failures=3,
            ),
        ),
        error_code=CheckErrorCode.PARSE_FAILED,
        error_handling=decide_error_handling(
            checked_at=checked_at,
            error_code=CheckErrorCode.PARSE_FAILED,
            consecutive_failures=3,
        ),
    )

    assert artifacts.latest_check_snapshot.is_degraded is True
    assert artifacts.latest_check_snapshot.consecutive_failures == 3
    assert artifacts.latest_check_snapshot.last_error_code == "parse_failed"
    assert artifacts.check_event.event_kinds == ("parse_failed",)
    assert artifacts.check_event.notification_status is NotificationDeliveryStatus.NOT_REQUESTED
    assert artifacts.price_history_entry is None


def test_build_monitor_check_artifacts_keeps_multiple_notification_events() -> None:
    """驗證同次檢查可同時保留多個通知事件種類。"""
    checked_at = datetime(2026, 4, 12, 10, 0, 0)
    result = compare_snapshots(
        checked_at=checked_at,
        previous_snapshot=_snapshot(amount=None, availability=Availability.SOLD_OUT),
        current_snapshot=_snapshot(amount="22000", availability=Availability.AVAILABLE),
    )

    artifacts = build_monitor_check_artifacts(
        watch_item_id="watch-1",
        check_result=result,
        notification_decision=NotificationDecision(
            event_kinds=(
                NotificationEventKind.PRICE_DROP,
                NotificationEventKind.BECAME_AVAILABLE,
            ),
            next_state=NotificationState(
                watch_item_id="watch-1",
                last_notified_price=Decimal("22000"),
                last_notified_availability=Availability.AVAILABLE,
                last_notified_at=checked_at,
            ),
        ),
        error_code=None,
        error_handling=decide_error_handling(
            checked_at=checked_at,
            error_code=None,
            consecutive_failures=0,
        ),
    )

    assert artifacts.check_event.event_kinds == ("price_drop", "became_available")


def test_build_monitor_check_artifacts_records_actual_dispatch_result() -> None:
    """驗證 check event 會保存實際 dispatch 結果，而不是理論通知值。"""
    checked_at = datetime(2026, 4, 12, 10, 0, 0)
    result = compare_snapshots(
        checked_at=checked_at,
        previous_snapshot=_snapshot(amount="24000"),
        current_snapshot=_snapshot(amount="22000"),
    )

    artifacts = build_monitor_check_artifacts(
        watch_item_id="watch-1",
        check_result=result,
        notification_decision=NotificationDecision(
            event_kinds=(NotificationEventKind.PRICE_DROP,),
            next_state=NotificationState(watch_item_id="watch-1"),
        ),
        error_code=None,
        error_handling=decide_error_handling(
            checked_at=checked_at,
            error_code=None,
            consecutive_failures=0,
        ),
        dispatch_result=NotificationDispatchResult(
            sent_channels=("desktop",),
            throttled_channels=("discord",),
            failed_channels=(),
            attempted_at=checked_at,
        ),
    )

    assert artifacts.check_event.notification_status is NotificationDeliveryStatus.PARTIAL
    assert artifacts.check_event.sent_channels == ("desktop",)
    assert artifacts.check_event.throttled_channels == ("discord",)
    assert artifacts.check_event.failed_channels == ()


def test_reset_notification_state_after_success_clears_parse_failure_streak() -> None:
    """驗證成功檢查後會清除通知狀態中的解析失敗 streak。"""
    next_state = reset_notification_state_after_success(
        NotificationState(
            watch_item_id="watch-1",
            consecutive_failures=4,
            consecutive_parse_failures=4,
            degraded_notified_at=datetime(2026, 4, 12, 10, 0, 0),
        )
    )

    assert next_state.consecutive_failures == 0
    assert next_state.consecutive_parse_failures == 0
    assert next_state.degraded_notified_at is None


def _snapshot(
    *,
    amount: str | None,
    availability: Availability = Availability.AVAILABLE,
) -> PriceSnapshot:
    """建立 monitor policy 測試共用的價格快照。"""
    return PriceSnapshot(
        display_price_text=None if amount is None else f"JPY {amount}",
        normalized_price_amount=None if amount is None else Decimal(amount),
        currency=None if amount is None else "JPY",
        availability=availability,
        source_kind=SourceKind.HTTP,
    )


def _latest_snapshot(*, checked_at: datetime) -> LatestCheckSnapshot:
    """建立 runtime control recommendation 測試使用的最新檢查摘要。"""
    return LatestCheckSnapshot(
        watch_item_id="watch-1",
        checked_at=checked_at,
        availability=Availability.UNKNOWN,
        normalized_price_amount=None,
        currency=None,
        consecutive_failures=1,
        last_error_code=CheckErrorCode.FORBIDDEN_403.value,
    )


def _watch_item() -> WatchItem:
    """建立 monitor policy 測試使用的 watch item。"""
    return WatchItem(
        id="watch-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=datetime(2026, 9, 18).date(),
            check_out_date=datetime(2026, 9, 19).date(),
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
    )
