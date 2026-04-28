"""Watch Detail 頁面 shell 與 fragment section renderer。"""

from __future__ import annotations

from html import escape

from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    RuntimeStateEvent,
    WatchItem,
)
from app.web.ui_components import (
    action_row,
    card,
    collapsible_section,
    link_button,
    page_header,
    page_layout,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.ui_page_sections import page_stack
from app.web.ui_presenters import WatchActionSurface
from app.web.ui_styles import meta_paragraph_style
from app.web.watch_detail_fragment_assembler import (
    render_watch_detail_sections,
    render_watch_detail_sections_from_view_model,
)
from app.web.watch_detail_page_scripts import render_watch_detail_page_scripts
from app.web.watch_detail_partials import render_watch_action_controls
from app.web.watch_detail_presenters import build_watch_detail_page_view_model
from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_DOM_IDS,
    WATCH_DETAIL_FRAGMENT_SECTIONS,
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
    detail_view_model = build_watch_detail_page_view_model(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        check_events=check_events,
        notification_state=notification_state,
        debug_artifacts=debug_artifacts,
        runtime_state_events=runtime_state_events,
        use_24_hour_time=use_24_hour_time,
    )
    section_html_by_key = render_watch_detail_sections_from_view_model(
        detail_view_model,
        use_24_hour_time=use_24_hour_time,
    )
    flash_html = render_flash_message(flash_message)
    action_controls_html = render_watch_action_controls(
        watch_item=watch_item,
        runtime_state=detail_view_model.summary.runtime_state,
        surface=WatchActionSurface.DETAIL,
    )
    technical_info_html = card(
        title="技術資訊",
        body=f"""
        <p style="{meta_paragraph_style()}">
          這些資訊主要用於排錯，平常不需要查看。
        </p>
        <p>Canonical URL：<code>{escape(detail_view_model.summary.canonical_url)}</code></p>
        <p>檢查頻率：每 {detail_view_model.summary.scheduler_interval_seconds} 秒</p>
        """,
    )
    advanced_diagnostics_html = collapsible_section(
        title="進階診斷",
        body=f"""
        {technical_info_html}
        {_render_section_container("runtime_state_events", section_html_by_key)}
        {_render_section_container("debug_artifacts", section_html_by_key)}
        """,
    )

    return page_layout(
        title=f"監視詳情 - {watch_item.hotel_name}",
        body=page_stack(
            f"""
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
          {_render_section_container("hero", section_html_by_key)}
          {_render_section_container("price_summary", section_html_by_key)}
          {_render_section_container("price_trend", section_html_by_key)}
          {_render_section_container("check_events", section_html_by_key)}
          {advanced_diagnostics_html}
        {render_watch_detail_page_scripts(
            watch_item.id,
            initial_fragment_version=initial_fragment_version,
        )}
        """,
        ),
    )


def _render_section_container(
    section_name: str,
    section_html_by_key: dict[str, str],
) -> str:
    """依 detail section registry 渲染可被 fragment polling 更新的容器。"""
    section = next(
        item for item in WATCH_DETAIL_FRAGMENT_SECTIONS if item.name == section_name
    )
    return (
        f'<div id="{section.dom_id}">'
        f"{section_html_by_key[section.payload_key]}"
        "</div>"
    )


__all__ = [
    "WATCH_DETAIL_DOM_IDS",
    "render_watch_detail_page",
    "render_watch_detail_sections",
]
