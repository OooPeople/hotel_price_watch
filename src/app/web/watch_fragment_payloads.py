"""watch list / detail fragment payload 的 HTML 組裝入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.web.ui_components import flash_message as render_flash_message
from app.web.views import (
    render_dashboard_summary_fragment,
    render_runtime_status_fragment,
    render_watch_list_rows_fragment,
)
from app.web.watch_detail_fragment_assembler import render_watch_detail_sections
from app.web.watch_fragment_contracts import (
    WatchDetailFragmentPayload,
    WatchListFragmentPayload,
)

if TYPE_CHECKING:
    from app.web.watch_page_service import (
        WatchDetailPageContext,
        WatchListPageContext,
    )


def build_watch_list_fragment_payload(
    *,
    context: WatchListPageContext,
    version: str,
    flash_message: str | None = None,
) -> WatchListFragmentPayload:
    """把首頁 read context 組成前端局部更新 payload。"""
    return WatchListFragmentPayload(
        version=version,
        flash_html=render_flash_message(flash_message),
        summary_html=render_dashboard_summary_fragment(
            context.watch_items,
            latest_snapshots_by_watch_id=context.latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=context.recent_price_history_by_watch_id,
            today_notification_count=context.today_notification_count,
            runtime_status=context.runtime_status,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
        runtime_html=render_runtime_status_fragment(
            context.runtime_status,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
        table_body_html=render_watch_list_rows_fragment(
            context.watch_items,
            latest_snapshots_by_watch_id=context.latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=context.recent_price_history_by_watch_id,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
    )


def build_watch_detail_fragment_payload(
    *,
    context: WatchDetailPageContext,
    version: str,
) -> WatchDetailFragmentPayload:
    """把詳情頁 read context 組成前端局部更新 payload。"""
    return WatchDetailFragmentPayload(
        version=version,
        sections=render_watch_detail_sections(
            watch_item=context.watch_item,
            latest_snapshot=context.latest_snapshot,
            check_events=context.check_events,
            notification_state=context.notification_state,
            debug_artifacts=context.debug_artifacts,
            runtime_state_events=context.runtime_state_events,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
    )
