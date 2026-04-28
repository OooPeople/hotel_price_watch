"""Dashboard summary card partial renderer。"""

from __future__ import annotations

from html import escape
from typing import Iterable

from app.domain.entities import LatestCheckSnapshot, PriceHistoryEntry, WatchItem
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import icon_svg
from app.web.ui_styles import color_token, muted_text_style, responsive_grid_style
from app.web.watch_list_presenters import (
    DashboardMetricPresentation,
    build_dashboard_page_view_model,
)


def render_dashboard_summary_cards(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    today_notification_count: int = 0,
    runtime_status: MonitorRuntimeStatus | None = None,
    use_24_hour_time: bool,
) -> str:
    """渲染首頁摘要卡片，讓首屏先呈現產品資訊而非 runtime 細節。"""
    view_model = build_dashboard_page_view_model(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        today_notification_count=today_notification_count,
        runtime_status=runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    return render_dashboard_summary_cards_from_presentation(view_model.summary_cards)


def render_dashboard_summary_cards_from_presentation(
    summary_cards: tuple[DashboardMetricPresentation, ...],
) -> str:
    """依首頁 summary presentation 渲染摘要卡片。"""
    cards_html = "".join(_dashboard_metric_card(card) for card in summary_cards)
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {cards_html}
    </section>
    """


def _dashboard_metric_card(
    presentation: DashboardMetricPresentation,
) -> str:
    """渲染 Dashboard 參考圖風格的彩色 icon 摘要卡。"""
    icon_style = _dashboard_metric_icon_style(presentation.icon_kind)
    return f"""
    <section
      style="
        display:grid;grid-template-columns:auto minmax(0,1fr);gap:16px;align-items:center;
        padding:20px;border:1px solid {color_token("border")};
        border-radius:12px;background:{color_token("surface")};
        box-shadow:0 10px 28px {color_token("shadow_soft")};
      "
    >
      <span aria-hidden="true" style="{icon_style}">
        {icon_svg(presentation.icon_name, size=30)}
      </span>
      <span style="display:grid;gap:4px;min-width:0;">
        <span style="{muted_text_style(font_size="14px")}">{escape(presentation.label)}</span>
        <strong style="font-size:30px;line-height:1;color:{color_token("primary")};">
          {escape(presentation.value)}
        </strong>
        <span style="{muted_text_style(font_size="13px")}">{escape(presentation.helper_text)}</span>
      </span>
    </section>
    """


def _dashboard_metric_icon_style(kind: str) -> str:
    """依 summary card 語意回傳 icon 方塊樣式。"""
    palettes = {
        "success": ("#e8f7ef", "#15935f"),
        "warning": ("#fff3d8", "#d97706"),
        "info": ("#e8f2ff", "#2563eb"),
    }
    background, color = palettes.get(kind, palettes["success"])
    return (
        "width:72px;height:72px;display:grid;place-items:center;border-radius:10px;"
        f"background:{background};color:{color};"
    )
