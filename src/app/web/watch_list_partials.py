"""watch list / dashboard 專用 partial renderer。"""

from __future__ import annotations

from html import escape
from typing import Iterable

from app.domain.entities import LatestCheckSnapshot, PriceHistoryEntry, WatchItem
from app.web.ui_components import empty_state_card, icon_svg, status_badge, text_link
from app.web.ui_presenters import (
    BadgePresentation,
    WatchActionSurface,
    WatchRowPresentation,
)
from app.web.ui_styles import (
    color_token,
    list_price_style,
    meta_label_style,
    muted_text_style,
    responsive_grid_style,
    stack_style,
    surface_card_style,
    watch_title_style,
)
from app.web.watch_action_partials import render_watch_action_controls
from app.web.watch_list_presenters import (
    DashboardPageViewModel,
    build_dashboard_page_view_model,
)
from app.web.watch_list_runtime_partials import (
    render_runtime_status_section,
    render_runtime_status_section_from_presentation,
    render_runtime_status_section_with_time_format,
)
from app.web.watch_list_summary_partials import (
    render_dashboard_summary_cards,
    render_dashboard_summary_cards_from_presentation,
)

__all__ = [
    "render_dashboard_summary_cards",
    "render_dashboard_summary_cards_from_presentation",
    "render_runtime_status_section",
    "render_runtime_status_section_from_presentation",
    "render_runtime_status_section_with_time_format",
    "render_watch_list_rows",
    "render_watch_list_rows_from_presentation",
]


