"""watch 列表與詳細頁面的頁面級 HTML renderer。"""

from __future__ import annotations

from typing import Iterable

from app.domain.entities import (
    LatestCheckSnapshot,
    PriceHistoryEntry,
    WatchItem,
)
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import (
    action_row,
    link_button,
    page_header,
    page_layout,
    section_header,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.ui_page_sections import cluster_style
from app.web.ui_styles import stack_style
from app.web.watch_client_scripts import (
    render_watch_list_polling_script,
)
from app.web.watch_detail_views import (
    render_watch_detail_page,
    render_watch_detail_sections,
)
from app.web.watch_fragment_contracts import (
    WATCH_LIST_DOM_IDS,
)
from app.web.watch_list_partials import (
    render_dashboard_summary_cards_from_presentation,
    render_runtime_status_section_from_presentation,
    render_watch_list_rows_from_presentation,
)
from app.web.watch_list_presenters import (
    build_dashboard_page_view_model,
    build_runtime_status_presentation,
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
    dashboard_view_model = build_dashboard_page_view_model(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        today_notification_count=today_notification_count,
        runtime_status=runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    flash_html = render_flash_message(flash_message)
    runtime_html = render_runtime_status_section_from_presentation(
        dashboard_view_model.runtime_status,
    )
    summary_html = render_dashboard_summary_cards_from_presentation(
        dashboard_view_model.summary_cards,
    )
    watch_cards_html = render_watch_list_rows_from_presentation(
        dashboard_view_model,
    )
    watch_list_header_style = cluster_style(
        gap="lg",
        justify="space-between",
        align="end",
    )
    watch_view_toggle_style = cluster_style(gap="sm")
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
          <div id="{WATCH_LIST_DOM_IDS.flash}">{flash_html}</div>
          <div id="{WATCH_LIST_DOM_IDS.summary}">{summary_html}</div>
          <section style="{stack_style(gap="lg")}">
            <div style="{watch_list_header_style}">
              {section_header(
                  title="監視項目",
                  subtitle="需要注意的項目會優先顯示；技術細節保留在進階診斷中。",
              )}
              <div class="watch-list-view-toggle" style="{watch_view_toggle_style}">
                <button type="button" data-watch-view-mode-button="cards">卡片</button>
                <button type="button" data-watch-view-mode-button="list">清單</button>
              </div>
            </div>
            <div id="{WATCH_LIST_DOM_IDS.watch_list}" style="{stack_style(gap="lg")}">
              {watch_cards_html}
            </div>
          </section>
          <div id="{WATCH_LIST_DOM_IDS.runtime}">{runtime_html}</div>
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
    return render_runtime_status_section_from_presentation(
        build_runtime_status_presentation(
            runtime_status,
            use_24_hour_time=use_24_hour_time,
        )
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
    dashboard_view_model = build_dashboard_page_view_model(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        today_notification_count=today_notification_count,
        runtime_status=runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    return render_dashboard_summary_cards_from_presentation(
        dashboard_view_model.summary_cards,
    )


def render_watch_list_rows_fragment(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """提供首頁 polling 使用的 watch 列表 tbody 片段。"""
    dashboard_view_model = build_dashboard_page_view_model(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        use_24_hour_time=use_24_hour_time,
    )
    return render_watch_list_rows_from_presentation(dashboard_view_model)


__all__ = [
    "render_dashboard_summary_fragment",
    "render_runtime_status_fragment",
    "render_watch_detail_page",
    "render_watch_detail_sections",
    "render_watch_list_page",
    "render_watch_list_rows_fragment",
]
