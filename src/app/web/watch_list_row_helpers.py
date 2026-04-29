"""Dashboard watch row renderer 共用 helper。"""

from __future__ import annotations

from html import escape

from app.web.ui_components import status_badge
from app.web.ui_page_sections import block_nowrap_style
from app.web.ui_presenters import BadgePresentation, WatchRowPresentation
from app.web.ui_styles import muted_text_style


def render_presentation_badge_html(presentation: BadgePresentation | None) -> str:
    """把 presenter badge 轉成共用 badge HTML，允許缺值。"""
    if presentation is None:
        return ""
    return status_badge(label=presentation.label, kind=presentation.kind)


def render_last_checked_relative_html(row: WatchRowPresentation) -> str:
    """渲染可由前端自行更新的最後檢查相對時間。"""
    timestamp_attr = (
        f' data-relative-time="{escape(row.last_checked_at_iso)}"'
        if row.last_checked_at_iso is not None
        else ""
    )
    return (
        f'<strong{timestamp_attr} style="{block_nowrap_style()}">'
        f"{escape(row.last_checked_relative_text)}</strong>"
    )


def render_runtime_state_helper_html(row: WatchRowPresentation) -> str:
    """渲染狀態輔助文字；退避倒數可由前端自行更新。"""
    if not row.runtime_state_helper_text:
        return ""
    countdown_attr = (
        f' data-countdown-time="{escape(row.runtime_state_helper_target_iso)}"'
        if row.runtime_state_helper_target_iso is not None
        else ""
    )
    return (
        f'<span{countdown_attr} '
        f'style="{block_nowrap_style(muted_text_style(font_size="12px"))}">'
        f"{escape(row.runtime_state_helper_text)}</span>"
    )
