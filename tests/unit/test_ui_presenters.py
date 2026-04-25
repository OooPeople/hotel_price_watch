"""GUI presentation helper 測試。"""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import WatchItem
from app.domain.enums import (
    Availability,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    WatchRuntimeState,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.web.ui_presenters import (
    availability_badge,
    check_event_kinds_text,
    error_code_text,
    money_text,
    notification_rule_text,
    notification_status_badge,
    runtime_state_badge,
)


def test_money_text_formats_missing_and_integer_amounts() -> None:
    """價格顯示 helper 應把缺值與整數金額轉成穩定文案。"""
    assert money_text("JPY", None) == "無資料"
    assert money_text("JPY", Decimal("22990.00")) == "JPY 22990"


def test_badge_presenters_humanize_core_states() -> None:
    """核心狀態 badge helper 應輸出人話化標籤與穩定語意 kind。"""
    assert availability_badge(Availability.AVAILABLE).label == "有空房"
    assert availability_badge(Availability.PARSE_ERROR).kind == "danger"
    assert notification_status_badge(NotificationDeliveryStatus.NOT_REQUESTED).label == (
        "本次未通知"
    )
    assert runtime_state_badge(WatchRuntimeState.ACTIVE).label == "監視中"


def test_check_event_and_error_text_are_user_facing() -> None:
    """檢查事件與錯誤代碼應轉成人能理解的摘要文字。"""
    assert check_event_kinds_text(("checked", "price_changed")) == "已檢查、價格變動"
    assert check_event_kinds_text(("availability_changed",)) == "空房狀態變動"
    assert check_event_kinds_text(()) == "已檢查"
    assert error_code_text(None) == "無"
    assert error_code_text("http_403") == "站方阻擋"


def test_notification_rule_text_matches_supported_domain_rules() -> None:
    """通知規則摘要只呈現目前 domain 已支援的 V1 規則。"""
    assert notification_rule_text(_build_watch_item(NotificationLeafKind.ANY_DROP)) == (
        "價格下降時"
    )
    assert notification_rule_text(
        _build_watch_item(NotificationLeafKind.BELOW_TARGET_PRICE, Decimal("20000"))
    ) == "低於目標價 20000 時通知"


def _build_watch_item(
    kind: NotificationLeafKind,
    target_price: Decimal | None = None,
) -> WatchItem:
    """建立 presenter 測試用的最小 watch item。"""
    from datetime import date

    return WatchItem(
        id="watch-presenter-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="room-1",
            plan_id="plan-1",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Ocean Hotel",
        room_name="Standard Twin",
        plan_name="Room Only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
        notification_rule=RuleLeaf(kind=kind, target_price=target_price),
        scheduler_interval_seconds=600,
    )
