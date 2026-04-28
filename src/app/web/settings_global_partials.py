"""全域設定頁 summary、editor 與 scripts partial renderer。"""

from __future__ import annotations

from html import escape

from app.web.client_contracts import SETTINGS_DOM_IDS
from app.web.settings_page_scripts import render_global_settings_page_scripts
from app.web.settings_presenters import (
    NotificationChannelSettingsPresentation,
    SettingsEditorPresentation,
    SettingsSummaryCardPresentation,
)
from app.web.ui_components import (
    card,
    form_card,
    section_header,
    status_badge,
    submit_button,
    unsaved_changes_indicator,
)
from app.web.ui_page_sections import (
    checkbox_label,
    details_panel,
    field_stack_style,
    inline_cluster,
    text_input,
)
from app.web.ui_styles import (
    card_title_style,
    color_token,
    muted_text_style,
    responsive_grid_style,
    stack_style,
    surface_card_style,
)


def render_global_settings_summary(
    presentation: NotificationChannelSettingsPresentation,
) -> str:
    """渲染設定頁摘要卡，避免一進頁面就看到大量輸入欄位。"""
    return f"""
    <section style="{stack_style(gap="lg")}">
      {section_header(title="設定摘要", subtitle="快速確認目前顯示偏好與通知通道狀態。")}
      <div style="{responsive_grid_style(min_width="210px", gap="14px")}">
        {"".join(_render_settings_summary_card(card) for card in presentation.summary_cards)}
      </div>
    </section>
    """


def render_global_settings_editor_form(
    presentation: SettingsEditorPresentation,
) -> str:
    """渲染全域設定編輯表單。"""
    return form_card(
        action=presentation.action,
        form_id=presentation.form_id,
        body=f"""
        {section_header(title="編輯設定", subtitle="展開需要修改的區塊；摘要會在儲存後更新。")}
        {_render_display_settings_editor(
            use_24_hour_time=presentation.use_24_hour_time,
        )}
        {_render_notification_channels_editor(presentation)}
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          {submit_button(label=presentation.submit_label, kind="primary")}
          {unsaved_changes_indicator()}
        </div>
        """,
    )


def render_global_settings_scripts() -> str:
    """相容舊入口，委派到設定頁 page-level script entrypoint。"""
    return render_global_settings_page_scripts()


def _render_settings_summary_card(
    presentation: SettingsSummaryCardPresentation,
) -> str:
    """渲染單張設定摘要卡。"""
    badge = status_badge(
        label="已啟用" if presentation.enabled else "未啟用",
        kind="success" if presentation.enabled else "muted",
    )
    return card(
        body=f"""
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:start;">
          <h3 style="{card_title_style()}">{escape(presentation.title)}</h3>
          {badge}
        </div>
        <p style="margin:0;color:{color_token("text")};">{escape(presentation.body)}</p>
        <p style="margin:0;{muted_text_style(font_size="13px")}">{escape(presentation.helper)}</p>
        """,
    )


def _render_display_settings_editor(*, use_24_hour_time: bool) -> str:
    """渲染顯示偏好的展開編輯區。"""
    return details_panel(
        title="顯示偏好",
        body=inline_cluster(
            checkbox_label(
                input_html=f"""
            <input
              id="{SETTINGS_DOM_IDS.time_format_12h}"
              type="checkbox"
              name="time_format_12h"
              {"checked" if not use_24_hour_time else ""}
            >
            """,
                label="12 小時制",
            )
            + checkbox_label(
                input_html=f"""
            <input
              id="{SETTINGS_DOM_IDS.time_format_24h}"
              type="checkbox"
              name="time_format_24h"
              {"checked" if use_24_hour_time else ""}
            >
            """,
                label="24 小時制",
            ),
            gap="lg",
        ),
    )


def _render_notification_channels_editor(
    presentation: SettingsEditorPresentation,
) -> str:
    """渲染通知通道的展開編輯區，保留既有欄位名稱。"""
    channel_section_style = surface_card_style(gap="8px", padding="14px")
    return details_panel(
        title="通知通道",
        body=f"""
        {checkbox_label(
            input_html=f'''
          <input
            type="checkbox"
            name="desktop_enabled"
            {"checked" if presentation.desktop_enabled else ""}
          >
          ''',
            label="啟用本機桌面通知",
        )}
        <section style="{channel_section_style}">
          {checkbox_label(
              input_html=f'''
            <input
              id="{SETTINGS_DOM_IDS.global_ntfy_enabled}"
              type="checkbox"
              name="ntfy_enabled"
              {"checked" if presentation.ntfy_enabled else ""}
            >
            ''',
              label="啟用 ntfy",
          )}
          <div
            id="{SETTINGS_DOM_IDS.global_ntfy_settings}"
            style="{_channel_wrapper_style(presentation.ntfy_enabled)}"
          >
            <label>ntfy Server URL</label>
            {text_input(
              name="ntfy_server_url",
              value=presentation.ntfy_server_url,
              placeholder="https://ntfy.sh",
            )}
            <label>ntfy Topic</label>
            {text_input(
              name="ntfy_topic",
              value=presentation.ntfy_topic,
              placeholder="例如 hotel-watch",
            )}
          </div>
        </section>
        <section style="{channel_section_style}">
          {checkbox_label(
              input_html=f'''
            <input
              id="{SETTINGS_DOM_IDS.global_discord_enabled}"
              type="checkbox"
              name="discord_enabled"
              {"checked" if presentation.discord_enabled else ""}
            >
            ''',
              label="啟用 Discord webhook",
          )}
          <p style="margin:0;{muted_text_style(font_size="13px")}">
            摘要會遮罩 webhook；展開編輯區才顯示完整輸入值。
          </p>
          <div
            id="{SETTINGS_DOM_IDS.global_discord_settings}"
            style="{_channel_wrapper_style(presentation.discord_enabled)}"
          >
            <label>Discord Webhook URL</label>
            {text_input(
              name="discord_webhook_url",
              value=presentation.discord_webhook_url,
              placeholder="https://discord.com/api/webhooks/...",
            )}
          </div>
        </section>
        """,
    )


def _channel_wrapper_style(enabled: bool) -> str:
    """依通道是否啟用回傳設定區塊的顯示樣式。"""
    return field_stack_style(visible=enabled)
