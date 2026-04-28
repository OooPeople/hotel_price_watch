"""全域設定頁使用的 presentation model。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind


@dataclass(frozen=True, slots=True)
class SettingsSummaryCardPresentation:
    """描述設定摘要卡需要的顯示資料。"""

    title: str
    enabled: bool
    body: str
    helper: str


@dataclass(frozen=True, slots=True)
class NotificationChannelSettingsPresentation:
    """集中全域通知與顯示設定頁需要的顯示資料。"""

    desktop_enabled: bool
    ntfy_enabled: bool
    ntfy_server_url: str
    ntfy_topic: str
    discord_enabled: bool
    discord_webhook_url: str
    masked_discord_webhook_url: str
    use_24_hour_time: bool
    summary_cards: tuple[SettingsSummaryCardPresentation, ...]


@dataclass(frozen=True, slots=True)
class SettingsEditorPresentation:
    """描述全域設定編輯表單需要的欄位值與 action 狀態。"""

    form_id: str
    action: str
    submit_label: str
    use_24_hour_time: bool
    desktop_enabled: bool
    ntfy_enabled: bool
    ntfy_server_url: str
    ntfy_topic: str
    discord_enabled: bool
    discord_webhook_url: str


@dataclass(frozen=True, slots=True)
class SettingsTestResultPresentation:
    """描述測試通知結果區塊需要的結構化顯示資料。"""

    sent_text: str
    throttled_text: str
    failed_text: str
    details_text: str


@dataclass(frozen=True, slots=True)
class SettingsTestActionPresentation:
    """描述測試通知表單的 action 與按鈕文案。"""

    action: str
    title: str
    body: str
    submit_label: str


@dataclass(frozen=True, slots=True)
class SettingsPageViewModel:
    """集中全域設定頁 renderer 需要的 presentation 與訊息狀態。"""

    channel_settings: NotificationChannelSettingsPresentation
    editor: SettingsEditorPresentation
    test_action: SettingsTestActionPresentation
    test_result: SettingsTestResultPresentation | None
    error_message: str | None
    flash_message: str | None


@dataclass(frozen=True, slots=True)
class WatchNotificationRulePresentation:
    """集中單一 watch 通知規則頁的表單回填資料。"""

    watch_id: str
    hotel_name: str
    room_name: str
    selected_kind: NotificationLeafKind
    target_price_value: str
    error_message: str | None
    flash_message: str | None


def build_settings_page_view_model(
    *,
    settings: NotificationChannelSettings,
    display_settings: DisplaySettings,
    error_message: str | None = None,
    flash_message: str | None = None,
    test_result_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> SettingsPageViewModel:
    """把全域設定頁 context 轉成頁面級 view model。"""
    channel_settings = build_notification_channel_settings_presentation(
        settings=settings,
        display_settings=display_settings,
        form_values=form_values,
    )
    return SettingsPageViewModel(
        channel_settings=channel_settings,
        editor=build_settings_editor_presentation(channel_settings),
        test_action=SettingsTestActionPresentation(
            action="/settings/test-notification",
            title="測試通知",
            body=(
                "會使用目前已保存的通知通道設定，"
                "走正式 notifier / dispatcher 路徑送出一則測試訊息。"
            ),
            submit_label="發送測試通知",
        ),
        test_result=parse_settings_test_result_message(test_result_message),
        error_message=error_message,
        flash_message=flash_message,
    )


def build_settings_editor_presentation(
    channel_settings: NotificationChannelSettingsPresentation,
) -> SettingsEditorPresentation:
    """從通道設定 presentation 建立全域設定表單 view model。"""
    return SettingsEditorPresentation(
        form_id="global-settings-form",
        action="/settings",
        submit_label="儲存設定",
        use_24_hour_time=channel_settings.use_24_hour_time,
        desktop_enabled=channel_settings.desktop_enabled,
        ntfy_enabled=channel_settings.ntfy_enabled,
        ntfy_server_url=channel_settings.ntfy_server_url,
        ntfy_topic=channel_settings.ntfy_topic,
        discord_enabled=channel_settings.discord_enabled,
        discord_webhook_url=channel_settings.discord_webhook_url,
    )


def parse_settings_test_result_message(
    test_result_message: str | None,
) -> SettingsTestResultPresentation | None:
    """把 redirect query 中的測試通知摘要轉成結構化 presentation。"""
    if not test_result_message:
        return None
    return SettingsTestResultPresentation(
        sent_text=_extract_test_result_segment(test_result_message, "sent") or "none",
        throttled_text=(
            _extract_test_result_segment(test_result_message, "throttled") or "none"
        ),
        failed_text=_extract_test_result_segment(test_result_message, "failed") or "none",
        details_text=_extract_test_result_segment(test_result_message, "details")
        or "none",
    )


def build_watch_notification_rule_presentation(
    *,
    watch_item: WatchItem,
    error_message: str | None = None,
    flash_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> WatchNotificationRulePresentation:
    """把單一 watch 通知設定 context 轉成表單 view model。"""
    rule = watch_item.notification_rule
    form_values = form_values or {}
    selected_kind_value = form_values.get(
        "notification_rule_kind",
        getattr(rule, "kind", NotificationLeafKind.ANY_DROP).value,
    )
    selected_kind = NotificationLeafKind(selected_kind_value)
    if "target_price" in form_values:
        target_price_value = form_values["target_price"]
    else:
        stored_target_price = getattr(rule, "target_price", None)
        target_price_value = (
            _format_decimal_for_display(stored_target_price)
            if stored_target_price is not None
            else ""
        )
    return WatchNotificationRulePresentation(
        watch_id=watch_item.id,
        hotel_name=watch_item.hotel_name,
        room_name=watch_item.room_name,
        selected_kind=selected_kind,
        target_price_value=target_price_value,
        error_message=error_message,
        flash_message=flash_message,
    )


def build_notification_channel_settings_presentation(
    *,
    settings: NotificationChannelSettings,
    display_settings: DisplaySettings,
    form_values: dict[str, str] | None = None,
) -> NotificationChannelSettingsPresentation:
    """把保存設定與表單回填值整理成設定頁 view model。"""
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
    use_24_hour_time = _form_time_format_value(
        form_values,
        fallback=display_settings.use_24_hour_time,
    )
    ntfy_server_url = form_values.get("ntfy_server_url", settings.ntfy_server_url)
    ntfy_topic = form_values.get("ntfy_topic", settings.ntfy_topic or "")
    discord_webhook_url = form_values.get(
        "discord_webhook_url",
        settings.discord_webhook_url or "",
    )
    masked_discord_webhook_url = _mask_sensitive_value(discord_webhook_url)
    return NotificationChannelSettingsPresentation(
        desktop_enabled=desktop_enabled,
        ntfy_enabled=ntfy_enabled,
        ntfy_server_url=ntfy_server_url,
        ntfy_topic=ntfy_topic,
        discord_enabled=discord_enabled,
        discord_webhook_url=discord_webhook_url,
        masked_discord_webhook_url=masked_discord_webhook_url,
        use_24_hour_time=use_24_hour_time,
        summary_cards=(
            SettingsSummaryCardPresentation(
                title="時間顯示",
                enabled=True,
                body="24 小時制" if use_24_hour_time else "12 小時制",
                helper="會套用到列表、詳情與 debug 時間。",
            ),
            SettingsSummaryCardPresentation(
                title="桌面通知",
                enabled=desktop_enabled,
                body="目前裝置的本機通知。",
                helper="測試通知會走正式 dispatcher。",
            ),
            SettingsSummaryCardPresentation(
                title="ntfy",
                enabled=ntfy_enabled,
                body=f"Topic：{ntfy_topic or '未設定'}",
                helper=f"Server：{ntfy_server_url or '未設定'}",
            ),
            SettingsSummaryCardPresentation(
                title="Discord",
                enabled=discord_enabled,
                body=masked_discord_webhook_url,
                helper="Webhook URL 摘要已遮罩。",
            ),
        ),
    )


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


def _form_time_format_value(
    form_values: dict[str, str],
    *,
    fallback: bool,
) -> bool:
    """依表單回填資料或既有設定決定時間格式是否為 24 小時制。"""
    has_12h = "time_format_12h" in form_values
    has_24h = "time_format_24h" in form_values
    if not has_12h and not has_24h and "use_24_hour_time" in form_values:
        return form_values["use_24_hour_time"] == "on"
    if not has_12h and not has_24h:
        return fallback
    return has_24h


def _extract_test_result_segment(message: str, key: str) -> str:
    """從測試通知摘要中取出指定欄位內容。"""
    marker = f"{key}="
    if marker not in message:
        return ""

    suffix = message.split(marker, 1)[1]
    for separator in ("；", ";"):
        if separator in suffix:
            return suffix.split(separator, 1)[0].strip()
    return suffix.strip()


def _mask_sensitive_value(value: str) -> str:
    """遮罩敏感設定摘要，避免 webhook 或 token 在摘要卡裸露。"""
    if not value:
        return "未設定"
    if len(value) <= 12:
        return "已設定"
    return f"{value[:18]}...{value[-6:]}"


def _format_decimal_for_display(amount: Decimal) -> str:
    """把 Decimal 數字格式化成表單欄位適用文字。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")
