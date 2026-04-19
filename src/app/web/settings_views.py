"""通知設定頁面的 HTML renderer。"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.config.models import NotificationChannelSettings
from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind
from app.web.view_helpers import (
    CARD_STYLE,
    ERROR_STYLE,
    SUCCESS_STYLE,
    input_style,
    page_layout,
    primary_button_style,
    secondary_button_style,
)


def render_notification_settings_page(
    *,
    watch_item: WatchItem,
    error_message: str | None = None,
    flash_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> str:
    """渲染單一 watch item 的通知設定頁。"""
    rule = watch_item.notification_rule
    form_values = form_values or {}
    selected_kind_value = form_values.get(
        "notification_rule_kind",
        getattr(rule, "kind", NotificationLeafKind.ANY_DROP).value,
    )
    selected_kind = NotificationLeafKind(selected_kind_value)
    if "target_price" in form_values:
        target_price_value = escape(form_values["target_price"])
    else:
        stored_target_price = getattr(rule, "target_price", None)
        target_price_value = (
            escape(_format_decimal_for_display(stored_target_price))
            if stored_target_price is not None
            else ""
        )
    error_html = (
        f'<p style="{ERROR_STYLE}">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    flash_html = (
        f'<p style="{SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    target_price_wrapper_style = _notification_target_price_wrapper_style(selected_kind)
    return page_layout(
        title=f"通知設定 - {watch_item.hotel_name}",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            <a href="/watches/{escape(watch_item.id)}" style="color:#0f766e;text-decoration:none;">
              ← 回 watch 詳細頁
            </a>
            <h1>通知設定</h1>
            <p>{escape(watch_item.hotel_name)} / {escape(watch_item.room_name)}</p>
            <p>{escape(watch_item.plan_name)}</p>
          </div>
          {error_html}
          {flash_html}
          <form
            action="/watches/{escape(watch_item.id)}/notification-settings"
            method="post"
            style="{CARD_STYLE}"
          >
            <label>通知條件</label>
            <select
              id="notification-rule-kind"
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
            <div id="notification-target-price-wrapper" style="{target_price_wrapper_style}">
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
            <button type="submit" style="{primary_button_style()}">儲存通知設定</button>
          </form>
          {_render_notification_rule_toggle_script(
              select_id="notification-rule-kind",
              wrapper_id="notification-target-price-wrapper",
          )}
        </section>
        """,
    )


