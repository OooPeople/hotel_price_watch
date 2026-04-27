"""watch list / dashboard 專用 partial renderer。"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Iterable

from app.domain import derive_watch_runtime_state
from app.domain.entities import LatestCheckSnapshot, PriceHistoryEntry, WatchItem
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import empty_state_card, icon_svg, status_badge, text_link
from app.web.ui_presenters import (
    BadgePresentation,
    WatchActionSurface,
    WatchRowPresentation,
    build_watch_row_presentation,
    price_history_changed,
    price_history_increased,
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
from app.web.view_formatters import format_datetime_for_display
from app.web.watch_action_partials import render_watch_action_controls


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

def _watch_needs_attention(snapshot: LatestCheckSnapshot | None) -> bool:
    """判斷首頁摘要是否應把 watch 計入需注意項目。"""
    if snapshot is None:
        return False
    return bool(snapshot.last_error_code or snapshot.is_degraded)

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

