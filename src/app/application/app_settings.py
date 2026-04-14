"""全域設定頁 use case 與驗證邏輯。"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.config.models import NotificationChannelSettings


class NotificationChannelSettingsRepository:
    """描述全域通知通道設定的最小持久化介面。"""

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """讀取目前保存的全域通知通道設定。"""
        raise NotImplementedError

    def save_notification_channel_settings(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationChannelSettings:
        """保存全域通知通道設定。"""
        raise NotImplementedError


@dataclass(slots=True)
class AppSettingsService:
    """負責全域設定頁所需的讀寫與欄位驗證。"""

    settings_repository: NotificationChannelSettingsRepository

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """讀出目前已保存的全域通知通道設定。"""
        return self.settings_repository.get_notification_channel_settings()

    def update_notification_channel_settings(
        self,
        *,
        desktop_enabled: bool,
        ntfy_enabled: bool,
        ntfy_server_url: str,
        ntfy_topic: str | None,
        discord_enabled: bool,
        discord_webhook_url: str | None,
    ) -> NotificationChannelSettings:
        """驗證並保存全域通知通道設定。"""
        normalized_ntfy_server_url = ntfy_server_url.strip() or "https://ntfy.sh"
        normalized_ntfy_topic = _normalize_optional_text(ntfy_topic)
        normalized_discord_webhook_url = _normalize_optional_text(discord_webhook_url)

        _validate_http_url(
            normalized_ntfy_server_url,
            field_name="ntfy server URL",
        )
        if ntfy_enabled and normalized_ntfy_topic is None:
            raise ValueError("啟用 ntfy 時，必須填寫 topic。")
        if normalized_discord_webhook_url is not None:
            _validate_http_url(
                normalized_discord_webhook_url,
                field_name="Discord webhook URL",
            )
        if discord_enabled and normalized_discord_webhook_url is None:
            raise ValueError("啟用 Discord 時，必須填寫 webhook URL。")

        settings = NotificationChannelSettings(
            desktop_enabled=desktop_enabled,
            ntfy_enabled=ntfy_enabled,
            ntfy_server_url=normalized_ntfy_server_url,
            ntfy_topic=normalized_ntfy_topic,
            discord_enabled=discord_enabled,
            discord_webhook_url=normalized_discord_webhook_url,
        )
        return self.settings_repository.save_notification_channel_settings(settings)


def _normalize_optional_text(value: str | None) -> str | None:
    """把可選字串欄位整理成去空白後的值。"""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_http_url(value: str, *, field_name: str) -> None:
    """驗證通知相關 URL 必須是合法的 http/https 位址。"""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} 必須是合法的 http/https URL。")
