"""Dashboard watch card mode renderer。"""

from __future__ import annotations

from html import escape

from app.web.ui_components import status_badge, text_link
from app.web.ui_page_sections import cluster_style
from app.web.ui_presenters import WatchRowPresentation
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
from app.web.watch_list_row_helpers import (
    render_last_checked_relative_html,
    render_runtime_state_helper_html,
)


def render_watch_card(
    *,
    row: WatchRowPresentation,
    actions_html: str,
    availability_html: str,
    runtime_badge_html: str,
    attention_badge_html: str,
) -> str:
    """渲染 Dashboard 卡片模式的一筆 watch。"""
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
    return f"""
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
            <div style="{cluster_style(gap="sm")}">
              {runtime_badge_html}
            </div>
            {render_runtime_state_helper_html(row)}
          </div>
          <div>
            <span style="{meta_label_style()}">通知條件</span>
            <strong>{escape(row.notification_rule_text)}</strong>
          </div>
          <span style="{muted_text_style(font_size="13px")}">
            最後檢查：{render_last_checked_relative_html(row)}
          </span>
        </div>
      </div>
      <div class="watch-card-footer" style="{card_footer_style}">
        <span style="{muted_text_style()}">錯誤摘要：{escape(row.error_text)}</span>
        <div style="{cluster_style(gap="sm")}">
          {text_link(href=f"/watches/{row.watch_id}", label="查看詳情")}
          {actions_html}
        </div>
      </div>
    </article>
    """
