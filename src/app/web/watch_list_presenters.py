"""Dashboard / watch list 頁面的 page-level presentation model。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.domain.entities import LatestCheckSnapshot, PriceHistoryEntry, WatchItem
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_presenters import (
    WatchRowPresentation,
    build_watch_row_presentation,
    price_history_changed,
    price_history_increased,
)
from app.web.view_formatters import format_datetime_for_display


@dataclass(frozen=True, slots=True)
class DashboardMetricPresentation:
    """描述首頁摘要卡需要的顯示資料與 icon 語意。"""

    label: str
    value: str
    helper_text: str
    icon_name: str
    icon_kind: str


@dataclass(frozen=True, slots=True)
class RuntimeStatusItemPresentation:
    """描述系統狀態列中的單一狀態項目。"""

    icon_name: str
    icon_kind: str
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class RuntimeStatusActionPresentation:
    """描述系統狀態列右側操作連結。"""

    href: str
    label: str
    title: str


@dataclass(frozen=True, slots=True)
class RuntimeStatusPresentation:
    """集中首頁系統狀態列的可見文案與狀態語意。"""

    items: tuple[RuntimeStatusItemPresentation, ...]
    action: RuntimeStatusActionPresentation


@dataclass(frozen=True, slots=True)
class DashboardPageViewModel:
    """集中 Dashboard 首頁摘要卡、watch rows 與 runtime dock 的資料。"""

    summary_cards: tuple[DashboardMetricPresentation, ...]
    watch_rows: tuple[WatchRowPresentation, ...]
    runtime_status: RuntimeStatusPresentation | None


def build_dashboard_page_view_model(
    *,
    watch_items: Iterable[WatchItem],
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]]
    | None = None,
    today_notification_count: int = 0,
    runtime_status: MonitorRuntimeStatus | None = None,
    use_24_hour_time: bool,
) -> DashboardPageViewModel:
    """把 Dashboard 所需資料整理成 renderer 可直接使用的 view model。"""
    watch_items_tuple = tuple(watch_items)
    latest_snapshots_by_watch_id = latest_snapshots_by_watch_id or {}
    recent_price_history_by_watch_id = recent_price_history_by_watch_id or {}
    watch_rows = tuple(
        sorted(
            (
                build_watch_row_presentation(
                    watch_item=watch_item,
                    latest_snapshot=latest_snapshots_by_watch_id.get(watch_item.id),
                    recent_price_history=recent_price_history_by_watch_id.get(
                        watch_item.id,
                        (),
                    ),
                    use_24_hour_time=use_24_hour_time,
                )
                for watch_item in watch_items_tuple
            ),
            key=lambda row: row.sort_key,
        )
    )
    return DashboardPageViewModel(
        summary_cards=_build_dashboard_summary_cards(
            watch_items=watch_items_tuple,
            latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=recent_price_history_by_watch_id,
            today_notification_count=today_notification_count,
            runtime_status=runtime_status,
        ),
        watch_rows=watch_rows,
        runtime_status=build_runtime_status_presentation(
            runtime_status,
            use_24_hour_time=use_24_hour_time,
        ),
    )


def build_runtime_status_presentation(
    runtime_status: MonitorRuntimeStatus | None,
    *,
    use_24_hour_time: bool,
) -> RuntimeStatusPresentation | None:
    """把 runtime status 轉成首頁系統狀態列使用的 presentation model。"""
    if runtime_status is None:
        return None

    running_text = "運作正常" if runtime_status.is_running else "未啟動"
    chrome_text = "已連線" if runtime_status.chrome_debuggable else "未連線"
    last_tick_text = format_datetime_for_display(
        runtime_status.last_tick_at,
        use_24_hour_time=use_24_hour_time,
    )
    last_sync_text = format_datetime_for_display(
        runtime_status.last_watch_sync_at,
        use_24_hour_time=use_24_hour_time,
    )
    runtime_details = (
        f"已啟用監視：{runtime_status.enabled_watch_count}；"
        f"目前檢查中：{runtime_status.inflight_watch_count}；"
        f"最後 tick：{last_tick_text}"
    )
    return RuntimeStatusPresentation(
        items=(
            RuntimeStatusItemPresentation(
                icon_name="check-circle",
                icon_kind="success" if runtime_status.is_running else "warning",
                label="背景監視器",
                value=running_text,
            ),
            RuntimeStatusItemPresentation(
                icon_name="chrome",
                icon_kind="success" if runtime_status.chrome_debuggable else "warning",
                label="專用 Chrome",
                value=chrome_text,
            ),
            RuntimeStatusItemPresentation(
                icon_name="clock",
                icon_kind="success",
                label="最後同步時間",
                value=last_sync_text,
            ),
        ),
        action=RuntimeStatusActionPresentation(
            href="/debug/captures",
            label="查看詳細狀態",
            title=runtime_details,
        ),
    )


def _build_dashboard_summary_cards(
    *,
    watch_items: tuple[WatchItem, ...],
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None],
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]],
    today_notification_count: int,
    runtime_status: MonitorRuntimeStatus | None,
) -> tuple[DashboardMetricPresentation, ...]:
    """集中首頁摘要卡的計數與輔助文案，避免 renderer 自行推導。"""
    attention_count = sum(
        1
        for watch_item in watch_items
        if _watch_needs_attention(latest_snapshots_by_watch_id.get(watch_item.id))
        or price_history_increased(recent_price_history_by_watch_id.get(watch_item.id, ()))
    )
    changed_count = sum(
        1
        for watch_item in watch_items
        if price_history_changed(recent_price_history_by_watch_id.get(watch_item.id, ()))
    )
    active_count = (
        runtime_status.enabled_watch_count
        if runtime_status is not None
        else sum(1 for watch_item in watch_items if watch_item.enabled)
    )
    return (
        DashboardMetricPresentation(
            label="啟用中的監視",
            value=str(active_count),
            helper_text=f"共 {len(watch_items)} 個監視",
            icon_name="trend-up",
            icon_kind="success",
        ),
        DashboardMetricPresentation(
            label="需要注意",
            value=str(attention_count),
            helper_text="異常、退避或價格上漲",
            icon_name="alert-circle",
            icon_kind="warning",
        ),
        DashboardMetricPresentation(
            label="最近有變動",
            value=str(changed_count),
            helper_text="過去 24 小時內",
            icon_name="arrow-up-down",
            icon_kind="info",
        ),
        DashboardMetricPresentation(
            label="今日通知",
            value=str(today_notification_count),
            helper_text=f"{today_notification_count} 封新通知",
            icon_name="bell",
            icon_kind="success",
        ),
    )


def _watch_needs_attention(snapshot: LatestCheckSnapshot | None) -> bool:
    """判斷首頁摘要是否應把 watch 計入需注意項目。"""
    if snapshot is None:
        return False
    return bool(snapshot.last_error_code or snapshot.is_degraded)