def render_notification_channel_settings_page(
    *,
    settings: NotificationChannelSettings,
    error_message: str | None = None,
    flash_message: str | None = None,
    test_result_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> str:
    """渲染主頁層級的全域通知通道設定頁。"""
    form_values = form_values or {}
    desktop_enabled = _form_checkbox_value(
        form_values,
        key="desktop_enabled",
        fallback=settings.desktop_enabled,
    )
    ntfy_enabled = _form_checkbox_value(
        form_values,
        key="ntfy_enabled",
        fallback=settings.ntfy_enabled,
    )
    discord_enabled = _form_checkbox_value(
        form_values,
        key="discord_enabled",
        fallback=settings.discord_enabled,
    )
    ntfy_server_url = escape(
        form_values.get("ntfy_server_url", settings.ntfy_server_url)
    )
    ntfy_topic = escape(form_values.get("ntfy_topic", settings.ntfy_topic or ""))
    discord_webhook_url = escape(
        form_values.get("discord_webhook_url", settings.discord_webhook_url or "")
    )
    error_html = (
        f'<p style="{ERROR_STYLE}">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    flash_html = (
        f'<p style="{SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    test_result_html = _render_notification_test_result_section(test_result_message)
    return page_layout(
        title="全域通知設定",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            <a href="/" style="color:#0f766e;text-decoration:none;">← 回列表</a>
            <h1>全域通知設定</h1>
            <p>這裡設定通知要送到哪些通道；單一 watch 頁面只負責通知規則，不負責 webhook/topic。</p>
          </div>
          {error_html}
          {flash_html}
          {test_result_html}
          <form action="/settings/notifications" method="post" style="{CARD_STYLE}">
            <label style="display:flex;gap:8px;align-items:center;">
              <input type="checkbox" name="desktop_enabled" {"checked" if desktop_enabled else ""}>
              啟用本機桌面通知
            </label>
            <label style="display:flex;gap:8px;align-items:center;">
              <input
                id="global-ntfy-enabled"
                type="checkbox"
                name="ntfy_enabled"
                {"checked" if ntfy_enabled else ""}
              >
              啟用 ntfy
            </label>
            <div
              id="global-ntfy-settings"
              style="{_channel_wrapper_style(ntfy_enabled)}"
            >
              <label>ntfy Server URL</label>
              <input
                type="text"
                name="ntfy_server_url"
                value="{ntfy_server_url}"
                placeholder="https://ntfy.sh"
                style="{input_style()}"
              >
              <label>ntfy Topic</label>
              <input
                type="text"
                name="ntfy_topic"
                value="{ntfy_topic}"
                placeholder="例如 hotel-watch"
                style="{input_style()}"
              >
            </div>
            <label style="display:flex;gap:8px;align-items:center;">
              <input
                id="global-discord-enabled"
                type="checkbox"
                name="discord_enabled"
                {"checked" if discord_enabled else ""}
              >
              啟用 Discord webhook
            </label>
            <div
              id="global-discord-settings"
              style="{_channel_wrapper_style(discord_enabled)}"
            >
              <label>Discord Webhook URL</label>
              <input
                type="text"
                name="discord_webhook_url"
                value="{discord_webhook_url}"
                placeholder="https://discord.com/api/webhooks/..."
                style="{input_style()}"
              >
            </div>
            <button type="submit" style="{primary_button_style()}">儲存全域通知設定</button>
          </form>
          <form action="/settings/notifications/test" method="post" style="{CARD_STYLE}">
            <h2 style="margin:0;">測試通知</h2>
            <p style="margin:0;">
              會使用目前已保存的全域通知設定，走正式 notifier / dispatcher 路徑送出一則測試訊息。
            </p>
            <button type="submit" style="{secondary_button_style()}">發送測試通知</button>
          </form>
          {_render_checkbox_toggle_script(
              checkbox_id="global-ntfy-enabled",
              wrapper_id="global-ntfy-settings",
          )}
          {_render_checkbox_toggle_script(
              checkbox_id="global-discord-enabled",
              wrapper_id="global-discord-settings",
          )}
        </section>
        """,
    )


def _format_decimal_for_display(amount) -> str:
    """把 Decimal 數字格式化成較適合 GUI 顯示的文字。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")


def _render_notification_target_price_hint(kind: NotificationLeafKind) -> str:
    """依目前選定的通知規則顯示目標價欄位提示。"""
    if kind is NotificationLeafKind.ANY_DROP:
        return (
            '<p style="margin:0;color:#4b635f;">'
            "目前為「價格下降」，目標價欄位會被忽略。"
            "</p>"
        )
    return (
        '<p style="margin:0;color:#4b635f;">'
        "只有當價格低於此門檻時才會通知。"
        "</p>"
    )


def _render_notification_test_result_section(test_result_message: str | None) -> str:
    """把測試通知結果整理成較易讀的摘要區塊。"""
    if not test_result_message:
        return ""

    sent_text = _extract_test_result_segment(test_result_message, "sent")
    throttled_text = _extract_test_result_segment(test_result_message, "throttled")
    failed_text = _extract_test_result_segment(test_result_message, "failed")
    details_text = _extract_test_result_segment(test_result_message, "details")
    return f"""
    <section style="{CARD_STYLE}">
      <h2 style="margin:0;">測試通知結果</h2>
      <p style="margin:0;">成功通道：{escape(sent_text or "none")}</p>
      <p style="margin:0;">節流通道：{escape(throttled_text or "none")}</p>
      <p style="margin:0;">失敗通道：{escape(failed_text or "none")}</p>
      <p style="margin:0;">失敗原因：{escape(details_text or "none")}</p>
    </section>
    """


def _extract_test_result_segment(message: str, key: str) -> str:
    """從 redirect 的測試通知摘要中取出指定欄位內容。"""
    marker = f"{key}="
    if marker not in message:
        return ""

    suffix = message.split(marker, 1)[1]
    for separator in ("；", ";"):
        if separator in suffix:
            return suffix.split(separator, 1)[0].strip()
    return suffix.strip()


def _notification_target_price_wrapper_style(kind: NotificationLeafKind) -> str:
    """依通知規則回傳目標價欄位容器的顯示樣式。"""
    display = "none" if kind is NotificationLeafKind.ANY_DROP else "grid"
    return f"display:{display};gap:8px;"


def _channel_wrapper_style(enabled: bool) -> str:
    """依通道是否啟用回傳設定區塊的顯示樣式。"""
    display = "grid" if enabled else "none"
    return f"display:{display};gap:8px;"


def _render_notification_rule_toggle_script(*, select_id: str, wrapper_id: str) -> str:
    """渲染通知規則切換腳本，控制目標價欄位顯示與隱藏。"""
    any_drop_value = NotificationLeafKind.ANY_DROP.value
    return f"""
    <script>
      (() => {{
        const select = document.getElementById("{escape(select_id)}");
        const wrapper = document.getElementById("{escape(wrapper_id)}");
        if (!select || !wrapper) {{
          return;
        }}

        const syncTargetPriceVisibility = () => {{
          wrapper.style.display = select.value === "{escape(any_drop_value)}" ? "none" : "grid";
        }};

        syncTargetPriceVisibility();
        select.addEventListener("change", syncTargetPriceVisibility);
      }})();
    </script>
    """


def _render_checkbox_toggle_script(*, checkbox_id: str, wrapper_id: str) -> str:
    """渲染 checkbox 切換腳本，用於控制通道設定區塊顯示。"""
    return f"""
    <script>
      (() => {{
        const checkbox = document.getElementById("{escape(checkbox_id)}");
        const wrapper = document.getElementById("{escape(wrapper_id)}");
        if (!checkbox || !wrapper) {{
          return;
        }}

        const syncVisibility = () => {{
          wrapper.style.display = checkbox.checked ? "grid" : "none";
        }};

        syncVisibility();
        checkbox.addEventListener("change", syncVisibility);
      }})();
    </script>
    """


def _form_checkbox_value(
    form_values: dict[str, str],
    *,
    key: str,
    fallback: bool,
) -> bool:
    """依表單回填資料或既有設定決定 checkbox 是否勾選。"""
    if key not in form_values:
        return fallback
    return form_values[key] == "on"
