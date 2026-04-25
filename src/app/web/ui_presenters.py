"""本機 GUI 的 presentation helper，集中處理顯示文案與 badge 語意。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.domain.entities import WatchItem
from app.domain.enums import (
    Availability,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    WatchRuntimeState,
)


@dataclass(frozen=True)
class BadgePresentation:
    """描述 UI badge 需要的顯示文字與語意樣式。"""

    label: str
    kind: str


def format_decimal_for_display(amount: Decimal) -> str:
    """把 Decimal 數字格式化成較適合 GUI 顯示的文字。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")


def money_text(currency: str | None, amount: Decimal | None) -> str:
    """把可選價格欄位整理成使用者可讀文字。"""
    if amount is None:
        return "無資料"
    amount_text = format_decimal_for_display(amount)
    return f"{currency or ''} {amount_text}".strip()


def availability_badge(availability: Availability) -> BadgePresentation:
    """依空房狀態回傳 badge 呈現資訊。"""
    mapping = {
        Availability.AVAILABLE: BadgePresentation("有空房", "success"),
        Availability.SOLD_OUT: BadgePresentation("已售完", "warning"),
        Availability.UNKNOWN: BadgePresentation("狀態未知", "muted"),
        Availability.PARSE_ERROR: BadgePresentation("解析問題", "danger"),
        Availability.TARGET_MISSING: BadgePresentation("目標消失", "warning"),
    }
    return mapping[availability]


def notification_status_badge(
    status: NotificationDeliveryStatus,
) -> BadgePresentation:
    """依通知派送狀態回傳 badge 呈現資訊。"""
    mapping = {
        NotificationDeliveryStatus.NOT_REQUESTED: BadgePresentation("本次未通知", "muted"),
        NotificationDeliveryStatus.PENDING_DISPATCH: BadgePresentation("等待通知", "info"),
        NotificationDeliveryStatus.SENT: BadgePresentation("已通知", "success"),
        NotificationDeliveryStatus.THROTTLED: BadgePresentation("通知節流", "warning"),
        NotificationDeliveryStatus.FAILED: BadgePresentation("通知失敗", "danger"),
        NotificationDeliveryStatus.PARTIAL: BadgePresentation("部分通知成功", "warning"),
    }
    return mapping[status]


def runtime_state_badge(state: WatchRuntimeState) -> BadgePresentation:
    """依 watch runtime 狀態回傳 badge 呈現資訊。"""
    mapping = {
        WatchRuntimeState.ACTIVE: BadgePresentation("監視中", "success"),
        WatchRuntimeState.BACKOFF_ACTIVE: BadgePresentation("退避中", "warning"),
        WatchRuntimeState.DEGRADED_ACTIVE: BadgePresentation("降級運作", "warning"),
        WatchRuntimeState.RECOVER_PENDING: BadgePresentation("恢復確認中", "info"),
        WatchRuntimeState.MANUALLY_PAUSED: BadgePresentation("已暫停", "muted"),
        WatchRuntimeState.MANUALLY_DISABLED: BadgePresentation("已停用", "muted"),
        WatchRuntimeState.PAUSED_BLOCKED: BadgePresentation("因阻擋暫停", "danger"),
        WatchRuntimeState.PAUSED_BLOCKED_403: BadgePresentation("因阻擋暫停", "danger"),
        WatchRuntimeState.PAUSED_OTHER: BadgePresentation("已暫停", "warning"),
    }
    return mapping[state]


def check_event_kinds_text(event_kinds: Iterable[str]) -> str:
    """把檢查事件類型轉成較自然的使用者文案。"""
    mapping = {
        "checked": "已檢查",
        "price_changed": "價格變動",
        "price_drop": "價格下降",
        "availability_changed": "空房狀態變動",
        "became_available": "恢復可訂",
        "sold_out": "售完",
        "parse_failed": "解析問題",
        "target_missing": "目標消失",
    }
    labels = [mapping.get(event_kind, event_kind) for event_kind in event_kinds]
    return "、".join(labels) if labels else "已檢查"


def error_code_text(error_code: str | None) -> str:
    """把錯誤代碼轉成較易理解的摘要文字。"""
    if not error_code:
        return "無"
    mapping = {
        "network_timeout": "網路逾時",
        "network_error": "網路錯誤",
        "http_429": "站方節流",
        "http_403": "站方阻擋",
        "parse_failed": "解析問題",
        "target_missing": "目標消失",
    }
    return mapping.get(error_code, error_code)


def notification_rule_text(watch_item: WatchItem) -> str:
    """把 V1 通知條件整理成使用者可讀摘要。"""
    rule = watch_item.notification_rule
    if getattr(rule, "kind", None) == NotificationLeafKind.ANY_DROP:
        return "價格下降時"

    target_price = getattr(rule, "target_price", None)
    if getattr(rule, "kind", None) == NotificationLeafKind.BELOW_TARGET_PRICE:
        if target_price is None:
            return "低於目標價時通知"
        return f"低於目標價 {format_decimal_for_display(target_price)} 時通知"

    return "複合通知規則"
