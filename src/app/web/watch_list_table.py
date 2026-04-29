"""Dashboard watch list mode renderer。"""

from __future__ import annotations

from html import escape

from app.web.ui_components import icon_svg, text_link
from app.web.ui_page_sections import (
    block_nowrap_style,
    cluster_style,
    stack_block_style,
    table_action_cell_style,
)
from app.web.ui_presenters import WatchRowPresentation
from app.web.ui_styles import (
    color_token,
    list_price_style,
    muted_text_style,
)
from app.web.watch_list_row_helpers import (
    render_last_checked_relative_html,
    render_runtime_state_helper_html,
)


def render_dashboard_list(rows_html: str) -> str:
    """渲染參考圖風格的 dashboard 清單外框與欄位標題。"""
    header_style = (
        f"display:grid;grid-template-columns:{_dashboard_grid_template()};gap:0;"
        f"padding:0 14px;color:{color_token('secondary')};font-weight:800;"
        f"font-size:13px;background:{color_token('primary_faint')};"
        f"border:1px solid {color_token('border')};border-radius:12px 12px 0 0;"
    )
    header_cell_style = (
        f"padding:12px 10px;border-right:1px solid {color_token('border')};"
    )
    return f"""
    <div class="dashboard-watch-list" style="{stack_block_style(gap="sm")}">
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


def render_dashboard_list_row(
    *,
    row: WatchRowPresentation,
    actions_html: str,
    availability_html: str,
    runtime_badge_html: str,
) -> str:
    """渲染 dashboard 折衷清單的一筆 watch row。"""
    row_style = (
        f"display:grid;grid-template-columns:{_dashboard_grid_template()};"
        f"gap:0;align-items:stretch;padding:0 14px;"
        f"border:1px solid {color_token('border')};"
        f"border-radius:12px;background:{color_token('surface')};"
        f"box-shadow:0 8px 22px {color_token('shadow_soft')};"
    )
    return f"""
    <article style="{row_style}">
      {_render_dashboard_list_cell(_render_monitor_cell(row))}
      {_render_dashboard_list_cell(_render_price_cell(row, availability_html))}
      {_render_dashboard_list_cell(_render_change_cell(row))}
      {_render_dashboard_list_cell(_render_notification_cell(row))}
      {_render_dashboard_list_cell(runtime_badge_html + render_runtime_state_helper_html(row))}
      {_render_dashboard_list_cell(_render_last_checked_cell(row))}
      {_render_dashboard_list_cell(_render_actions_cell(actions_html), last=True)}
    </article>
    """


def _dashboard_grid_template() -> str:
    """回傳 Dashboard list mode 共用欄位比例。"""
    return (
        "minmax(240px,1.75fr) minmax(140px,0.85fr) minmax(130px,0.8fr) "
        "minmax(150px,0.9fr) minmax(110px,0.7fr) minmax(120px,0.75fr) "
        "minmax(170px,1fr)"
    )


def _render_monitor_cell(row: WatchRowPresentation) -> str:
    """渲染 Dashboard list 的監視資訊欄位。"""
    hotel_html = text_link(href=f"/watches/{row.watch_id}", label=row.hotel_name)
    return (
        f'<div style="{stack_block_style(gap="xs")}">'
        f'<strong style="font-size:18px;line-height:1.25;">{hotel_html}</strong>'
        f'<span style="{block_nowrap_style(muted_text_style(font_size="13px"))}">'
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


def _render_price_cell(row: WatchRowPresentation, availability_html: str) -> str:
    """渲染 Dashboard list 的價格欄位。"""
    return (
        f'<strong style="{block_nowrap_style(list_price_style())}">'
        f"{escape(row.current_price_text)}</strong>"
        f'<div style="{stack_block_style(gap="sm")}">'
        f'{availability_html or "<strong>尚未檢查</strong>"}</div>'
    )


def _render_change_cell(row: WatchRowPresentation) -> str:
    """渲染 Dashboard list 的價格變動欄位。"""
    price_change_color = (
        color_token(f"{row.price_change_kind}_text")
        if row.price_change_kind in {"success", "warning", "danger"}
        else color_token("muted")
    )
    return (
        f'<strong style="color:{price_change_color};">'
        f"{escape(row.price_change_text)}</strong>"
        f'<span style="{block_nowrap_style(muted_text_style(font_size="12px"))}">'
        f"{escape(row.price_change_helper_text)}</span>"
    )


def _render_notification_cell(row: WatchRowPresentation) -> str:
    """渲染 Dashboard list 的通知條件欄位。"""
    return f"<strong>{escape(row.notification_rule_text)}</strong>"


def _render_last_checked_cell(row: WatchRowPresentation) -> str:
    """渲染 Dashboard list 的最後檢查欄位。"""
    return (
        render_last_checked_relative_html(row)
        + f'<span style="{block_nowrap_style(muted_text_style(font_size="12px"))}">'
        f"{escape(row.last_checked_short_text)}</span>"
    )


def _render_actions_cell(actions_html: str) -> str:
    """渲染 Dashboard list 的操作欄位。"""
    return f'<div style="{cluster_style(gap="sm", wrap=False)}">{actions_html}</div>'


def _render_dashboard_list_cell(content: str, *, last: bool = False) -> str:
    """渲染 dashboard list row 的單一欄位，集中欄間分隔樣式。"""
    border_style = "" if last else f"border-right:1px solid {color_token('border')};"
    return (
        f'<div style="{table_action_cell_style()}padding:14px 10px;'
        f'min-width:0;{border_style}">{content}</div>'
    )


def _dashboard_meta_icon_line_style() -> str:
    """回傳 dashboard 第一欄 icon + meta 文字列樣式。"""
    return cluster_style(gap="sm", wrap=False) + muted_text_style(font_size="13px")
