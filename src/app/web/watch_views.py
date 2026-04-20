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
from app.web.view_helpers import (
    SUCCESS_STYLE,
    cell_style,
    page_layout,
    primary_button_style,
    secondary_button_style,
)
from app.web.watch_view_partials import (
    render_check_events_section,
    render_debug_artifacts_section,
    render_latest_snapshot_section,
    render_runtime_state_events_section,
    render_runtime_status_section,
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
) -> str:
    """渲染 watch item 列表頁。"""
    flash_html = (
        f'<p style="{SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    runtime_html = render_runtime_status_section(runtime_status)
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
            <div style="display:flex;gap:12px;align-items:center;">
              <a href="/settings/notifications" style="{secondary_button_style()}">全域通知設定</a>
              <a href="/debug/captures" style="{secondary_button_style()}">Debug 區</a>
              <a href="/watches/new" style="{primary_button_style()}">新增 Watch</a>
            </div>
          </div>
          {flash_html}
          <div id="runtime-status-section">{runtime_html}</div>
          <table style="width:100%;border-collapse:collapse;margin-top:20px;">
            <thead>
              <tr>
                <th style="{cell_style(head=True)}">飯店</th>
                <th style="{cell_style(head=True)}">房型</th>
                <th style="{cell_style(head=True)}">方案</th>
                <th style="{cell_style(head=True)}">日期</th>
                <th style="{cell_style(head=True)}">輪詢秒數</th>
                <th style="{cell_style(head=True)}">狀態</th>
                <th style="{cell_style(head=True)}">操作</th>
              </tr>
            </thead>
            <tbody id="watch-list-table-body">{table_body}</tbody>
          </table>
        </section>
        {render_watch_list_polling_script()}
        """,
    )


def render_runtime_status_fragment(runtime_status: MonitorRuntimeStatus | None) -> str:
    """提供首頁 polling 使用的 runtime 摘要 HTML 片段。"""
    return render_runtime_status_section(runtime_status)


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
    )
    runtime_state_events_html = render_runtime_state_events_section(runtime_state_events)
    check_events_html = render_check_events_section(check_events)
    debug_artifacts_html = render_debug_artifacts_section(debug_artifacts)
    flash_html = (
        f'<p style="{SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
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
            <a href="/" style="color:#0f766e;text-decoration:none;">← 回列表</a>
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
              <a
                href="/watches/{escape(watch_item.id)}/notification-settings"
                style="{secondary_button_style()}"
              >
                通知設定
              </a>
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
) -> dict[str, str]:
    """提供 watch 詳細頁 polling 使用的主要 HTML 片段。"""
    return {
        "latest_section_html": render_latest_snapshot_section(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            notification_state=notification_state,
            debug_artifacts=debug_artifacts,
        ),
        "runtime_state_events_section_html": render_runtime_state_events_section(
            runtime_state_events
        ),
        "check_events_section_html": render_check_events_section(check_events),
        "debug_artifacts_section_html": render_debug_artifacts_section(debug_artifacts),
    }
