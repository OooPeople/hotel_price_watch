"""本機 GUI renderer 的相容匯出入口。"""

from __future__ import annotations

from app.web.debug_views import (
    render_debug_capture_detail_page,
    render_debug_capture_list_page,
)
from app.web.settings_views import (
    render_notification_channel_settings_page,
    render_notification_settings_page,
)
from app.web.watch_creation_views import (
    render_chrome_tab_selection_page,
    render_new_watch_page,
)
from app.web.watch_views import (
    render_dashboard_summary_fragment,
    render_runtime_status_fragment,
    render_watch_detail_page,
    render_watch_detail_sections,
    render_watch_list_page,
    render_watch_list_rows_fragment,
)

__all__ = [
    "render_chrome_tab_selection_page",
    "render_debug_capture_detail_page",
    "render_debug_capture_list_page",
    "render_new_watch_page",
    "render_notification_channel_settings_page",
    "render_notification_settings_page",
    "render_dashboard_summary_fragment",
    "render_runtime_status_fragment",
    "render_watch_detail_page",
    "render_watch_detail_sections",
    "render_watch_list_page",
    "render_watch_list_rows_fragment",
]
