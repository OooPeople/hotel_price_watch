from datetime import date, datetime
from decimal import Decimal

from app.domain.entities import (
    CheckResult,
    NotificationDecision,
    NotificationState,
    PriceSnapshot,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    NotificationEventKind,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.notifiers.formatters import build_notification_message


def test_build_notification_message_formats_price_drop_content() -> None:
    message = build_notification_message(
        watch_item=_watch_item(),
        check_result=CheckResult(
            checked_at=datetime(2026, 4, 12, 10, 0, 0),
            current_snapshot=_snapshot(amount="22000"),
            previous_snapshot=_snapshot(amount="24000"),
            price_changed=True,
            availability_changed=False,
            price_dropped=True,
            became_available=False,
            parse_failed=False,
        ),
        decision=NotificationDecision(
            event_kinds=(NotificationEventKind.PRICE_DROP,),
            next_state=NotificationState(watch_item_id="watch-1"),
        ),
    )

    assert message.title == "價格下降：Ocean Hotel"
    assert "房型：Standard Twin" in message.body
    assert "價格：JPY 22000" in message.body
    assert message.tags == ("price-drop",)
    assert message.dedupe_key == "watch-1:price_drop:available:22000"


def test_build_notification_message_formats_parse_failed_content() -> None:
    message = build_notification_message(
        watch_item=_watch_item(),
        check_result=CheckResult(
            checked_at=datetime(2026, 4, 12, 10, 0, 0),
            current_snapshot=_snapshot(amount=None, availability=Availability.PARSE_ERROR),
            previous_snapshot=None,
            price_changed=False,
            availability_changed=True,
            price_dropped=False,
            became_available=False,
            parse_failed=True,
        ),
        decision=NotificationDecision(
            event_kinds=(NotificationEventKind.PARSE_FAILED,),
            next_state=NotificationState(watch_item_id="watch-1"),
        ),
    )

    assert message.title == "解析異常：Ocean Hotel"
    assert "狀態：parse_error" in message.body
    assert message.tags == ("parse-failed",)


def _watch_item() -> WatchItem:
    """建立通知格式化測試共用的 watch item。"""
    return WatchItem(
        id="watch-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="hotel-123",
            room_id="room-1",
            plan_id="plan-1",
            check_in_date=date(2026, 5, 1),
            check_out_date=date(2026, 5, 3),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Ocean Hotel",
        room_name="Standard Twin",
        plan_name="Room Only",
        canonical_url="https://www.ikyu.com/hotel/hotel-123",
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
    )


def _snapshot(
    *,
    amount: str | None,
    availability: Availability = Availability.AVAILABLE,
) -> PriceSnapshot:
    """建立通知格式化測試共用的快照。"""
    return PriceSnapshot(
        display_price_text=None if amount is None else f"JPY {amount}",
        normalized_price_amount=None if amount is None else Decimal(amount),
        currency=None if amount is None else "JPY",
        availability=availability,
        source_kind=SourceKind.HTTP,
    )
