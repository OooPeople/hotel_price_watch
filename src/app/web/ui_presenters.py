"""本機 GUI 的 presentation helper，集中處理顯示文案與 badge 語意。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

from app.domain import derive_watch_runtime_state
from app.domain.entities import LatestCheckSnapshot, PriceHistoryEntry, WatchItem
from app.domain.enums import (
    Availability,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    WatchRuntimeState,
)
from app.web.view_formatters import format_datetime_for_display


@dataclass(frozen=True)
class BadgePresentation:
    """描述 UI badge 需要的顯示文字與語意樣式。"""

    label: str
    kind: str


class WatchActionSurface(StrEnum):
    """表示 watch action controls 所在的頁面情境。"""

    LIST = "list"
    DETAIL = "detail"


@dataclass(frozen=True)
class WatchActionPresentation:
    """描述單一 watch 操作按鈕的行為與顯示方式。"""

    action: str
    label: str
    button_kind: str
    submit_mode: str
    confirm_message: str | None = None


@dataclass(frozen=True)
class WatchRowPresentation:
    """集中首頁 watch row / card 需要的顯示文字與狀態語意。"""

    watch_id: str
    runtime_state: WatchRuntimeState
    hotel_name: str
    room_name: str
    plan_name: str
    date_range_text: str
    date_range_short_text: str
    nights_text: str
    occupancy_text: str
    current_price_text: str
    availability_badge: BadgePresentation | None
    runtime_state_badge: BadgePresentation
    runtime_state_helper_text: str
    attention_badge: BadgePresentation | None
    notification_rule_text: str
    price_change_text: str
    price_change_kind: str
    price_change_helper_text: str
    last_checked_text: str
    last_checked_short_text: str
    last_checked_relative_text: str
    last_checked_at_iso: str | None
    error_text: str
    runtime_state_helper_target_iso: str | None
    sort_key: tuple[int, float, str]


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


def build_watch_action_presentations(
    *,
    runtime_state: WatchRuntimeState,
    surface: WatchActionSurface,
) -> tuple[WatchActionPresentation, ...]:
    """依頁面情境與 runtime 狀態建立 watch 操作按鈕 view model。"""
    submit_mode = "fetch" if surface is WatchActionSurface.LIST else "form"
    actions: list[WatchActionPresentation] = []

    if surface is WatchActionSurface.DETAIL and runtime_state in {
        WatchRuntimeState.ACTIVE,
        WatchRuntimeState.BACKOFF_ACTIVE,
        WatchRuntimeState.DEGRADED_ACTIVE,
        WatchRuntimeState.RECOVER_PENDING,
    }:
        actions.append(
            WatchActionPresentation(
                action="check-now",
                label="立即檢查",
                button_kind="primary",
                submit_mode=submit_mode,
            )
        )

    if runtime_state in {
        WatchRuntimeState.ACTIVE,
        WatchRuntimeState.BACKOFF_ACTIVE,
        WatchRuntimeState.DEGRADED_ACTIVE,
        WatchRuntimeState.RECOVER_PENDING,
    }:
        actions.append(
            WatchActionPresentation(
                action="pause",
                label="暫停",
                button_kind="secondary",
                submit_mode=submit_mode,
            )
        )
    elif runtime_state in {
        WatchRuntimeState.MANUALLY_PAUSED,
        WatchRuntimeState.PAUSED_BLOCKED,
        WatchRuntimeState.PAUSED_BLOCKED_403,
        WatchRuntimeState.PAUSED_OTHER,
    }:
        actions.append(
            WatchActionPresentation(
                action="resume",
                label="恢復",
                button_kind="primary",
                submit_mode=submit_mode,
            )
        )
    else:
        actions.append(
            WatchActionPresentation(
                action="enable",
                label="啟用",
                button_kind="primary",
                submit_mode=submit_mode,
            )
        )

    actions.append(
        WatchActionPresentation(
            action="delete",
            label="刪除",
            button_kind="danger",
            submit_mode=submit_mode,
            confirm_message="確定要刪除此監視嗎？此操作無法復原。",
        )
    )
    return tuple(actions)


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


def build_watch_row_presentation(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    use_24_hour_time: bool,
    recent_price_history: tuple[PriceHistoryEntry, ...] = (),
) -> WatchRowPresentation:
    """把首頁 watch row 所需判讀集中成穩定 view model。"""
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    runtime_badge = runtime_state_badge(runtime_state)
    attention_badge = _watch_attention_badge(
        runtime_state=runtime_state,
        latest_snapshot=latest_snapshot,
        watch_item=watch_item,
    )
    checked_at = latest_snapshot.checked_at if latest_snapshot is not None else None
    date_range_short = _format_date_range_core(watch_item)
    nights_text = f"{watch_item.target.nights} 晚"
    current_price_text = (
        money_text(
            latest_snapshot.currency,
            latest_snapshot.normalized_price_amount,
        )
        if latest_snapshot is not None
        else "尚未檢查"
    )
    availability = (
        availability_badge(latest_snapshot.availability)
        if latest_snapshot is not None
        else None
    )
    price_change_text, price_change_kind, price_change_helper = (
        _price_change_presentation(recent_price_history)
    )
    attention_rank = 0 if _watch_needs_attention(latest_snapshot) else 1
    checked_rank = -(checked_at.timestamp()) if checked_at is not None else 0.0
    return WatchRowPresentation(
        watch_id=watch_item.id,
        runtime_state=runtime_state,
        hotel_name=watch_item.hotel_name,
        room_name=watch_item.room_name,
        plan_name=watch_item.plan_name,
        date_range_text=f"{date_range_short}，{nights_text}",
        date_range_short_text=date_range_short,
        nights_text=nights_text,
        occupancy_text=(
            f"{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房"
        ),
        current_price_text=current_price_text,
        availability_badge=availability,
        runtime_state_badge=runtime_badge,
        runtime_state_helper_text=_runtime_state_helper_text(
            runtime_state=runtime_state,
            latest_snapshot=latest_snapshot,
        ),
        attention_badge=attention_badge,
        notification_rule_text=notification_rule_text(watch_item),
        price_change_text=price_change_text,
        price_change_kind=price_change_kind,
        price_change_helper_text=price_change_helper,
        last_checked_text=(
            format_datetime_for_display(checked_at, use_24_hour_time=use_24_hour_time)
            if checked_at is not None
            else "尚未檢查"
        ),
        last_checked_short_text=(
            _format_short_datetime_for_list(
                checked_at,
                use_24_hour_time=use_24_hour_time,
            )
            if checked_at is not None
            else "尚未檢查"
        ),
        last_checked_relative_text=(
            _format_relative_time(checked_at) if checked_at is not None else "尚未檢查"
        ),
        last_checked_at_iso=checked_at.isoformat() if checked_at is not None else None,
        error_text=(
            error_code_text(latest_snapshot.last_error_code)
            if latest_snapshot is not None
            else "無"
        ),
        runtime_state_helper_target_iso=(
            latest_snapshot.backoff_until.isoformat()
            if runtime_state is WatchRuntimeState.BACKOFF_ACTIVE
            and latest_snapshot is not None
            and latest_snapshot.backoff_until is not None
            else None
        ),
        sort_key=(attention_rank, checked_rank, watch_item.hotel_name),
    )


def _watch_attention_badge(
    *,
    runtime_state: WatchRuntimeState,
    latest_snapshot: LatestCheckSnapshot | None,
    watch_item: WatchItem,
) -> BadgePresentation | None:
    """依 runtime / latest snapshot 推導首頁優先掃描狀態。"""
    if latest_snapshot is None:
        return BadgePresentation("尚未檢查", "muted")
    if runtime_state is not WatchRuntimeState.ACTIVE:
        return runtime_state_badge(runtime_state)
    if latest_snapshot.last_error_code:
        return BadgePresentation("最近檢查失敗", "danger")
    if latest_snapshot.availability is Availability.AVAILABLE:
        return None
    if latest_snapshot.availability is Availability.SOLD_OUT:
        return BadgePresentation("目前售完", "warning")
    if latest_snapshot.availability is Availability.PARSE_ERROR:
        return BadgePresentation("解析問題", "danger")
    if latest_snapshot.availability is Availability.TARGET_MISSING:
        return BadgePresentation("目標消失", "warning")
    return BadgePresentation("狀態待確認", "muted")


def _runtime_state_helper_text(
    *,
    runtime_state: WatchRuntimeState,
    latest_snapshot: LatestCheckSnapshot | None,
) -> str:
    """依 runtime 狀態提供 Dashboard 狀態欄的下一步提示。"""
    if runtime_state is WatchRuntimeState.BACKOFF_ACTIVE:
        if latest_snapshot is not None and latest_snapshot.backoff_until is not None:
            return _format_backoff_retry_text(latest_snapshot.backoff_until)
        return "系統會自動重試"
    mapping = {
        WatchRuntimeState.DEGRADED_ACTIVE: "系統會繼續檢查，若持續異常請看進階診斷",
        WatchRuntimeState.RECOVER_PENDING: "系統會自動確認是否恢復",
        WatchRuntimeState.MANUALLY_PAUSED: "按恢復後才會繼續",
        WatchRuntimeState.MANUALLY_DISABLED: "按啟用後才會加入排程",
        WatchRuntimeState.PAUSED_BLOCKED: "處理專用 Chrome 或站方阻擋後再恢復",
        WatchRuntimeState.PAUSED_BLOCKED_403: "處理專用 Chrome 或站方阻擋後再恢復",
        WatchRuntimeState.PAUSED_OTHER: "查看進階診斷後再恢復",
    }
    return mapping.get(runtime_state, "")


def _format_backoff_retry_text(backoff_until: datetime) -> str:
    """把退避結束時間轉成不含秒數的自動重試提示。"""
    now = datetime.now(backoff_until.tzinfo)
    remaining_seconds = int((backoff_until - now).total_seconds())
    if remaining_seconds <= 60:
        return "預計 1 分鐘內自動重試"
    remaining_minutes = (remaining_seconds + 59) // 60
    return f"預計 {remaining_minutes} 分鐘後自動重試"


def _price_change_presentation(
    recent_price_history: tuple[PriceHistoryEntry, ...],
) -> tuple[str, str, str]:
    """依 24 小時內有效價格計算 Dashboard 的價格變動文案。"""
    if len(recent_price_history) < 2:
        return ("尚無前次價格", "muted", "24 小時內資料不足")
    first_entry = recent_price_history[0]
    latest_entry = recent_price_history[-1]
    delta = latest_entry.normalized_price_amount - first_entry.normalized_price_amount
    if delta == 0:
        return ("—", "muted", "過去 24 小時")
    if delta < 0:
        return (f"▼ {money_text(latest_entry.currency, abs(delta))}", "success", "過去 24 小時")
    return (f"▲ {money_text(latest_entry.currency, delta)}", "danger", "過去 24 小時")


def price_history_changed(recent_price_history: tuple[PriceHistoryEntry, ...]) -> bool:
    """判斷 24 小時內價格是否有非零變動，供 Dashboard summary 使用。"""
    if len(recent_price_history) < 2:
        return False
    return (
        recent_price_history[-1].normalized_price_amount
        != recent_price_history[0].normalized_price_amount
    )


def price_history_increased(recent_price_history: tuple[PriceHistoryEntry, ...]) -> bool:
    """判斷 24 小時價格是否上漲，供需要注意摘要使用。"""
    if len(recent_price_history) < 2:
        return False
    return (
        recent_price_history[-1].normalized_price_amount
        > recent_price_history[0].normalized_price_amount
    )


def _watch_needs_attention(snapshot: LatestCheckSnapshot | None) -> bool:
    """判斷首頁排序是否應把 watch 計入需注意項目。"""
    if snapshot is None:
        return False
    return snapshot.last_error_code is not None or snapshot.backoff_until is not None


def _format_date_range_core(watch_item: WatchItem) -> str:
    """產生不含晚數的精簡日期區間，跨年時才顯示年份。"""
    check_in = watch_item.target.check_in_date
    check_out = watch_item.target.check_out_date
    if check_in.year == check_out.year:
        return f"{check_in.month}/{check_in.day} - {check_out.month}/{check_out.day}"
    return (
        f"{check_in.year}/{check_in.month}/{check_in.day} - "
        f"{check_out.year}/{check_out.month}/{check_out.day}"
    )


def _format_short_datetime_for_list(
    value: datetime,
    *,
    use_24_hour_time: bool,
) -> str:
    """產生清單欄位使用的短時間格式，避免年份佔用過多欄寬。"""
    local_value = value.astimezone()
    if use_24_hour_time:
        return f"{local_value.month}/{local_value.day} {local_value:%H:%M}"

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return f"{local_value.month}/{local_value.day} {period_text} {hour:02d}:{local_value:%M}"


def _format_relative_time(value: datetime) -> str:
    """把檢查時間轉成首頁列表使用的相對時間文案。"""
    now = datetime.now(value.tzinfo)
    elapsed_seconds = max(int((now - value).total_seconds()), 0)
    if elapsed_seconds < 60:
        return "剛剛"
    elapsed_minutes = elapsed_seconds // 60
    if elapsed_minutes < 60:
        return f"{elapsed_minutes} 分鐘前"
    elapsed_hours = elapsed_minutes // 60
    if elapsed_hours < 24:
        return f"{elapsed_hours} 小時前"
    elapsed_days = elapsed_hours // 24
    return f"{elapsed_days} 天前"
