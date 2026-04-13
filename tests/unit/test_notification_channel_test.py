from __future__ import annotations

from app.application.app_settings import AppSettingsService
from app.application.notification_channel_test import NotificationChannelTestService
from app.config.models import NotificationChannelSettings
from app.notifiers.models import NotificationMessage


def test_test_notification_service_reuses_dispatcher_when_settings_unchanged() -> None:
    """全域測試通知在設定未變時應重用同一個 dispatcher。"""
    settings = NotificationChannelSettings(desktop_enabled=True)
    repository = _FakeSettingsRepository(settings)
    notifier_factory = _CountingNotifierFactory()
    service = NotificationChannelTestService(
        app_settings_service=AppSettingsService(repository),
        notifier_factory=notifier_factory,
    )

    service.send_test_notification()
    service.send_test_notification()

    assert notifier_factory.call_count == 1


def test_test_notification_service_rebuilds_dispatcher_after_settings_change() -> None:
    """全域設定變更後，測試通知應重建 dispatcher。"""
    repository = _FakeSettingsRepository(NotificationChannelSettings(desktop_enabled=True))
    notifier_factory = _CountingNotifierFactory()
    service = NotificationChannelTestService(
        app_settings_service=AppSettingsService(repository),
        notifier_factory=notifier_factory,
    )

    service.send_test_notification()
    repository.settings = NotificationChannelSettings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_topic="hotel-watch",
    )
    service.send_test_notification()

    assert notifier_factory.call_count == 2


class _FakeSettingsRepository:
    """提供測試通知 service 使用的最小設定替身。"""

    def __init__(self, settings: NotificationChannelSettings) -> None:
        self.settings = settings

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


class _CountingNotifierFactory:
    """記錄 factory 被呼叫次數，驗證 dispatcher 是否被重建。"""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(
        self,
        settings: NotificationChannelSettings,
    ) -> tuple["_FakeNotifier", ...]:
        """依設定建立最小 notifier 集合。"""
        self.call_count += 1
        if not settings.desktop_enabled:
            return ()
        return (_FakeNotifier(),)


class _FakeNotifier:
    """測試通知 service 的最小 notifier。"""

    channel_name = "desktop"

    def send(self, message: NotificationMessage) -> None:
        """接受訊息但不做任何外部操作。"""
        del message
