"""monitor check artifact 建立與 notification state policy 測試。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.domain.entities import (
    NotificationDecision,
    NotificationDispatchResult,
    NotificationState,
)
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationDeliveryStatus,
    NotificationEventKind,
)
from app.domain.notification_engine import compare_snapshots
from app.monitor.policies import (
    build_monitor_check_artifacts,
    decide_error_handling,
    reset_notification_state_after_success,
)

from .helpers import _snapshot


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
