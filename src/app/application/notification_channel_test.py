"""全域通知通道測試用的 application service。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import NotificationDispatchResult
from app.notifiers import (
    InMemoryNotificationThrottle,
    NotificationDispatcher,
    NotificationMessage,
)
from app.notifiers.base import Notifier

NotifierFactory = Callable[[object], tuple[Notifier, ...]]


@dataclass(slots=True)
class NotificationChannelTestService:
    """使用正式 notifier / dispatcher 路徑發送全域測試通知。"""

    app_settings_service: AppSettingsService
    notifier_factory: NotifierFactory
    throttle: InMemoryNotificationThrottle | None = None
    _dispatcher_cache: tuple[NotificationChannelSettings, NotificationDispatcher] | None = field(
        init=False,
        default=None,
        repr=False,
    )

    def send_test_notification(self) -> NotificationDispatchResult:
        """以目前已保存的全域設定送出一則測試通知。"""
        settings = self.app_settings_service.get_notification_channel_settings()
        dispatcher = self._get_or_build_dispatcher(settings)
        attempted_at = datetime.now(UTC)
        return dispatcher.dispatch(
            message=NotificationMessage(
                watch_item_id="system-test",
                dedupe_key=f"system-test:{attempted_at.isoformat()}",
                title="hotel_price_watch 測試通知",
                body=(
                    "這是一則全域通知通道測試訊息。\n"
                    "若你收到這則通知，代表目前的通知發送路徑可正常工作。"
                ),
                tags=("test", "channel-check"),
            ),
            attempted_at=attempted_at,
        )

    def _get_or_build_dispatcher(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationDispatcher:
        """在設定未變動時重用 dispatcher，避免每次測試通知都重建。"""
        if self._dispatcher_cache is not None:
            cached_settings, cached_dispatcher = self._dispatcher_cache
            if cached_settings == settings:
                return cached_dispatcher

        enabled_notifiers = self.notifier_factory(settings)
        if not enabled_notifiers:
            raise ValueError("目前沒有任何已啟用的通知通道可供測試。")

        dispatcher = NotificationDispatcher(
            notifiers=tuple(enabled_notifiers),
            throttle=self.throttle or InMemoryNotificationThrottle(),
            cooldown_seconds_by_channel={
                "desktop": 60,
                "ntfy": 300,
                "discord": 300,
            },
        )
        self._dispatcher_cache = (settings, dispatcher)
        return dispatcher
