"""把 domain 檢查結果整理成可送出的通知文字。"""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import CheckResult, NotificationDecision, WatchItem
from app.domain.enums import NotificationEventKind
from app.notifiers.models import NotificationMessage


def build_notification_message(
    *,
    watch_item: WatchItem,
    check_result: CheckResult,
    decision: NotificationDecision,
) -> NotificationMessage:
    """把通知決策轉成可跨通道共用的訊息內容。"""
    event_kinds = decision.event_kinds
    title = _build_title(watch_item=watch_item, event_kinds=event_kinds)
    body = _build_body(
        watch_item=watch_item,
        check_result=check_result,
        event_kinds=event_kinds,
    )
    return NotificationMessage(
        watch_item_id=watch_item.id,
        dedupe_key=_build_dedupe_key(
            watch_item=watch_item,
            check_result=check_result,
            event_kinds=event_kinds,
        ),
        title=title,
        body=body,
        tags=tuple(_event_tag(event_kind) for event_kind in event_kinds),
    )


def _build_title(
    *,
    watch_item: WatchItem,
    event_kinds: tuple[NotificationEventKind, ...],
) -> str:
    """依事件種類產生簡短的通知標題。"""
    prefix = "、".join(_event_title(event_kind) for event_kind in event_kinds) or "監看更新"
    return f"{prefix}：{watch_item.hotel_name}"


def _build_body(
    *,
    watch_item: WatchItem,
    check_result: CheckResult,
    event_kinds: tuple[NotificationEventKind, ...],
) -> str:
    """組合通知本文，帶出方案與價格狀態。"""
    snapshot = check_result.current_snapshot
    lines = [
        f"房型：{watch_item.room_name}",
        f"方案：{watch_item.plan_name}",
        f"事件：{'、'.join(_event_title(event_kind) for event_kind in event_kinds) or '檢查完成'}",
    ]

    if snapshot.display_price_text is not None:
        lines.append(f"價格：{snapshot.display_price_text}")
    elif snapshot.normalized_price_amount is not None and snapshot.currency is not None:
        lines.append(
            f"價格：{snapshot.currency} {_format_decimal(snapshot.normalized_price_amount)}"
        )
    else:
        lines.append(f"狀態：{snapshot.availability.value}")

    return "\n".join(lines)


def _build_dedupe_key(
    *,
    watch_item: WatchItem,
    check_result: CheckResult,
    event_kinds: tuple[NotificationEventKind, ...],
) -> str:
    """建立跨通道共用的通知節流 key。"""
    snapshot = check_result.current_snapshot
    amount = (
        "na"
        if snapshot.normalized_price_amount is None
        else _format_decimal(snapshot.normalized_price_amount)
    )
    events = ",".join(event_kind.value for event_kind in event_kinds) or "checked"
    return f"{watch_item.id}:{events}:{snapshot.availability.value}:{amount}"


def _event_title(event_kind: NotificationEventKind) -> str:
    """把事件列舉轉成通知顯示用中文標題。"""
    mapping = {
        NotificationEventKind.PRICE_DROP: "價格下降",
        NotificationEventKind.BELOW_TARGET_PRICE: "低於目標價",
        NotificationEventKind.BECAME_AVAILABLE: "恢復可訂",
        NotificationEventKind.PARSE_FAILED: "解析異常",
    }
    return mapping[event_kind]


def _event_tag(event_kind: NotificationEventKind) -> str:
    """把事件列舉轉成遠端通知可用的標籤字串。"""
    return event_kind.value.replace("_", "-")


def _format_decimal(value: Decimal) -> str:
    """把 `Decimal` 價格轉成通知 key 與顯示可用的字串。"""
    normalized = value.normalize()
    return format(normalized, "f")
