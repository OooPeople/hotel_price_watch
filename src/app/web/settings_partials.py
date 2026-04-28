"""設定頁 domain UI partial renderer。"""

from __future__ import annotations

from html import escape

from app.domain.enums import NotificationLeafKind
from app.web.client_contracts import SETTINGS_DOM_IDS
from app.web.settings_client_scripts import (
    render_notification_channel_toggle_script,
    render_notification_rule_toggle_script,
    render_time_format_exclusive_script,
)
from app.web.settings_presenters import (
    NotificationChannelSettingsPresentation,
    SettingsEditorPresentation,
    SettingsSummaryCardPresentation,
    SettingsTestActionPresentation,
    SettingsTestResultPresentation,
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
    meta_paragraph_style,
    muted_text_style,
    responsive_grid_style,
    stack_style,
    surface_card_style,
)


def render_watch_notification_rule_form_body(
    *,
    selected_kind: NotificationLeafKind,
    target_price_value: str,
) -> str:
    """渲染單一 watch 通知規則設定表單內容。"""
    target_price_wrapper_style = _notification_target_price_wrapper_style(selected_kind)
    return f"""
    <label>通知條件</label>
    <select
      id="{SETTINGS_DOM_IDS.notification_rule_kind}"
      name="notification_rule_kind"
      style="{input_style()}"
    >
      <option
        value="{NotificationLeafKind.ANY_DROP.value}"
        {"selected" if selected_kind == NotificationLeafKind.ANY_DROP else ""}
      >
        價格下降
      </option>
      <option
        value="{NotificationLeafKind.BELOW_TARGET_PRICE.value}"
        {"selected" if selected_kind == NotificationLeafKind.BELOW_TARGET_PRICE else ""}
      >
        低於目標價
      </option>
    </select>
    <div
      id="{SETTINGS_DOM_IDS.notification_target_price_wrapper}"
      style="{target_price_wrapper_style}"
    >
      <label>目標價（僅低於目標價時使用）</label>
      <input
        type="text"
        name="target_price"
        value="{target_price_value}"
        placeholder="例如 20000"
        style="{input_style()}"
      >
      {_render_notification_target_price_hint(selected_kind)}
    </div>
    {submit_button(label="儲存通知設定", kind="primary")}
    """


def render_watch_notification_rule_scripts() -> str:
    """渲染單一 watch 通知規則頁需要的 client script。"""
    return render_notification_rule_toggle_script(
        select_id=SETTINGS_DOM_IDS.notification_rule_kind,
        wrapper_id=SETTINGS_DOM_IDS.notification_target_price_wrapper,
    )


def render_notification_test_result_section(
    presentation: SettingsTestResultPresentation | None,
) -> str:
    """渲染測試通知結果摘要區塊。"""
    if presentation is None:
        return ""
    return card(
        title="測試通知結果",
        body=f"""
        <p style="margin:0;">成功通道：{escape(presentation.sent_text)}</p>
        <p style="margin:0;">節流通道：{escape(presentation.throttled_text)}</p>
        <p style="margin:0;">失敗通道：{escape(presentation.failed_text)}</p>
        <p style="margin:0;">失敗原因：{escape(presentation.details_text)}</p>
        """,
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


def render_test_notification_form(
    presentation: SettingsTestActionPresentation,
) -> str:
    """渲染測試通知表單。"""
    return form_card(
        action=presentation.action,
        body=f"""
        <h2 style="{card_title_style()}">{escape(presentation.title)}</h2>
        <p style="margin:0;">
          {escape(presentation.body)}
        </p>
        {submit_button(label=presentation.submit_label, kind="secondary")}
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


def _render_notification_target_price_hint(kind: NotificationLeafKind) -> str:
    """依目前選定的通知規則顯示目標價欄位提示。"""
    if kind is NotificationLeafKind.ANY_DROP:
        return (
            f'<p style="{meta_paragraph_style()}">'
            "目前為「價格下降」，目標價欄位會被忽略。"
            "</p>"
        )
    return (
        f'<p style="{meta_paragraph_style()}">'
        "只有當價格低於此門檻時才會通知。"
        "</p>"
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


def _notification_target_price_wrapper_style(kind: NotificationLeafKind) -> str:
    """依通知規則回傳目標價欄位容器的顯示樣式。"""
    display = "none" if kind is NotificationLeafKind.ANY_DROP else "grid"
    return f"display:{display};gap:8px;"


def _channel_wrapper_style(enabled: bool) -> str:
    """依通道是否啟用回傳設定區塊的顯示樣式。"""
    display = "grid" if enabled else "none"
    return f"display:{display};gap:8px;"
