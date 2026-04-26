"""watch 列表與詳細頁面的頁面級 HTML renderer。"""

from __future__ import annotations

from html import escape
from typing import Iterable

from app.domain import derive_watch_runtime_state
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    PriceHistoryEntry,
    RuntimeStateEvent,
    WatchItem,
)
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import (
    action_row,
    card,
    collapsible_section,
    link_button,
    page_header,
    page_layout,
    section_header,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.ui_presenters import WatchActionSurface
from app.web.ui_styles import meta_paragraph_style, stack_style
from app.web.watch_view_partials import (
    render_check_events_section_with_time_format,
    render_dashboard_summary_cards,
    render_debug_artifacts_section_with_time_format,
    render_price_trend_section_with_time_format,
    render_runtime_state_events_section_with_time_format,
    render_runtime_status_section_with_time_format,
    render_watch_action_controls,
    render_watch_detail_hero_section,
    render_watch_detail_polling_script,
    render_watch_list_polling_script,
    render_watch_list_rows,
    render_watch_price_summary_cards,
)


def render_watch_list_page(
    *,
    watch_items: Iterable[WatchItem],
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    today_notification_count: int = 0,
    flash_message: str | None = None,
    runtime_status: MonitorRuntimeStatus | None = None,
    use_24_hour_time: bool = True,
    initial_fragment_version: str | None = None,
) -> str:
    """渲染 watch item 列表頁。"""
    flash_html = render_flash_message(flash_message)
    runtime_html = render_runtime_status_section_with_time_format(
        runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    summary_html = render_dashboard_summary_cards(
        watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        today_notification_count=today_notification_count,
        runtime_status=runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    watch_cards_html = render_watch_list_rows(
        watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        use_24_hour_time=use_24_hour_time,
    )
    watch_list_header_style = (
        "display:flex;justify-content:space-between;gap:16px;"
        "align-items:end;flex-wrap:wrap;"
    )
    return page_layout(
        title="我的價格監視",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="我的價格監視",
              subtitle="追蹤指定飯店、日期、房型與方案的價格變化。",
              actions_html=action_row(
                  body=(
                      link_button(href="/settings", label="設定")
                      + link_button(href="/debug/captures", label="進階診斷")
                      + link_button(href="/watches/new", label="新增監視", kind="primary")
                  ),
                  extra_style="align-items:center;",
              ),
          )}
          <div id="dashboard-flash-section">{flash_html}</div>
          <div id="dashboard-summary-section">{summary_html}</div>
          <section style="{stack_style(gap="lg")}">
            <div style="{watch_list_header_style}">
              {section_header(
                  title="監視項目",
                  subtitle="需要注意的項目會優先顯示；技術細節保留在進階診斷中。",
              )}
              <div class="watch-list-view-toggle" style="display:flex;gap:8px;flex-wrap:wrap;">
                <button type="button" data-watch-view-mode-button="cards">卡片</button>
                <button type="button" data-watch-view-mode-button="list">清單</button>
              </div>
            </div>
            <div id="watch-list-table-body" style="{stack_style(gap="lg")}">
              {watch_cards_html}
            </div>
          </section>
          <div id="runtime-status-section">{runtime_html}</div>
        </section>
        {render_watch_list_polling_script(initial_fragment_version)}
        """,
    )


def render_runtime_status_fragment(
    runtime_status: MonitorRuntimeStatus | None,
    *,
    use_24_hour_time: bool = True,
) -> str:
    """提供首頁 polling 使用的 runtime 摘要 HTML 片段。"""
    return render_runtime_status_section_with_time_format(
        runtime_status,
        use_24_hour_time=use_24_hour_time,
    )


def render_dashboard_summary_fragment(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    today_notification_count: int = 0,
    runtime_status: MonitorRuntimeStatus | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """提供首頁 polling 使用的 summary cards HTML 片段。"""
    return render_dashboard_summary_cards(
        watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        today_notification_count=today_notification_count,
        runtime_status=runtime_status,
        use_24_hour_time=use_24_hour_time,
    )


def render_watch_list_rows_fragment(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """提供首頁 polling 使用的 watch 列表 tbody 片段。"""
    return render_watch_list_rows(
        watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        use_24_hour_time=use_24_hour_time,
    )


def render_watch_detail_page(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    check_events: tuple[CheckEvent, ...],
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    flash_message: str | None = None,
    use_24_hour_time: bool = True,
    initial_fragment_version: str | None = None,
) -> str:
    """渲染單一 watch item 的詳細頁與歷史摘要。"""
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    hero_html = render_watch_detail_hero_section(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        use_24_hour_time=use_24_hour_time,
    )
    price_summary_html = render_watch_price_summary_cards(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        notification_state=notification_state,
        use_24_hour_time=use_24_hour_time,
    )
    runtime_state_events_html = render_runtime_state_events_section_with_time_format(
        runtime_state_events,
        use_24_hour_time=use_24_hour_time,
    )
    check_events_html = render_check_events_section_with_time_format(
        check_events,
        use_24_hour_time=use_24_hour_time,
    )
    price_trend_html = render_price_trend_section_with_time_format(
        check_events,
        use_24_hour_time=use_24_hour_time,
    )
    debug_artifacts_html = render_debug_artifacts_section_with_time_format(
        debug_artifacts,
        use_24_hour_time=use_24_hour_time,
    )
    flash_html = render_flash_message(flash_message)
    action_controls_html = render_watch_action_controls(
        watch_item=watch_item,
        runtime_state=runtime_state,
        surface=WatchActionSurface.DETAIL,
    )
    technical_info_html = card(
        title="技術資訊",
        body=f"""
        <p style="{meta_paragraph_style()}">
          這些資訊主要用於排錯，平常不需要查看。
        </p>
        <p>Canonical URL：<code>{escape(watch_item.canonical_url)}</code></p>
        <p>檢查頻率：每 {watch_item.scheduler_interval_seconds} 秒</p>
        """,
    )
    advanced_diagnostics_html = collapsible_section(
        title="進階診斷",
        body=f"""
        {technical_info_html}
        <div id="watch-detail-runtime-state-events-section">{runtime_state_events_html}</div>
        <div id="watch-detail-debug-artifacts-section">{debug_artifacts_html}</div>
        """,
    )

    return page_layout(
        title=f"監視詳情 - {watch_item.hotel_name}",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="監視詳情",
              subtitle="查看此飯店房型的價格、空房狀態與通知條件。",
              back_href="/",
              back_label="回列表",
              actions_html=action_row(
                  body=(
                      link_button(
                          href=f"/watches/{watch_item.id}/notification-settings",
                          label="通知設定",
                      )
                      + action_controls_html
                  ),
                  extra_style="align-items:center;",
              ),
          )}
          {flash_html}
          <div id="watch-detail-hero-section">{hero_html}</div>
          <div id="watch-detail-price-summary-section">{price_summary_html}</div>
          <div id="watch-detail-price-trend-section">{price_trend_html}</div>
          <div id="watch-detail-check-events-section">{check_events_html}</div>
          {advanced_diagnostics_html}
        </section>
        {render_watch_detail_polling_script(
            watch_item.id,
            initial_fragment_version=initial_fragment_version,
        )}
        """,
    )


def render_watch_detail_sections(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    check_events: tuple[CheckEvent, ...],
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    use_24_hour_time: bool = True,
) -> dict[str, str]:
    """提供 watch 詳細頁 polling 使用的主要 HTML 片段。"""
    return {
        "hero_section_html": render_watch_detail_hero_section(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            use_24_hour_time=use_24_hour_time,
        ),
        "runtime_state_events_section_html": render_runtime_state_events_section_with_time_format(
            runtime_state_events,
            use_24_hour_time=use_24_hour_time,
        ),
        "price_summary_section_html": render_watch_price_summary_cards(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            notification_state=notification_state,
            use_24_hour_time=use_24_hour_time,
        ),
        "check_events_section_html": render_check_events_section_with_time_format(
            check_events,
            use_24_hour_time=use_24_hour_time,
        ),
        "price_trend_section_html": render_price_trend_section_with_time_format(
            check_events,
            use_24_hour_time=use_24_hour_time,
        ),
        "debug_artifacts_section_html": render_debug_artifacts_section_with_time_format(
            debug_artifacts,
            use_24_hour_time=use_24_hour_time,
        ),
    }
