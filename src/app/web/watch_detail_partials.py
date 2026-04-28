"""watch detail 專用 partial renderer 相容匯出入口。"""

from __future__ import annotations

from app.web.watch_action_partials import render_watch_action_controls
from app.web.watch_detail_history_partials import (
    render_check_events_section,
    render_check_events_section_with_time_format,
    render_debug_artifacts_section,
    render_debug_artifacts_section_with_time_format,
    render_runtime_state_events_section,
    render_runtime_state_events_section_with_time_format,
)
from app.web.watch_detail_summary_partials import (
    render_watch_detail_hero_section,
    render_watch_price_summary_cards,
)
from app.web.watch_detail_trend_partials import render_price_trend_section_with_time_format

__all__ = [
    "render_check_events_section",
    "render_check_events_section_with_time_format",
    "render_debug_artifacts_section",
    "render_debug_artifacts_section_with_time_format",
    "render_price_trend_section_with_time_format",
    "render_runtime_state_events_section",
    "render_runtime_state_events_section_with_time_format",
    "render_watch_action_controls",
    "render_watch_detail_hero_section",
    "render_watch_price_summary_cards",
]
