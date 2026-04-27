"""全域設定頁使用的 presentation model。"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.models import DisplaySettings, NotificationChannelSettings


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


def _mask_sensitive_value(value: str) -> str:
    """遮罩敏感設定摘要，避免 webhook 或 token 在摘要卡裸露。"""
    if not value:
        return "未設定"
    if len(value) <= 12:
        return "已設定"
    return f"{value[:18]}...{value[-6:]}"
