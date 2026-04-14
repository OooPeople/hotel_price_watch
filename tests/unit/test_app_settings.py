from __future__ import annotations

import pytest

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings


class _FakeSettingsRepository:
    """提供 AppSettingsService 測試使用的最小設定替身。"""

    def __init__(self) -> None:
        self.settings = NotificationChannelSettings()

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """回傳目前保存的設定。"""
        return self.settings

    def save_notification_channel_settings(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationChannelSettings:
        """保存設定並回傳新值。"""
        self.settings = settings
        return settings


def test_update_notification_channel_settings_rejects_invalid_ntfy_server_url() -> None:
    """ntfy server URL 若不是合法 http/https 位址，應被後端拒絕。"""
    service = AppSettingsService(_FakeSettingsRepository())

    with pytest.raises(ValueError):
        service.update_notification_channel_settings(
            desktop_enabled=True,
            ntfy_enabled=False,
            ntfy_server_url="javascript:alert(1)",
            ntfy_topic=None,
            discord_enabled=False,
            discord_webhook_url=None,
        )


def test_update_notification_channel_settings_rejects_invalid_discord_webhook_url() -> None:
    """Discord webhook URL 若不是合法 http/https 位址，應被後端拒絕。"""
    service = AppSettingsService(_FakeSettingsRepository())

    with pytest.raises(ValueError):
        service.update_notification_channel_settings(
            desktop_enabled=True,
            ntfy_enabled=False,
            ntfy_server_url="https://ntfy.sh",
            ntfy_topic=None,
            discord_enabled=True,
            discord_webhook_url="file:///tmp/webhook.txt",
        )


def test_update_notification_channel_settings_accepts_valid_http_urls() -> None:
    """合法的通知 URL 應能正常保存。"""
    service = AppSettingsService(_FakeSettingsRepository())

    settings = service.update_notification_channel_settings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_server_url="https://ntfy.example.com",
        ntfy_topic="hotel-watch",
        discord_enabled=True,
        discord_webhook_url="https://discord.example.com/api/webhooks/1/2",
    )

    assert settings.ntfy_server_url == "https://ntfy.example.com"
    assert settings.discord_webhook_url == "https://discord.example.com/api/webhooks/1/2"
