"""設定頁測試通知相關 partial renderer。"""

from __future__ import annotations

from html import escape

from app.web.settings_presenters import (
    SettingsTestActionPresentation,
    SettingsTestResultPresentation,
)
from app.web.ui_components import card, form_card, submit_button
from app.web.ui_page_sections import zero_margin_style
from app.web.ui_styles import card_title_style


def render_notification_test_result_section(
    presentation: SettingsTestResultPresentation | None,
) -> str:
    """渲染測試通知結果摘要區塊。"""
    if presentation is None:
        return ""
    result_line_style = zero_margin_style()
    return card(
        title="測試通知結果",
        body=f"""
        <p style="{result_line_style}">成功通道：{escape(presentation.sent_text)}</p>
        <p style="{result_line_style}">節流通道：{escape(presentation.throttled_text)}</p>
        <p style="{result_line_style}">失敗通道：{escape(presentation.failed_text)}</p>
        <p style="{result_line_style}">失敗原因：{escape(presentation.details_text)}</p>
        """,
    )


def render_test_notification_form(
    presentation: SettingsTestActionPresentation,
) -> str:
    """渲染測試通知表單。"""
    body_style = zero_margin_style()
    return form_card(
        action=presentation.action,
        body=f"""
        <h2 style="{card_title_style()}">{escape(presentation.title)}</h2>
        <p style="{body_style}">
          {escape(presentation.body)}
        </p>
        {submit_button(label=presentation.submit_label, kind="secondary")}
        """,
    )
