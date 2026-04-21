"""watch 列表與詳細頁面的頁面級 HTML renderer。"""

from __future__ import annotations

from html import escape
from typing import Iterable

from app.domain import derive_watch_runtime_state, describe_watch_runtime_state
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    RuntimeStateEvent,
    WatchItem,
)
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import (
    action_row,
    data_table,
    link_button,
    page_layout,
    text_link,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.watch_view_partials import (
    render_check_events_section_with_time_format,
    render_debug_artifacts_section_with_time_format,
    render_latest_snapshot_section,
    render_runtime_state_events_section_with_time_format,
    render_runtime_status_section_with_time_format,
    render_watch_action_controls,
    render_watch_detail_polling_script,
    render_watch_list_polling_script,
    render_watch_list_rows,
)


def render_watch_list_page(
    *,
    watch_items: Iterable[WatchItem],
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    flash_message: str | None = None,
    runtime_status: MonitorRuntimeStatus | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染 watch item 列表頁。"""
    flash_html = render_flash_message(flash_message)
    runtime_html = render_runtime_status_section_with_time_format(
        runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    table_body = render_watch_list_rows(
        watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
    )
    return page_layout(
        title="Watch Items",
        body=f"""
        <section>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;">
            <div>
              <h1>Watch Items</h1>
              <p>目前可直接從專用 Chrome 頁面抓取候選並建立新的監看項。</p>
            </div>
            {action_row(
                body=(
                    link_button(href="/settings", label="設定")
                    + link_button(href="/debug/captures", label="Debug 區")
                    + link_button(href="/watches/new", label="新增 Watch", kind="primary")
                ),
                extra_style="align-items:center;",
            )}
          </div>
          {flash_html}
          <div id="runtime-status-section">{runtime_html}</div>
          {data_table(
              headers=("飯店", "房型", "方案", "日期", "輪詢秒數", "狀態", "操作"),
              rows_html=table_body,
              body_id="watch-list-table-body",
              extra_style="margin-top:20px;",
          )}
        </section>
        {render_watch_list_polling_script()}
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


def render_watch_list_rows_fragment(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
) -> str:
    """提供首頁 polling 使用的 watch 列表 tbody 片段。"""
    return render_watch_list_rows(
        watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
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
) -> str:
    """渲染單一 watch item 的詳細頁與歷史摘要。"""
    target_date_range = (
        f"{watch_item.target.check_in_date.isoformat()} - "
        f"{watch_item.target.check_out_date.isoformat()}"
    )
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    latest_snapshot_html = render_latest_snapshot_section(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        notification_state=notification_state,
        debug_artifacts=debug_artifacts,
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
    debug_artifacts_html = render_debug_artifacts_section_with_time_format(
        debug_artifacts,
        use_24_hour_time=use_24_hour_time,
    )
    flash_html = render_flash_message(flash_message)
    action_controls_html = render_watch_action_controls(
        watch_item=watch_item,
        runtime_state=runtime_state,
        show_check_now=True,
    )

    return page_layout(
        title=f"Watch Detail - {watch_item.hotel_name}",
        body=f"""
        <section style="display:grid;gap:20px;">
          <div>
            {text_link(href="/", label="← 回列表")}
            <h1>{escape(watch_item.hotel_name)}</h1>
            <p>房型：{escape(watch_item.room_name)}</p>
            <p>方案：{escape(watch_item.plan_name)}</p>
            <p>
              監看條件：
              {target_date_range}
              ，{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房
            </p>
            <p>輪詢秒數：{watch_item.scheduler_interval_seconds}</p>
            <p>
              目前狀態：
              {escape(describe_watch_runtime_state(runtime_state))}
            </p>
            <p>Canonical URL：<code>{escape(watch_item.canonical_url)}</code></p>
            <p>
              {link_button(
                  href=f"/watches/{watch_item.id}/notification-settings",
                  label="通知設定",
              )}
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">{action_controls_html}</div>
          </div>
          {flash_html}
          <div id="watch-detail-latest-section">{latest_snapshot_html}</div>
          <div id="watch-detail-runtime-state-events-section">{runtime_state_events_html}</div>
          <div id="watch-detail-check-events-section">{check_events_html}</div>
          <div id="watch-detail-debug-artifacts-section">{debug_artifacts_html}</div>
        </section>
        {render_watch_detail_polling_script(watch_item.id)}
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
        "latest_section_html": render_latest_snapshot_section(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            notification_state=notification_state,
            debug_artifacts=debug_artifacts,
            use_24_hour_time=use_24_hour_time,
        ),
        "runtime_state_events_section_html": render_runtime_state_events_section_with_time_format(
            runtime_state_events,
            use_24_hour_time=use_24_hour_time,
        ),
        "check_events_section_html": render_check_events_section_with_time_format(
            check_events,
            use_24_hour_time=use_24_hour_time,
        ),
        "debug_artifacts_section_html": render_debug_artifacts_section_with_time_format(
            debug_artifacts,
            use_24_hour_time=use_24_hour_time,
        ),
    }
