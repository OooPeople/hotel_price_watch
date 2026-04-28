"""本機 GUI 共用 HTML component 的相容匯出入口。"""

from __future__ import annotations

from app.web.ui_icons import icon_svg
from app.web.ui_layout import page_layout
from app.web.ui_primitives import (
    action_row,
    button_style,
    card,
    collapsible_section,
    data_table,
    empty_state_card,
    flash_message,
    form_card,
    key_value_grid,
    link_button,
    notice_box,
    page_header,
    section_header,
    status_badge,
    submit_button,
    summary_card,
    table_cell,
    table_row,
    text_link,
    unsaved_changes_indicator,
    unsaved_changes_script,
)

__all__ = [
    "action_row",
    "button_style",
    "card",
    "collapsible_section",
    "data_table",
    "empty_state_card",
    "flash_message",
    "form_card",
    "icon_svg",
    "key_value_grid",
    "link_button",
    "notice_box",
    "page_header",
    "page_layout",
    "section_header",
    "status_badge",
    "submit_button",
    "summary_card",
    "table_cell",
    "table_row",
    "text_link",
    "unsaved_changes_indicator",
    "unsaved_changes_script",
]
