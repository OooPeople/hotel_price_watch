"""全域設定頁 summary、editor 與 scripts partial renderer。"""

from __future__ import annotations

from html import escape

from app.web.client_contracts import SETTINGS_DOM_IDS
from app.web.settings_client_scripts import (
    render_notification_channel_toggle_script,
    render_time_format_exclusive_script,
)
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
    unsaved_changes_script,
)
from app.web.ui_styles import (
    card_title_style,
    color_token,
    input_style,
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
    """渲染全域設定頁需要的 client scripts。"""
    return (
        render_notification_channel_toggle_script(
            checkbox_id=SETTINGS_DOM_IDS.global_ntfy_enabled,
            wrapper_id=SETTINGS_DOM_IDS.global_ntfy_settings,
        )
        + render_notification_channel_toggle_script(
            checkbox_id=SETTINGS_DOM_IDS.global_discord_enabled,
            wrapper_id=SETTINGS_DOM_IDS.global_discord_settings,
        )
        + render_time_format_exclusive_script(
            first_checkbox_id=SETTINGS_DOM_IDS.time_format_12h,
            second_checkbox_id=SETTINGS_DOM_IDS.time_format_24h,
        )
        + unsaved_changes_script(form_id=SETTINGS_DOM_IDS.global_settings_form)
    )


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
    details_style = surface_card_style(gap="12px", padding="16px")
    return f"""
    <details open style="{details_style}">
      <summary style="cursor:pointer;font-weight:700;">顯示偏好</summary>
      <div style="{stack_style(gap="md")}margin-top:12px;">
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
          <label style="display:flex;gap:8px;align-items:center;">
            <input
              id="{SETTINGS_DOM_IDS.time_format_12h}"
              type="checkbox"
              name="time_format_12h"
              {"checked" if not use_24_hour_time else ""}
            >
            12 小時制
          </label>
          <label style="display:flex;gap:8px;align-items:center;">
            <input
              id="{SETTINGS_DOM_IDS.time_format_24h}"
              type="checkbox"
              name="time_format_24h"
              {"checked" if use_24_hour_time else ""}
            >
            24 小時制
          </label>
        </div>
      </div>
    </details>
    """


def _render_notification_channels_editor(
    presentation: SettingsEditorPresentation,
) -> str:
    """渲染通知通道的展開編輯區，保留既有欄位名稱。"""
    details_style = surface_card_style(gap="12px", padding="16px")
    channel_section_style = surface_card_style(gap="8px", padding="14px")
    return f"""
    <details open style="{details_style}">
      <summary style="cursor:pointer;font-weight:700;">通知通道</summary>
      <div style="{stack_style(gap="lg")}margin-top:12px;">
        <label style="display:flex;gap:8px;align-items:center;">
          <input
            type="checkbox"
            name="desktop_enabled"
            {"checked" if presentation.desktop_enabled else ""}
          >
          啟用本機桌面通知
        </label>
        <section style="{channel_section_style}">
          <label style="display:flex;gap:8px;align-items:center;">
            <input
              id="{SETTINGS_DOM_IDS.global_ntfy_enabled}"
              type="checkbox"
              name="ntfy_enabled"
              {"checked" if presentation.ntfy_enabled else ""}
            >
            啟用 ntfy
          </label>
          <div
            id="{SETTINGS_DOM_IDS.global_ntfy_settings}"
            style="{_channel_wrapper_style(presentation.ntfy_enabled)}"
          >
            <label>ntfy Server URL</label>
            <input
              type="text"
              name="ntfy_server_url"
              value="{escape(presentation.ntfy_server_url)}"
              placeholder="https://ntfy.sh"
              style="{input_style()}"
            >
            <label>ntfy Topic</label>
            <input
              type="text"
              name="ntfy_topic"
              value="{escape(presentation.ntfy_topic)}"
              placeholder="例如 hotel-watch"
              style="{input_style()}"
            >
          </div>
        </section>
        <section style="{channel_section_style}">
          <label style="display:flex;gap:8px;align-items:center;">
            <input
              id="{SETTINGS_DOM_IDS.global_discord_enabled}"
              type="checkbox"
              name="discord_enabled"
              {"checked" if presentation.discord_enabled else ""}
            >
            啟用 Discord webhook
          </label>
          <p style="margin:0;{muted_text_style(font_size="13px")}">
            摘要會遮罩 webhook；展開編輯區才顯示完整輸入值。
          </p>
          <div
            id="{SETTINGS_DOM_IDS.global_discord_settings}"
            style="{_channel_wrapper_style(presentation.discord_enabled)}"
          >
            <label>Discord Webhook URL</label>
            <input
              type="text"
              name="discord_webhook_url"
              value="{escape(presentation.discord_webhook_url)}"
              placeholder="https://discord.com/api/webhooks/..."
              style="{input_style()}"
            >
          </div>
        </section>
      </div>
    </details>
    """


def _channel_wrapper_style(enabled: bool) -> str:
    """依通道是否啟用回傳設定區塊的顯示樣式。"""
    display = "grid" if enabled else "none"
    return f"display:{display};gap:8px;"
