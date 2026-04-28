"""watch 詳細頁使用的 page-level presentation model。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain import derive_watch_runtime_state, describe_watch_runtime_state
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import RuntimeStateEventKind, WatchRuntimeState
from app.web.ui_presenters import (
    BadgePresentation,
    availability_badge,
    check_event_kinds_text,
    error_code_text,
    money_text,
    notification_rule_text,
    notification_status_badge,
    runtime_state_badge,
)
from app.web.view_formatters import format_datetime_for_display


@dataclass(frozen=True, slots=True)
class WatchDetailPresentation:
    """集中監視詳情頁首屏與摘要卡需要的顯示資料。"""

    watch_id: str
    hotel_name: str
    room_name: str
    canonical_url: str
    scheduler_interval_seconds: int
    date_range_text: str
    occupancy_text: str
    runtime_state: WatchRuntimeState
    runtime_state_badge: BadgePresentation
    last_checked_at: datetime | None
    current_price_text: str
    availability_text: str
    notification_rule_text: str
    last_notified_at: datetime | None


@dataclass(frozen=True, slots=True)
class PriceTrendPointPresentation:
    """描述價格趨勢圖中的單一有效價格點。"""

    checked_at: datetime
    checked_at_text: str
    axis_time_text: str
    price_text: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class PriceTrendPresentation:
    """描述詳情頁價格趨勢區塊需要的資料與空狀態。"""

    points: tuple[PriceTrendPointPresentation, ...]
    latest_price_text: str
    delta_text: str
    range_text: str


@dataclass(frozen=True, slots=True)
class CheckEventRowPresentation:
    """描述檢查歷史表格的一列顯示資料。"""

    checked_at_text: str
    availability_badge: BadgePresentation
    event_kind_text: str
    price_text: str
    error_text: str
    notification_badge: BadgePresentation


@dataclass(frozen=True, slots=True)
class RuntimeStateEventRowPresentation:
    """描述 runtime 狀態事件表格的一列顯示資料。"""

    occurred_at_text: str
    event_kind_text: str
    from_state_text: str
    to_state_text: str
    detail_text: str


@dataclass(frozen=True, slots=True)
class DebugArtifactRowPresentation:
    """描述 watch 關聯診斷檔案表格的一列顯示資料。"""

    captured_at_text: str
    reason_text: str
    source_url_text: str
    http_status_text: str


@dataclass(frozen=True, slots=True)
class WatchDetailPageViewModel:
    """集中監視詳情頁所有主要區塊的顯示資料。"""

    summary: WatchDetailPresentation
    price_trend: PriceTrendPresentation
    check_event_rows: tuple[CheckEventRowPresentation, ...]
    runtime_state_event_rows: tuple[RuntimeStateEventRowPresentation, ...]
    debug_artifact_rows: tuple[DebugArtifactRowPresentation, ...]


def build_watch_detail_presentation(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    notification_state: NotificationState | None,
) -> WatchDetailPresentation:
    """把 watch 詳細頁會用到的 domain 資料整理成穩定 view model。"""
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    return WatchDetailPresentation(
        watch_id=watch_item.id,
        hotel_name=watch_item.hotel_name,
        room_name=watch_item.room_name,
        canonical_url=watch_item.canonical_url,
        scheduler_interval_seconds=watch_item.scheduler_interval_seconds,
        date_range_text=(
            f"{watch_item.target.check_in_date.isoformat()} - "
            f"{watch_item.target.check_out_date.isoformat()}"
        ),
        occupancy_text=(
            f"{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房"
        ),
        runtime_state=runtime_state,
        runtime_state_badge=runtime_state_badge(runtime_state),
        last_checked_at=(
            latest_snapshot.checked_at if latest_snapshot is not None else None
        ),
        current_price_text=(
            money_text(
                latest_snapshot.currency,
                latest_snapshot.normalized_price_amount,
            )
            if latest_snapshot is not None
            else "尚未檢查"
        ),
        availability_text=(
            availability_badge(latest_snapshot.availability).label
            if latest_snapshot is not None
            else "尚未檢查"
        ),
        notification_rule_text=notification_rule_text(watch_item),
        last_notified_at=(
            notification_state.last_notified_at
            if notification_state is not None
            else None
        ),
    )


def build_watch_detail_page_view_model(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    check_events: tuple[CheckEvent, ...],
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    use_24_hour_time: bool,
) -> WatchDetailPageViewModel:
    """把詳情頁所有 domain 資料整理成 renderer 穩定使用的 view model。"""
    return WatchDetailPageViewModel(
        summary=build_watch_detail_presentation(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            notification_state=notification_state,
        ),
        price_trend=build_price_trend_presentation(
            check_events,
            use_24_hour_time=use_24_hour_time,
        ),
        check_event_rows=build_check_event_row_presentations(
            check_events,
            use_24_hour_time=use_24_hour_time,
        ),
        runtime_state_event_rows=build_runtime_state_event_row_presentations(
            runtime_state_events,
            use_24_hour_time=use_24_hour_time,
        ),
        debug_artifact_rows=build_debug_artifact_row_presentations(
            debug_artifacts,
            use_24_hour_time=use_24_hour_time,
        ),
    )


def build_price_trend_presentation(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> PriceTrendPresentation:
    """把檢查事件整理成價格趨勢圖可直接使用的 presentation。"""
    priced_events = tuple(
        sorted(
            (
                event
                for event in check_events
                if event.normalized_price_amount is not None
            ),
            key=lambda event: event.checked_at,
        )
    )[-20:]
    points = tuple(
        PriceTrendPointPresentation(
            checked_at=event.checked_at,
            checked_at_text=format_datetime_for_display(
                event.checked_at,
                use_24_hour_time=use_24_hour_time,
            ),
            axis_time_text=_format_chart_axis_time(
                event.checked_at,
                use_24_hour_time=use_24_hour_time,
            ),
            price_text=money_text(event.currency, event.normalized_price_amount),
            amount=_priced_event_amount(event),
            currency=event.currency,
        )
        for event in priced_events
    )
    if not points:
        return PriceTrendPresentation(
            points=(),
            latest_price_text="",
            delta_text="",
            range_text="",
        )
    latest_point = points[-1]
    min_price = min(point.amount for point in points)
    max_price = max(point.amount for point in points)
    return PriceTrendPresentation(
        points=points,
        latest_price_text=latest_point.price_text,
        delta_text=_price_delta_text(points[0], latest_point),
        range_text=_price_range_text(
            latest_point.currency,
            min_price=min_price,
            max_price=max_price,
        ),
    )


def build_check_event_row_presentations(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> tuple[CheckEventRowPresentation, ...]:
    """把檢查事件轉成檢查歷史表格列 presentation。"""
    return tuple(
        CheckEventRowPresentation(
            checked_at_text=format_datetime_for_display(
                event.checked_at,
                use_24_hour_time=use_24_hour_time,
            ),
            availability_badge=availability_badge(event.availability),
            event_kind_text=check_event_kinds_text(event.event_kinds),
            price_text=money_text(event.currency, event.normalized_price_amount),
            error_text=error_code_text(event.error_code),
            notification_badge=notification_status_badge(event.notification_status),
        )
        for event in sorted(check_events, key=lambda item: item.checked_at, reverse=True)[
            :20
        ]
    )


def build_runtime_state_event_row_presentations(
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    *,
    use_24_hour_time: bool,
) -> tuple[RuntimeStateEventRowPresentation, ...]:
    """把 runtime 狀態事件轉成表格列 presentation。"""
    return tuple(
        RuntimeStateEventRowPresentation(
            occurred_at_text=format_datetime_for_display(
                event.occurred_at,
                use_24_hour_time=use_24_hour_time,
            ),
            event_kind_text=_describe_runtime_state_event_kind(event.event_kind),
            from_state_text=_describe_optional_runtime_state(event.from_state),
            to_state_text=_describe_optional_runtime_state(event.to_state),
            detail_text=event.detail_text or "無",
        )
        for event in runtime_state_events[:10]
    )


def build_debug_artifact_row_presentations(
    debug_artifacts: tuple[DebugArtifact, ...],
    *,
    use_24_hour_time: bool,
) -> tuple[DebugArtifactRowPresentation, ...]:
    """把 watch 關聯 debug artifact 轉成診斷表格列 presentation。"""
    return tuple(
        DebugArtifactRowPresentation(
            captured_at_text=format_datetime_for_display(
                artifact.captured_at,
                use_24_hour_time=use_24_hour_time,
            ),
            reason_text=_describe_debug_reason(artifact.reason),
            source_url_text=artifact.source_url or "無",
            http_status_text=(
                str(artifact.http_status) if artifact.http_status is not None else "無"
            ),
        )
        for artifact in debug_artifacts[:10]
    )


def _priced_event_amount(event: CheckEvent) -> Decimal:
    """取得已確認存在的價格數值，供趨勢圖計算使用。"""
    if event.normalized_price_amount is None:
        raise ValueError("priced check event must carry normalized_price_amount")
    return event.normalized_price_amount


def _format_chart_axis_time(value: datetime, *, use_24_hour_time: bool) -> str:
    """產生趨勢圖座標軸使用的短時間標籤。"""
    local_value = value.astimezone()
    if use_24_hour_time:
        return f"{local_value.month}/{local_value.day} {local_value:%H:%M}"

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return f"{local_value.month}/{local_value.day} {period_text} {hour:02d}:{local_value:%M}"


def _price_delta_text(
    oldest_point: PriceTrendPointPresentation,
    latest_point: PriceTrendPointPresentation,
) -> str:
    """計算趨勢圖區間內最新價格相對起點的變化文案。"""
    delta = latest_point.amount - oldest_point.amount
    if delta == 0:
        return "持平"
    direction = "下降" if delta < 0 else "上升"
    return f"{direction} {money_text(latest_point.currency, abs(delta))}"


def _price_range_text(
    currency: str,
    *,
    min_price: Decimal,
    max_price: Decimal,
) -> str:
    """產生趨勢圖價格範圍文案，單一價格時避免顯示假範圍。"""
    if min_price == max_price:
        return f"價格：{money_text(currency, min_price)}"
    return f"區間：{money_text(currency, min_price)} - {money_text(currency, max_price)}"


def _describe_debug_reason(reason: str) -> str:
    """把 runtime debug artifact 的原因轉成較易讀的中文。"""
    mapping = {
        "possible_throttling": "可能節流",
        "page_was_discarded": "分頁被瀏覽器暫停",
        "http_403": "站方阻擋",
        "parse_failed": "解析失敗",
        "target_missing": "目標房型方案消失",
        "network_timeout": "網路逾時",
        "network_error": "網路錯誤",
    }
    return mapping.get(reason, reason)


def _describe_runtime_state_event_kind(event_kind: RuntimeStateEventKind) -> str:
    """把 runtime 狀態事件類型轉成較易讀的中文。"""
    mapping = {
        RuntimeStateEventKind.MANUAL_ENABLE: "人工啟用",
        RuntimeStateEventKind.MANUAL_DISABLE: "人工停用",
        RuntimeStateEventKind.MANUAL_PAUSE: "人工暫停",
        RuntimeStateEventKind.MANUAL_RESUME: "人工恢復",
        RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING: "因站方阻擋而暫停",
        RuntimeStateEventKind.PAUSE_DUE_TO_HTTP_403: "因站方阻擋而暫停",
        RuntimeStateEventKind.ENTERED_BACKOFF: "進入退避",
        RuntimeStateEventKind.CLEARED_BACKOFF: "解除退避",
        RuntimeStateEventKind.ENTERED_DEGRADED: "進入降級運作",
        RuntimeStateEventKind.CLEARED_DEGRADED: "解除降級",
        RuntimeStateEventKind.RECOVERED_AFTER_SUCCESS: "成功恢復",
    }
    return mapping[event_kind]


def _describe_optional_runtime_state(state: WatchRuntimeState | None) -> str:
    """把可選 runtime 狀態轉成顯示文字。"""
    if state is None:
        return "無"
    return describe_watch_runtime_state(state)