def render_watch_list_rows(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染首頁 watch card 內容，供首屏與局部更新共用。"""
    view_model = build_dashboard_page_view_model(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        use_24_hour_time=use_24_hour_time,
    )
    return render_watch_list_rows_from_presentation(view_model)


def render_watch_list_rows_from_presentation(
    view_model: DashboardPageViewModel,
) -> str:
    """依 Dashboard view model 渲染 watch 卡片與清單模式。"""
    cards = []
    list_items = []
    for row in view_model.watch_rows:
        actions_html = render_watch_action_controls(
            watch_item_id=row.watch_id,
            runtime_state=row.runtime_state,
            surface=WatchActionSurface.LIST,
        )
        availability_html = _presentation_badge_html(row.availability_badge)
        runtime_badge_html = _presentation_badge_html(row.runtime_state_badge)
        attention_badge_html = _presentation_badge_html(row.attention_badge)
        price_change_badge_html = status_badge(
            label=row.price_change_text,
            kind=row.price_change_kind,
        )
        article_style = surface_card_style(gap="16px", padding="18px")
        card_header_style = (
            "display:flex;justify-content:space-between;gap:16px;"
            "align-items:flex-start;"
        )
        content_grid_style = (
            "display:grid;grid-template-columns:minmax(240px,1.1fr) minmax(320px,1.6fr) "
            "minmax(180px,0.9fr);gap:16px;align-items:stretch;"
        )
        monitoring_panel_style = (
            f"display:grid;gap:10px;padding:14px;background:{color_token('surface_alt')};"
            f"border:1px solid {color_token('border')};border-radius:12px;"
        )
        metric_grid_style = responsive_grid_style(min_width="130px", gap="10px")
        state_panel_style = (
            f"display:grid;gap:10px;padding:14px;border:1px solid {color_token('border')};"
            f"border-radius:12px;background:{color_token('surface')};align-content:start;"
        )
        card_footer_style = (
            "display:flex;justify-content:space-between;gap:14px;align-items:center;"
            "flex-wrap:wrap;"
        )
        cards.append(
            f"""
            <article style="{article_style}">
              <div class="watch-card-header" style="{card_header_style}">
                <div style="{stack_style(gap="xs")}">
                  <h3 style="{watch_title_style()}">
                    {text_link(href=f"/watches/{row.watch_id}", label=row.hotel_name)}
                  </h3>
                </div>
                {attention_badge_html or runtime_badge_html}
              </div>
              <div style="{content_grid_style}">
                <div style="{stack_style(gap="sm")}">
                  <span style="{meta_label_style()}">房間資訊</span>
                  <strong>{escape(row.room_name)}</strong>
                  <span style="{muted_text_style()}">{escape(row.plan_name)}</span>
                  <span style="{muted_text_style()}">{escape(row.date_range_text)}</span>
                  <span style="{muted_text_style()}">{escape(row.occupancy_text)}</span>
                </div>
                <div style="{monitoring_panel_style}">
                  <div>
                    <span style="{meta_label_style()}">目前價格</span>
                    <strong style="{list_price_style()}">{escape(row.current_price_text)}</strong>
                  </div>
                  <div style="{metric_grid_style}">
                    <div>
                      <span style="{meta_label_style()}">空房狀態</span>
                      {availability_html or '<strong>尚未檢查</strong>'}
                    </div>
                    <div>
                      <span style="{meta_label_style()}">價格變動</span>
                      {price_change_badge_html}
                    </div>
                  </div>
                </div>
                <div style="{state_panel_style}">
                  <div>
                    <span style="{meta_label_style()}">監視狀態</span>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                      {runtime_badge_html}
                    </div>
                    {_render_runtime_state_helper_html(row)}
                  </div>
                  <div>
                    <span style="{meta_label_style()}">通知條件</span>
                    <strong>{escape(row.notification_rule_text)}</strong>
                  </div>
                  <span style="{muted_text_style(font_size="13px")}">
                    最後檢查：{_render_last_checked_relative_html(row)}
                  </span>
                </div>
              </div>
              <div class="watch-card-footer" style="{card_footer_style}">
                <span style="{muted_text_style()}">錯誤摘要：{escape(row.error_text)}</span>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                  {text_link(href=f"/watches/{row.watch_id}", label="查看詳情")}
                  {actions_html}
                </div>
              </div>
            </article>
            """
        )
        list_items.append(
            _render_dashboard_list_row(
                row=row,
                actions_html=actions_html,
                availability_html=availability_html,
                runtime_badge_html=runtime_badge_html,
            )
        )
    if cards:
        card_view_html = "\n".join(cards)
        list_view_html = _render_dashboard_list("".join(list_items))
        return f"""
        <div data-watch-list-view="cards">
          {card_view_html}
        </div>
        <div data-watch-list-view="list" style="display:none;">
          {list_view_html}
        </div>
        """
    return empty_state_card(
        title="目前尚無監視項目",
        message="請先從專用 Chrome 分頁建立第一個價格監視。",
    )


def _render_dashboard_list(rows_html: str) -> str:
    """渲染參考圖風格的 dashboard 清單外框與欄位標題。"""
    grid_template = (
        "minmax(240px,1.75fr) minmax(140px,0.85fr) minmax(130px,0.8fr) "
        "minmax(150px,0.9fr) minmax(110px,0.7fr) minmax(120px,0.75fr) "
        "minmax(170px,1fr)"
    )
    header_style = (
        f"display:grid;grid-template-columns:{grid_template};gap:0;"
        f"padding:0 14px;color:{color_token('secondary')};font-weight:800;"
        f"font-size:13px;background:{color_token('primary_faint')};"
        f"border:1px solid {color_token('border')};border-radius:12px 12px 0 0;"
    )
    header_cell_style = (
        f"padding:12px 10px;border-right:1px solid {color_token('border')};"
    )
    return f"""
    <div class="dashboard-watch-list" style="display:grid;gap:8px;">
      <div style="{header_style}">
        <span style="{header_cell_style}">監視</span>
        <span style="{header_cell_style}">價格</span>
        <span style="{header_cell_style}">價格變動</span>
        <span style="{header_cell_style}">通知條件</span>
        <span style="{header_cell_style}">狀態</span>
        <span style="{header_cell_style}">最後檢查</span>
        <span style="padding:12px 10px;">操作</span>
      </div>
      {rows_html}
    </div>
    """


def _render_dashboard_list_row(
    *,
    row: WatchRowPresentation,
    actions_html: str,
    availability_html: str,
    runtime_badge_html: str,
) -> str:
    """渲染 dashboard 折衷清單的一筆 watch row。"""
    grid_template = (
        "minmax(240px,1.75fr) minmax(140px,0.85fr) minmax(130px,0.8fr) "
        "minmax(150px,0.9fr) minmax(110px,0.7fr) minmax(120px,0.75fr) "
        "minmax(170px,1fr)"
    )
    row_style = (
        f"display:grid;grid-template-columns:{grid_template};gap:0;align-items:stretch;"
        f"padding:0 14px;border:1px solid {color_token('border')};"
        f"border-radius:12px;background:{color_token('surface')};"
        f"box-shadow:0 8px 22px {color_token('shadow_soft')};"
    )
    hotel_html = text_link(href=f"/watches/{row.watch_id}", label=row.hotel_name)
    monitor_html = (
        '<div style="display:grid;gap:6px;">'
        f'<strong style="font-size:18px;line-height:1.25;">{hotel_html}</strong>'
        f'<span style="display:block;margin-top:4px;{muted_text_style(font_size="13px")}">'
        f"{escape(row.room_name)}</span>"
        f'<span style="{_dashboard_meta_icon_line_style()}">'
        f'{icon_svg("calendar", size=15)}'
        f"<span>{escape(row.date_range_short_text)}（{escape(row.nights_text)}）</span>"
        "</span>"
        f'<span style="{_dashboard_meta_icon_line_style()}">'
        f'{icon_svg("users", size=15)}'
        f"<span>{escape(row.occupancy_text)}</span>"
        "</span>"
        "</div>"
    )
    price_html = (
        f'<strong style="{list_price_style()}white-space:nowrap;">'
        f"{escape(row.current_price_text)}</strong>"
        f'<div style="margin-top:8px;">{availability_html or "<strong>尚未檢查</strong>"}</div>'
    )
    price_change_color = (
        color_token(f"{row.price_change_kind}_text")
        if row.price_change_kind in {"success", "warning", "danger"}
        else color_token("muted")
    )
    change_html = (
        f'<strong style="color:{price_change_color};">'
        f"{escape(row.price_change_text)}</strong>"
        f'<span style="display:block;margin-top:6px;{muted_text_style(font_size="12px")}">'
        f"{escape(row.price_change_helper_text)}</span>"
    )
    notification_html = (
        f'<strong>{escape(row.notification_rule_text)}</strong>'
    )
    runtime_state_html = runtime_badge_html + _render_runtime_state_helper_html(row)
    last_checked_html = (
        _render_last_checked_relative_html(row)
        + (
        f'<span style="display:block;margin-top:6px;{muted_text_style(font_size="12px")}">'
        f"{escape(row.last_checked_short_text)}</span>"
        )
    )
    actions_cell_html = (
        f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:nowrap;">'
        f"{actions_html}</div>"
    )
    return f"""
    <article style="{row_style}">
      {_render_dashboard_list_cell(monitor_html)}
      {_render_dashboard_list_cell(price_html)}
      {_render_dashboard_list_cell(change_html)}
      {_render_dashboard_list_cell(notification_html)}
      {_render_dashboard_list_cell(runtime_state_html)}
      {_render_dashboard_list_cell(last_checked_html)}
      {_render_dashboard_list_cell(actions_cell_html, last=True)}
    </article>
    """


def _render_dashboard_list_cell(content: str, *, last: bool = False) -> str:
    """渲染 dashboard list row 的單一欄位，集中欄間分隔樣式。"""
    border_style = "" if last else f"border-right:1px solid {color_token('border')};"
    return (
        '<div style="display:flex;flex-direction:column;justify-content:center;'
        f'padding:14px 10px;min-width:0;{border_style}">{content}</div>'
    )


def _render_last_checked_relative_html(row: WatchRowPresentation) -> str:
    """渲染可由前端自行更新的最後檢查相對時間。"""
    timestamp_attr = (
        f' data-relative-time="{escape(row.last_checked_at_iso)}"'
        if row.last_checked_at_iso is not None
        else ""
    )
    return (
        f'<strong{timestamp_attr} style="white-space:nowrap;">'
        f"{escape(row.last_checked_relative_text)}</strong>"
    )


def _render_runtime_state_helper_html(row: WatchRowPresentation) -> str:
    """渲染狀態輔助文字；退避倒數可由前端自行更新。"""
    if not row.runtime_state_helper_text:
        return ""
    countdown_attr = (
        f' data-countdown-time="{escape(row.runtime_state_helper_target_iso)}"'
        if row.runtime_state_helper_target_iso is not None
        else ""
    )
    return (
        f'<span{countdown_attr} style="display:block;margin-top:6px;'
        f'{muted_text_style(font_size="12px")}">'
        f"{escape(row.runtime_state_helper_text)}</span>"
    )


def _dashboard_meta_icon_line_style() -> str:
    """回傳 dashboard 第一欄 icon + meta 文字列樣式。"""
    return (
        "display:flex;align-items:center;gap:7px;margin-top:4px;"
        f"{muted_text_style(font_size='13px')}"
    )


def _presentation_badge_html(presentation: BadgePresentation | None) -> str:
    """把 presenter badge 轉成共用 badge HTML，允許缺值。"""
    if presentation is None:
        return ""
    return status_badge(label=presentation.label, kind=presentation.kind)

