"""watch list / detail 頁面可替換區塊的 HTML partial renderer。"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Iterable

from app.domain import derive_watch_runtime_state, describe_watch_runtime_state
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    PriceHistoryEntry,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import RuntimeStateEventKind, WatchRuntimeState
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import (
    action_row,
    card,
    data_table,
    empty_state_card,
    icon_svg,
    key_value_grid,
    status_badge,
    submit_button,
    summary_card,
    table_row,
    text_link,
)
from app.web.ui_presenters import (
    BadgePresentation,
    WatchActionPresentation,
    WatchActionSurface,
    WatchRowPresentation,
    availability_badge,
    build_watch_action_presentations,
    build_watch_row_presentation,
    check_event_kinds_text,
    error_code_text,
    money_text,
    notification_rule_text,
    notification_status_badge,
    price_history_changed,
    price_history_increased,
    runtime_state_badge,
)
from app.web.ui_styles import (
    color_token,
    hero_title_style,
    list_price_style,
    meta_label_style,
    meta_paragraph_style,
    muted_text_style,
    responsive_grid_style,
    stack_style,
    surface_card_style,
    watch_title_style,
)
from app.web.view_formatters import (
    format_datetime_for_display,
    format_datetime_lines_for_display,
)

PRICE_CHART_LEFT = 76
PRICE_CHART_TOP = 34
PRICE_CHART_WIDTH = 532
PRICE_CHART_HEIGHT = 100
PRICE_CHART_BOTTOM = PRICE_CHART_TOP + PRICE_CHART_HEIGHT


def render_runtime_status_section(runtime_status: MonitorRuntimeStatus | None) -> str:
    """在首頁顯示 background monitor runtime 的狀態摘要。"""
    return render_runtime_status_section_with_time_format(
        runtime_status,
        use_24_hour_time=True,
    )


def render_runtime_status_section_with_time_format(
    runtime_status: MonitorRuntimeStatus | None,
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染 background monitor runtime 的狀態摘要。"""
    if runtime_status is None:
        return ""

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
    runtime_kind = "success" if runtime_status.is_running else "warning"
    chrome_kind = "success" if runtime_status.chrome_debuggable else "warning"
    runtime_details = (
        f"已啟用監視：{runtime_status.enabled_watch_count}；"
        f"目前檢查中：{runtime_status.inflight_watch_count}；"
        f"最後 tick：{last_tick_text}"
    )
    return f"""
    <section
      class="runtime-status-dock"
      data-runtime-status-dock
      style="{surface_card_style(gap="0", padding="0")}"
    >
      <div
        class="runtime-status-header"
        style="
          display:flex;align-items:center;justify-content:space-between;gap:12px;
          padding:14px 18px;border-bottom:1px solid {color_token("border")};
        "
      >
        <h2 style="margin:0;font-size:18px;">系統狀態</h2>
        <button
          type="button"
          data-runtime-status-toggle
          aria-label="收合系統狀態"
          aria-expanded="true"
          style="
            width:28px;height:28px;display:grid;place-items:center;padding:0;
            border:1px solid {color_token("border")};border-radius:999px;
            background:{color_token("surface")};color:{color_token("secondary")};
            cursor:pointer;font-weight:800;line-height:1;
          "
        >
          <span data-runtime-expanded-icon>{icon_svg("chevron-down", size=16)}</span>
          <span data-runtime-collapsed-icon style="display:none;">
            {icon_svg("chevron-up", size=16)}
          </span>
        </button>
      </div>
      <div
        class="runtime-status-panel"
        style="
          display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;
          align-items:center;padding:16px 18px;
        "
      >
        {_render_runtime_status_item(
            icon_name="check-circle",
            icon_kind=runtime_kind,
            label="背景監視器",
            value=running_text,
        )}
        {_render_runtime_status_item(
            icon_name="chrome",
            icon_kind=chrome_kind,
            label="專用 Chrome",
            value=chrome_text,
        )}
        {_render_runtime_status_item(
            icon_name="clock",
            icon_kind="success",
            label="最後同步時間",
            value=last_sync_text,
        )}
        <div style="display:flex;justify-content:flex-end;">
          <a
            href="/debug/captures"
            title="{escape(runtime_details)}"
            style="
              display:inline-flex;align-items:center;gap:8px;padding:10px 14px;
              border:1px solid {color_token("border")};border-radius:8px;
              color:{color_token("primary")};text-decoration:none;font-weight:700;
              background:{color_token("surface")};
            "
          >
            查看詳細狀態 <span aria-hidden="true">›</span>
          </a>
        </div>
      </div>
    </section>
    """


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
    watch_items_tuple = tuple(watch_items)
    latest_snapshots_by_watch_id = latest_snapshots_by_watch_id or {}
    recent_price_history_by_watch_id = recent_price_history_by_watch_id or {}
    attention_count = sum(
        1
        for watch_item in watch_items_tuple
        if _watch_needs_attention(latest_snapshots_by_watch_id.get(watch_item.id))
        or price_history_increased(recent_price_history_by_watch_id.get(watch_item.id, ()))
    )
    changed_count = sum(
        1
        for watch_item in watch_items_tuple
        if price_history_changed(recent_price_history_by_watch_id.get(watch_item.id, ()))
    )
    active_count = (
        runtime_status.enabled_watch_count
        if runtime_status is not None
        else sum(1 for watch_item in watch_items_tuple if watch_item.enabled)
    )
    cards_html = "".join(
        (
            _dashboard_metric_card(
                label="啟用中的監視",
                value=str(active_count),
                helper_text=f"共 {len(watch_items_tuple)} 個監視",
                icon_name="trend-up",
                icon_kind="success",
            ),
            _dashboard_metric_card(
                label="需要注意",
                value=str(attention_count),
                helper_text="異常、退避或價格上漲",
                icon_name="alert-circle",
                icon_kind="warning",
            ),
            _dashboard_metric_card(
                label="最近有變動",
                value=str(changed_count),
                helper_text="過去 24 小時內",
                icon_name="arrow-up-down",
                icon_kind="info",
            ),
            _dashboard_metric_card(
                label="今日通知",
                value=str(today_notification_count),
                helper_text=f"{today_notification_count} 封新通知",
                icon_name="bell",
                icon_kind="success",
            ),
        )
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {cards_html}
    </section>
    """


def _dashboard_metric_card(
    *,
    label: str,
    value: str,
    helper_text: str,
    icon_name: str,
    icon_kind: str,
) -> str:
    """渲染 Dashboard 參考圖風格的彩色 icon 摘要卡。"""
    icon_style = _dashboard_metric_icon_style(icon_kind)
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
        {icon_svg(icon_name, size=30)}
      </span>
      <span style="display:grid;gap:4px;min-width:0;">
        <span style="{muted_text_style(font_size="14px")}">{escape(label)}</span>
        <strong style="font-size:30px;line-height:1;color:{color_token("primary")};">
          {escape(value)}
        </strong>
        <span style="{muted_text_style(font_size="13px")}">{escape(helper_text)}</span>
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


def _render_runtime_status_item(
    *,
    icon_name: str,
    icon_kind: str,
    label: str,
    value: str,
) -> str:
    """渲染系統狀態橫向列的單一狀態項目。"""
    return f"""
    <div
      style="
        display:flex;align-items:center;gap:12px;min-width:0;
        padding:4px 18px 4px 0;border-right:1px solid {color_token("border")};
      "
    >
      <span aria-hidden="true" style="{_runtime_status_icon_style(icon_kind)}">
        {icon_svg(icon_name, size=24)}
      </span>
      <span style="display:grid;gap:2px;min-width:0;">
        <span style="{muted_text_style(font_size="13px")}">{escape(label)}</span>
        <strong style="font-size:15px;color:{color_token("secondary")};">
          {escape(value)}
        </strong>
      </span>
    </div>
    """


def _runtime_status_icon_style(kind: str) -> str:
    """依 runtime 狀態語意回傳圓形 icon 樣式。"""
    palettes = {
        "success": ("#e8f7ef", "#15935f"),
        "warning": ("#fff3d8", "#d97706"),
    }
    background, color = palettes.get(kind, palettes["success"])
    return (
        "width:42px;height:42px;display:grid;place-items:center;border-radius:999px;"
        f"background:{background};color:{color};"
    )


def render_watch_list_rows(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染首頁 watch card 內容，供首屏與局部更新共用。"""
    cards = []
    list_items = []
    latest_snapshots_by_watch_id = latest_snapshots_by_watch_id or {}
    recent_price_history_by_watch_id = recent_price_history_by_watch_id or {}
    row_presentations = sorted(
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
            for watch_item in watch_items
        ),
        key=lambda row: row.sort_key,
    )
    watch_items_by_id = {watch_item.id: watch_item for watch_item in watch_items}
    for row in row_presentations:
        watch_item = watch_items_by_id[row.watch_id]
        runtime_state = derive_watch_runtime_state(
            watch_item=watch_item,
            latest_snapshot=latest_snapshots_by_watch_id.get(watch_item.id),
        )
        actions_html = render_watch_action_controls(
            watch_item=watch_item,
            runtime_state=runtime_state,
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


def render_watch_detail_hero_section(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    use_24_hour_time: bool,
) -> str:
    """渲染 watch 詳細頁的 hero summary，讓價格與狀態成為首屏主角。"""
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    runtime_presentation = runtime_state_badge(runtime_state)
    date_range = (
        f"{watch_item.target.check_in_date.isoformat()} - "
        f"{watch_item.target.check_out_date.isoformat()}"
    )
    last_checked_text, last_checked_html = _format_datetime_summary_value(
        latest_snapshot.checked_at if latest_snapshot is not None else None,
        empty_text="尚未檢查",
        use_24_hour_time=use_24_hour_time,
    )
    runtime_badge_html = status_badge(
        label=runtime_presentation.label,
        kind=runtime_presentation.kind,
    )
    occupancy_text = _format_occupancy_text(watch_item)
    return card(
        body=f"""
        <div class="watch-detail-hero" style="display:grid;gap:10px;">
          <div style="display:grid;gap:8px;min-width:260px;">
            <div>{runtime_badge_html}</div>
            <h2 style="{hero_title_style()}">{escape(watch_item.hotel_name)}</h2>
            <p style="{meta_paragraph_style()}">{escape(watch_item.room_name)}</p>
          </div>
        </div>
        {key_value_grid((
            ("日期", escape(date_range)),
            ("人數 / 房數", occupancy_text),
            ("最後檢查", last_checked_html or escape(last_checked_text)),
        ))}
        """,
    )


def render_watch_price_summary_cards(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    notification_state: NotificationState | None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染 watch 詳細頁的價格與通知摘要卡片。"""
    current_price = (
        money_text(
            latest_snapshot.currency,
            latest_snapshot.normalized_price_amount,
        )
        if latest_snapshot is not None
        else "尚未檢查"
    )
    availability_text = (
        availability_badge(latest_snapshot.availability).label
        if latest_snapshot is not None
        else "尚未檢查"
    )
    last_notified_text, last_notified_html = _format_datetime_summary_value(
        notification_state.last_notified_at
        if notification_state is not None
        else None,
        empty_text="尚未通知",
        use_24_hour_time=use_24_hour_time,
    )
    cards_html = "".join(
        (
            summary_card(
                label="目前價格",
                value=current_price,
                helper_text="最近一次解析結果",
            ),
            summary_card(
                label="空房狀態",
                value=availability_text,
                helper_text="最近一次檢查結果",
            ),
            summary_card(
                label="通知條件",
                value=notification_rule_text(watch_item),
                helper_text="可在通知設定中調整",
            ),
            summary_card(
                label="最近通知",
                value=last_notified_text,
                value_html=last_notified_html,
                helper_text="尚未觸發時不會通知",
            ),
        )
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {cards_html}
    </section>
    """


def render_price_trend_section_with_time_format(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """渲染 watch 詳細頁的輕量價格趨勢，不引入外部 chart library。"""
    priced_events = _priced_check_events(check_events)
    if not priced_events:
        return empty_state_card(
            title="價格趨勢",
            message="目前尚無可繪製趨勢的價格紀錄。",
        )

    if len(priced_events) == 1:
        only_event = priced_events[0]
        only_price = money_text(only_event.currency, only_event.normalized_price_amount)
        only_time = format_datetime_for_display(
            only_event.checked_at,
            use_24_hour_time=use_24_hour_time,
        )
        return card(
            title="價格趨勢",
            body=f"""
            <p style="{meta_paragraph_style()}">
              目前只有一筆有效價格，累積更多檢查後會顯示趨勢線。
            </p>
            <p><strong>{escape(only_price)}</strong>（{escape(only_time)}）</p>
            """,
        )

    chart_events = priced_events[-20:]
    points = _price_chart_points(chart_events)
    oldest_event = chart_events[0]
    latest_event = chart_events[-1]
    oldest_price = money_text(oldest_event.currency, oldest_event.normalized_price_amount)
    latest_price = money_text(latest_event.currency, latest_event.normalized_price_amount)
    min_price = min(_price_amount(event) for event in chart_events)
    max_price = max(_price_amount(event) for event in chart_events)
    point_markers = _price_chart_markers(
        chart_events,
        points,
        use_24_hour_time=use_24_hour_time,
    )
    chart_axes = _price_chart_axes(
        chart_events,
        min_price=min_price,
        max_price=max_price,
        use_24_hour_time=use_24_hour_time,
    )
    delta_text = _price_delta_text(oldest_event, latest_event)
    chart_style = (
        f"width:100%;height:auto;border:1px solid {color_token('border')};"
        f"background:{color_token('surface_alt')};border-radius:12px;"
    )
    range_text = _price_range_text(
        latest_event.currency,
        min_price=min_price,
        max_price=max_price,
    )
    return card(
        title="價格趨勢",
        body=f"""
        <div style="{responsive_grid_style(min_width="180px", gap="12px")}">
          <div>
            <span style="{meta_label_style()}">最新價格</span>
            <strong>{escape(latest_price)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">本圖變化</span>
            <strong>{escape(delta_text)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">圖表範圍</span>
            <strong>{len(chart_events)} 筆有效價格</strong>
          </div>
        </div>
        <svg viewBox="0 0 640 190" role="img" aria-label="價格趨勢圖" style="{chart_style}">
          {chart_axes}
          <polyline
            fill="none"
            stroke="{color_token('primary')}"
            stroke-width="4"
            stroke-linecap="round"
            stroke-linejoin="round"
            points="{escape(points)}"
          />
          {point_markers}
        </svg>
        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;">
          <span style="{muted_text_style()}">
            起點：{escape(oldest_price)}
            （{escape(format_datetime_for_display(
                oldest_event.checked_at,
                use_24_hour_time=use_24_hour_time,
            ))}）
          </span>
          <span style="{muted_text_style()}">
            {escape(range_text)}
          </span>
        </div>
        """,
    )


def render_check_events_section(check_events: tuple[CheckEvent, ...]) -> str:
    """渲染檢查歷史與錯誤摘要。"""
    return render_check_events_section_with_time_format(
        check_events,
        use_24_hour_time=True,
    )


def render_check_events_section_with_time_format(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染檢查歷史與錯誤摘要。"""
    if not check_events:
        return empty_state_card(title="檢查歷史", message="目前尚無檢查歷史。")

    rows = []
    for event in sorted(check_events, key=lambda item: item.checked_at, reverse=True)[:20]:
        event_kind_text = check_event_kinds_text(event.event_kinds)
        event_price_text = money_text(
            event.currency,
            event.normalized_price_amount,
        )
        availability_presentation = availability_badge(event.availability)
        notification_presentation = notification_status_badge(event.notification_status)
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            event.checked_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    status_badge(
                        label=availability_presentation.label,
                        kind=availability_presentation.kind,
                    ),
                    escape(event_kind_text),
                    escape(event_price_text),
                    escape(error_code_text(event.error_code)),
                    status_badge(
                        label=notification_presentation.label,
                        kind=notification_presentation.kind,
                    ),
                )
            )
        )

    return card(
        title="檢查歷史",
        body=data_table(
            headers=("時間", "空房狀態", "事件", "價格", "錯誤摘要", "通知結果"),
            rows_html="".join(rows),
        ),
    )


def render_runtime_state_events_section(
    runtime_state_events: tuple[RuntimeStateEvent, ...],
) -> str:
    """渲染 watch 狀態轉移事件摘要，避免只靠檢查事件推論狀態變化。"""
    return render_runtime_state_events_section_with_time_format(
        runtime_state_events,
        use_24_hour_time=True,
    )


def render_runtime_state_events_section_with_time_format(
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染 watch 狀態轉移事件摘要。"""
    if not runtime_state_events:
        return empty_state_card(
            title="狀態事件",
            message="目前尚無暫停、恢復或阻擋相關狀態事件。",
        )

    rows = []
    for event in runtime_state_events[:10]:
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            event.occurred_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    escape(_describe_runtime_state_event_kind(event.event_kind)),
                    escape(_describe_optional_runtime_state(event.from_state)),
                    escape(_describe_optional_runtime_state(event.to_state)),
                    escape(event.detail_text or "無"),
                )
            )
        )
    return card(
        title="狀態事件",
        body=data_table(
            headers=("時間", "事件", "前狀態", "後狀態", "說明"),
            rows_html="".join(rows),
        ),
    )


def render_debug_artifacts_section(debug_artifacts: tuple[DebugArtifact, ...]) -> str:
    """渲染與單一 watch item 關聯的診斷檔案摘要。"""
    return render_debug_artifacts_section_with_time_format(
        debug_artifacts,
        use_24_hour_time=True,
    )


def render_debug_artifacts_section_with_time_format(
    debug_artifacts: tuple[DebugArtifact, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染與單一 watch item 關聯的診斷檔案摘要。"""
    if not debug_artifacts:
        return empty_state_card(
            title="診斷檔案",
            message="目前尚無背景監視診斷紀錄。",
            extra_html=(
                "<p>若要看建立監視 / preview 過程的診斷紀錄，"
                "請到首頁的進階診斷。</p>"
            ),
        )

    rows = []
    for artifact in debug_artifacts[:10]:
        http_status_text = (
            str(artifact.http_status) if artifact.http_status is not None else "無"
        )
        reason_text = _describe_debug_reason(artifact.reason)
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            artifact.captured_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    escape(reason_text),
                    escape(artifact.source_url or "無"),
                    escape(http_status_text),
                )
            )
        )

    return card(
        title="診斷檔案",
        body=f"""
        <p>
          這裡顯示背景監視期間保存的診斷紀錄，例如站方阻擋、
          可能節流或分頁被瀏覽器暫停。
        </p>
        <p>建立監視或解析問題請到首頁的進階診斷查看。</p>
        {data_table(
            headers=("時間", "原因", "來源頁面", "頁面狀態"),
            rows_html="".join(rows),
        )}
        """,
    )


def render_watch_action_controls(
    *,
    watch_item: WatchItem,
    runtime_state: WatchRuntimeState,
    surface: WatchActionSurface,
) -> str:
    """依頁面情境渲染 watch 操作按鈕。"""
    actions = build_watch_action_presentations(
        runtime_state=runtime_state,
        surface=surface,
    )
    return action_row(
        body="".join(
            _render_watch_action_form(watch_item_id=watch_item.id, action=action)
            for action in actions
        ),
        extra_style="flex-wrap:nowrap;",
    )


def render_watch_list_polling_script(initial_fragment_version: str | None = None) -> str:
    """在首頁啟用版本 polling，只在資料變更時同步 fragment。"""
    return """
    <script>
      (() => {
        const summaryContainer = document.getElementById("dashboard-summary-section");
        const flashContainer = document.getElementById("dashboard-flash-section");
        const runtimeContainer = document.getElementById("runtime-status-section");
        const tableBody = document.getElementById("watch-list-table-body");
        const viewModeButtons = document.querySelectorAll("[data-watch-view-mode-button]");
        if (!summaryContainer || !runtimeContainer || !tableBody) {
          return;
        }
        const storageKey = "hotelPriceWatch.watchListViewMode";
        const runtimeDockStorageKey = "hotelPriceWatch.runtimeStatusCollapsed";
        const minFragmentRefreshMs = 1000;
        let currentVersion = __INITIAL_VERSION__;
        let pendingVersion = null;
        let lastFragmentRefreshAt = 0;
        let scheduledFragmentRefresh = null;

        const applyViewMode = (mode) => {
          const safeMode = mode === "list" ? "list" : "cards";
          document.querySelectorAll("[data-watch-list-view]").forEach((element) => {
            element.style.display =
              element.dataset.watchListView === safeMode ? "" : "none";
          });
          viewModeButtons.forEach((button) => {
            button.classList.toggle(
              "is-active",
              button.dataset.watchViewModeButton === safeMode
            );
          });
        };

        const currentViewMode = () =>
          window.localStorage.getItem(storageKey) === "list" ? "list" : "cards";

        const applyWatchListPayload = (payload) => {
          if (typeof payload.flash_html === "string" && flashContainer) {
            flashContainer.innerHTML = payload.flash_html;
          }
          summaryContainer.innerHTML = payload.summary_html;
          runtimeContainer.innerHTML = payload.runtime_html;
          tableBody.innerHTML = payload.table_body_html;
          applyViewMode(currentViewMode());
          applyRuntimeDockState();
          updateClientTimeText();
          if (typeof payload.version === "string") {
            currentVersion = payload.version;
            pendingVersion = null;
          }
        };

        const applyRuntimeDockState = () => {
          const collapsed = window.localStorage.getItem(runtimeDockStorageKey) === "1";
          runtimeContainer
            .querySelectorAll("[data-runtime-status-dock]")
            .forEach((dock) => {
              dock.classList.toggle("is-collapsed", collapsed);
              const toggle = dock.querySelector("[data-runtime-status-toggle]");
              if (!toggle) {
                return;
              }
              const expandedIcon = toggle.querySelector("[data-runtime-expanded-icon]");
              const collapsedIcon = toggle.querySelector("[data-runtime-collapsed-icon]");
              if (expandedIcon && collapsedIcon) {
                expandedIcon.style.display = collapsed ? "none" : "";
                collapsedIcon.style.display = collapsed ? "" : "none";
              }
              toggle.setAttribute(
                "aria-label",
                collapsed ? "展開系統狀態" : "收合系統狀態"
              );
              toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
            });
        };

        const formatRelativeTime = (targetDate) => {
          const elapsedSeconds = Math.max(
            Math.floor((Date.now() - targetDate.getTime()) / 1000),
            0
          );
          if (elapsedSeconds < 60) {
            return "剛剛";
          }
          const elapsedMinutes = Math.floor(elapsedSeconds / 60);
          if (elapsedMinutes < 60) {
            return `${elapsedMinutes} 分鐘前`;
          }
          const elapsedHours = Math.floor(elapsedMinutes / 60);
          if (elapsedHours < 24) {
            return `${elapsedHours} 小時前`;
          }
          return `${Math.floor(elapsedHours / 24)} 天前`;
        };

        const formatCountdownTime = (targetDate) => {
          const remainingSeconds = Math.ceil(
            (targetDate.getTime() - Date.now()) / 1000
          );
          if (remainingSeconds <= 60) {
            return "預計 1 分鐘內自動重試";
          }
          return `預計 ${Math.ceil(remainingSeconds / 60)} 分鐘後自動重試`;
        };

        const updateClientTimeText = () => {
          document.querySelectorAll("[data-relative-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.relativeTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatRelativeTime(targetDate);
            }
          });
          document.querySelectorAll("[data-countdown-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.countdownTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatCountdownTime(targetDate);
            }
          });
        };

        viewModeButtons.forEach((button) => {
          button.addEventListener("click", () => {
            const mode = button.dataset.watchViewModeButton === "list" ? "list" : "cards";
            window.localStorage.setItem(storageKey, mode);
            applyViewMode(mode);
          });
        });
        runtimeContainer.addEventListener("click", (event) => {
          const toggle = event.target.closest("[data-runtime-status-toggle]");
          if (!toggle) {
            return;
          }
          const collapsed = window.localStorage.getItem(runtimeDockStorageKey) === "1";
          window.localStorage.setItem(runtimeDockStorageKey, collapsed ? "0" : "1");
          applyRuntimeDockState();
        });
        tableBody.addEventListener("submit", async (event) => {
          const form = event.target.closest("form[data-watch-list-action]");
          if (!form || event.defaultPrevented) {
            return;
          }
          event.preventDefault();
          const buttons = form.querySelectorAll("button");
          buttons.forEach((button) => {
            button.disabled = true;
          });
          try {
            const response = await fetch(form.action, {
              method: "POST",
              body: new FormData(form),
              headers: {
                "Accept": "application/json",
                "X-Requested-With": "fetch",
              },
              credentials: "same-origin",
            });
            if (!response.ok) {
              buttons.forEach((button) => {
                button.disabled = false;
              });
              return;
            }
            applyWatchListPayload(await response.json());
          } catch {
            buttons.forEach((button) => {
              button.disabled = false;
            });
          }
        });
        applyViewMode(currentViewMode());
        applyRuntimeDockState();
        updateClientTimeText();

        const refreshFragments = async () => {
          try {
            const response = await fetch("/fragments/watch-list", {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            lastFragmentRefreshAt = Date.now();
            applyWatchListPayload(await response.json());
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        const scheduleFragmentRefresh = () => {
          if (scheduledFragmentRefresh !== null) {
            return;
          }
          const elapsed = Date.now() - lastFragmentRefreshAt;
          const delay = Math.max(minFragmentRefreshMs - elapsed, 0);
          scheduledFragmentRefresh = window.setTimeout(() => {
            scheduledFragmentRefresh = null;
            refreshFragments();
          }, delay);
        };

        const checkVersion = async () => {
          try {
            const response = await fetch("/fragments/watch-list/version", {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            const payload = await response.json();
            if (typeof payload.version !== "string") {
              return;
            }
            if (currentVersion === null) {
              currentVersion = payload.version;
              return;
            }
            if (payload.version !== currentVersion) {
              pendingVersion = payload.version;
              scheduleFragmentRefresh();
            }
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        window.setInterval(checkVersion, 1000);
        window.setInterval(updateClientTimeText, 30000);
      })();
    </script>
    """.replace("__INITIAL_VERSION__", json.dumps(initial_fragment_version))


def render_watch_detail_polling_script(
    watch_item_id: str,
    *,
    initial_fragment_version: str | None = None,
) -> str:
    """在 watch 詳細頁啟用版本 polling，只在資料變更時同步 fragment。"""
    fragments_url = json.dumps(f"/watches/{watch_item_id}/fragments")
    version_url = json.dumps(f"/watches/{watch_item_id}/fragments/version")
    return """
    <script>
      (() => {
        const heroSection = document.getElementById("watch-detail-hero-section");
        const checkEventsSection = document.getElementById(
          "watch-detail-check-events-section"
        );
        const priceSummarySection = document.getElementById(
          "watch-detail-price-summary-section"
        );
        const priceTrendSection = document.getElementById(
          "watch-detail-price-trend-section"
        );
        const runtimeStateEventsSection = document.getElementById(
          "watch-detail-runtime-state-events-section"
        );
        const debugArtifactsSection = document.getElementById(
          "watch-detail-debug-artifacts-section"
        );
        const fragmentsUrl = __FRAGMENTS_URL__;
        const versionUrl = __VERSION_URL__;
        const minFragmentRefreshMs = 1000;
        let currentVersion = __INITIAL_VERSION__;
        let pendingVersion = null;
        let lastFragmentRefreshAt = 0;
        let scheduledFragmentRefresh = null;
        if (
          !heroSection ||
          !priceSummarySection ||
          !priceTrendSection ||
          !runtimeStateEventsSection ||
          !checkEventsSection ||
          !debugArtifactsSection
        ) {
          return;
        }

        const formatRelativeTime = (targetDate) => {
          const elapsedSeconds = Math.max(
            Math.floor((Date.now() - targetDate.getTime()) / 1000),
            0
          );
          if (elapsedSeconds < 60) {
            return "剛剛";
          }
          const elapsedMinutes = Math.floor(elapsedSeconds / 60);
          if (elapsedMinutes < 60) {
            return `${elapsedMinutes} 分鐘前`;
          }
          const elapsedHours = Math.floor(elapsedMinutes / 60);
          if (elapsedHours < 24) {
            return `${elapsedHours} 小時前`;
          }
          return `${Math.floor(elapsedHours / 24)} 天前`;
        };

        const formatCountdownTime = (targetDate) => {
          const remainingSeconds = Math.ceil(
            (targetDate.getTime() - Date.now()) / 1000
          );
          if (remainingSeconds <= 60) {
            return "預計 1 分鐘內自動重試";
          }
          return `預計 ${Math.ceil(remainingSeconds / 60)} 分鐘後自動重試`;
        };

        const updateClientTimeText = () => {
          document.querySelectorAll("[data-relative-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.relativeTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatRelativeTime(targetDate);
            }
          });
          document.querySelectorAll("[data-countdown-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.countdownTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatCountdownTime(targetDate);
            }
          });
        };

        const applyWatchDetailPayload = (payload) => {
          heroSection.innerHTML = payload.hero_section_html;
          priceSummarySection.innerHTML = payload.price_summary_section_html;
          priceTrendSection.innerHTML = payload.price_trend_section_html;
          runtimeStateEventsSection.innerHTML = payload.runtime_state_events_section_html;
          checkEventsSection.innerHTML = payload.check_events_section_html;
          debugArtifactsSection.innerHTML = payload.debug_artifacts_section_html;
          updateClientTimeText();
          if (typeof payload.version === "string") {
            currentVersion = payload.version;
            pendingVersion = null;
          }
        };

        const refreshFragments = async () => {
          try {
            const response = await fetch(fragmentsUrl, {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            lastFragmentRefreshAt = Date.now();
            applyWatchDetailPayload(await response.json());
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        const scheduleFragmentRefresh = () => {
          if (scheduledFragmentRefresh !== null) {
            return;
          }
          const elapsed = Date.now() - lastFragmentRefreshAt;
          const delay = Math.max(minFragmentRefreshMs - elapsed, 0);
          scheduledFragmentRefresh = window.setTimeout(() => {
            scheduledFragmentRefresh = null;
            refreshFragments();
          }, delay);
        };

        const checkVersion = async () => {
          try {
            const response = await fetch(versionUrl, {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            const payload = await response.json();
            if (typeof payload.version !== "string") {
              return;
            }
            if (currentVersion === null) {
              currentVersion = payload.version;
              return;
            }
            if (payload.version !== currentVersion) {
              pendingVersion = payload.version;
              scheduleFragmentRefresh();
            }
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        updateClientTimeText();
        window.setInterval(checkVersion, 1000);
        window.setInterval(updateClientTimeText, 30000);
      })();
    </script>
    """.replace("__FRAGMENTS_URL__", fragments_url).replace(
        "__VERSION_URL__",
        version_url,
    ).replace("__INITIAL_VERSION__", json.dumps(initial_fragment_version))


def _render_watch_action_form(
    *,
    watch_item_id: str,
    action: WatchActionPresentation,
) -> str:
    """渲染單一 watch 操作按鈕表單。"""
    confirm_attr = (
        f' onsubmit="return confirm(\'{escape(action.confirm_message)}\')"'
        if action.confirm_message is not None
        else ""
    )
    quick_action_attr = (
        ' data-watch-list-action="true"' if action.submit_mode == "fetch" else ""
    )
    return f"""
    <form
      action="/watches/{escape(watch_item_id)}/{escape(action.action)}"
      method="post"
      style="margin:0;"
      {confirm_attr}
      {quick_action_attr}
    >
      {submit_button(label=action.label, kind=action.button_kind)}
    </form>
    """


def _watch_needs_attention(snapshot: LatestCheckSnapshot | None) -> bool:
    """判斷首頁摘要是否應把 watch 計入需注意項目。"""
    if snapshot is None:
        return False
    return bool(snapshot.last_error_code or snapshot.is_degraded)


def _format_occupancy_text(watch_item: WatchItem) -> str:
    """把 watch target 的入住人數與房數轉成首頁與詳情頁共用文案。"""
    return f"{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房"


def _format_date_range_text(watch_item: WatchItem) -> str:
    """把 watch target 的日期與晚數整理成使用者容易掃描的文案。"""
    date_text = _format_date_range_core(watch_item)
    return f"{date_text}，{watch_item.target.nights} 晚"


def _format_date_range_list_html(watch_item: WatchItem) -> str:
    """把清單模式日期分成日期區間與晚數兩行，降低欄寬壓力。"""
    date_text = _format_date_range_core(watch_item)
    nights_text = f"{watch_item.target.nights} 晚"
    return (
        f'<span style="white-space:nowrap;">{escape(date_text)}</span>'
        f"<br><span style=\"{muted_text_style(font_size='13px')}\">"
        f"{escape(nights_text)}</span>"
    )


def _format_date_range_list_html_from_row(row: WatchRowPresentation) -> str:
    """把首頁 view model 的日期拆成日期區間與晚數兩行。"""
    return (
        f'<span style="white-space:nowrap;">{escape(row.date_range_short_text)}</span>'
        f"<br><span style=\"{muted_text_style(font_size='13px')}\">"
        f"{escape(row.nights_text)}</span>"
    )


def _presentation_badge_html(presentation: BadgePresentation | None) -> str:
    """把 presenter badge 轉成共用 badge HTML，允許缺值。"""
    if presentation is None:
        return ""
    return status_badge(label=presentation.label, kind=presentation.kind)


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


def _format_datetime_summary_value(
    value: datetime | None,
    *,
    empty_text: str,
    use_24_hour_time: bool,
) -> tuple[str, str | None]:
    """把摘要卡片的時間拆成純文字與受控分行 HTML。"""
    if value is None:
        return empty_text, None

    date_text, time_text = format_datetime_lines_for_display(
        value,
        use_24_hour_time=use_24_hour_time,
    )
    html = (
        f'<span style="display:block;white-space:nowrap;">{escape(date_text)}</span>'
        f'<span style="display:block;white-space:nowrap;">{escape(time_text)}</span>'
    )
    return f"{date_text} {time_text}", html


def _watch_card_sort_key(
    watch_item: WatchItem,
    snapshot: LatestCheckSnapshot | None,
) -> tuple[int, float, str]:
    """回傳首頁 watch card 排序鍵，讓需注意項目優先顯示。"""
    attention_rank = 0 if _watch_needs_attention(snapshot) else 1
    checked_rank = -(snapshot.checked_at.timestamp()) if snapshot is not None else 0.0
    return (attention_rank, checked_rank, watch_item.hotel_name)


def _availability_badge_html(snapshot: LatestCheckSnapshot | None) -> str:
    """把 latest snapshot 的空房狀態轉成 badge，缺值時回傳尚未檢查。"""
    if snapshot is None:
        return "<strong>尚未檢查</strong>"
    availability_presentation = availability_badge(snapshot.availability)
    return status_badge(
        label=availability_presentation.label,
        kind=availability_presentation.kind,
    )


def _priced_check_events(check_events: tuple[CheckEvent, ...]) -> tuple[CheckEvent, ...]:
    """取出可用於價格趨勢的檢查事件，並依時間由舊到新排序。"""
    return tuple(
        sorted(
            (
                event
                for event in check_events
                if event.normalized_price_amount is not None
            ),
            key=lambda event: event.checked_at,
        )
    )


def _price_amount(event: CheckEvent) -> Decimal:
    """取得已確認存在的價格數值，供趨勢圖計算座標使用。"""
    if event.normalized_price_amount is None:
        raise ValueError("priced check event must carry normalized_price_amount")
    return event.normalized_price_amount


def _price_chart_points(chart_events: tuple[CheckEvent, ...]) -> str:
    """將價格事件轉成 SVG polyline points。"""
    prices = [_price_amount(event) for event in chart_events]
    min_price = min(prices)
    max_price = max(prices)
    price_span = max_price - min_price
    denominator = max(len(chart_events) - 1, 1)
    points: list[str] = []
    for index, price in enumerate(prices):
        x = PRICE_CHART_LEFT + (PRICE_CHART_WIDTH * index / denominator)
        normalized = 0.5 if price_span == 0 else float((price - min_price) / price_span)
        y = PRICE_CHART_TOP + PRICE_CHART_HEIGHT - (PRICE_CHART_HEIGHT * normalized)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _price_chart_axes(
    chart_events: tuple[CheckEvent, ...],
    *,
    min_price: Decimal,
    max_price: Decimal,
    use_24_hour_time: bool,
) -> str:
    """渲染價格趨勢圖的輕量 X/Y 軸與端點標籤。"""
    oldest_event = chart_events[0]
    latest_event = chart_events[-1]
    axis_color = color_token("border_strong")
    label_color = color_token("muted")
    min_label = money_text(latest_event.currency, min_price)
    max_label = money_text(latest_event.currency, max_price)
    oldest_label = _format_chart_axis_time(
        oldest_event.checked_at,
        use_24_hour_time=use_24_hour_time,
    )
    latest_label = _format_chart_axis_time(
        latest_event.checked_at,
        use_24_hour_time=use_24_hour_time,
    )
    if min_price == max_price:
        flat_label_y = PRICE_CHART_TOP + (PRICE_CHART_HEIGHT / 2) + 4
        price_label_html = f"""
    <text x="{PRICE_CHART_LEFT - 8}" y="{flat_label_y:.1f}" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(max_label)}</text>
        """
    else:
        price_label_html = f"""
    <text x="{PRICE_CHART_LEFT - 8}" y="{PRICE_CHART_TOP + 5}" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(max_label)}</text>
    <text x="{PRICE_CHART_LEFT - 8}" y="{PRICE_CHART_BOTTOM + 4}" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(min_label)}</text>
        """
    return f"""
    <line
      x1="{PRICE_CHART_LEFT}" y1="{PRICE_CHART_BOTTOM}"
      x2="{PRICE_CHART_LEFT + PRICE_CHART_WIDTH}" y2="{PRICE_CHART_BOTTOM}"
      stroke="{axis_color}" stroke-width="1"
    />
    <line
      x1="{PRICE_CHART_LEFT}" y1="{PRICE_CHART_TOP}"
      x2="{PRICE_CHART_LEFT}" y2="{PRICE_CHART_BOTTOM}"
      stroke="{axis_color}" stroke-width="1"
    />
    {price_label_html}
    <text x="{PRICE_CHART_LEFT}" y="166" text-anchor="start"
      font-size="12" fill="{label_color}">{escape(oldest_label)}</text>
    <text x="{PRICE_CHART_LEFT + PRICE_CHART_WIDTH}" y="166" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(latest_label)}</text>
    """


def _format_chart_axis_time(value: datetime, *, use_24_hour_time: bool) -> str:
    """產生趨勢圖座標軸使用的短時間標籤。"""
    local_value = value.astimezone()
    if use_24_hour_time:
        return f"{local_value.month}/{local_value.day} {local_value:%H:%M}"

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return f"{local_value.month}/{local_value.day} {period_text} {hour:02d}:{local_value:%M}"


def _price_chart_markers(
    chart_events: tuple[CheckEvent, ...],
    points: str,
    *,
    use_24_hour_time: bool,
) -> str:
    """渲染 SVG 上的價格節點，hover 時顯示時間與價格。"""
    point_values = [point.split(",") for point in points.split()]
    markers: list[str] = []
    for event, (x, y) in zip(chart_events, point_values, strict=True):
        point_time = _format_chart_axis_time(
            event.checked_at,
            use_24_hour_time=use_24_hour_time,
        )
        point_price = money_text(event.currency, event.normalized_price_amount)
        markers.append(
            f"""
            <circle cx="{escape(x)}" cy="{escape(y)}" r="4" fill="{color_token('primary')}">
              <title>{escape(point_time)} · {escape(point_price)}</title>
            </circle>
            """
        )
    return "".join(markers)


def _price_delta_text(oldest_event: CheckEvent, latest_event: CheckEvent) -> str:
    """計算趨勢圖區間內最新價格相對起點的變化文案。"""
    delta = _price_amount(latest_event) - _price_amount(oldest_event)
    if delta == 0:
        return "持平"
    direction = "下降" if delta < 0 else "上升"
    return f"{direction} {money_text(latest_event.currency, abs(delta))}"


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
