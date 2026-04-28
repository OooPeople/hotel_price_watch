"""runtime 通知分派協調器。"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Protocol

from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    CheckResult,
    NotificationDecision,
    NotificationDispatchResult,
    WatchItem,
)
from app.notifiers import (
    NotificationDispatcher,
    build_notification_message,
)
from app.notifiers.base import Notifier
from app.notifiers.throttling import NotificationThrottle

NotifierFactory = Callable[[NotificationChannelSettings], tuple[Notifier, ...]]


class NotificationSettingsReader(Protocol):
    """描述通知分派只需要的全域通知設定讀取介面。"""

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """讀取目前保存的全域通知通道設定。"""
        ...


class NotificationDispatchCoordinator:
    """封裝 runtime 通知分派、dispatcher cache 與通道節流協調。"""

    def __init__(
        self,
        *,
        app_settings_service: NotificationSettingsReader,
        notifier_factory: NotifierFactory,
        notification_throttle: NotificationThrottle,
    ) -> None:
        """建立 runtime 通知分派協調器。"""
        self._app_settings_service = app_settings_service
        self._notifier_factory = notifier_factory
        self._notification_throttle = notification_throttle
        self._dispatcher_cache: (
            tuple[NotificationChannelSettings, NotificationDispatcher] | None
        ) = None

    def dispatch_notification(
        self,
        *,
        watch_item: WatchItem,
        check_result: CheckResult,
        notification_decision: NotificationDecision,
        attempted_at: datetime,
    ) -> NotificationDispatchResult | None:
        """依全域設定建立 notifier 並實際送出通知。"""
        settings = self._app_settings_service.get_notification_channel_settings()
        dispatcher = self._get_or_build_dispatcher(settings)
        if dispatcher is None:
            return None
        message = build_notification_message(
            watch_item=watch_item,
            check_result=check_result,
            decision=notification_decision,
        )
        return dispatcher.dispatch(
            message=message,
            attempted_at=attempted_at,
        )

    def _get_or_build_dispatcher(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationDispatcher | None:
        """在設定未變動時重用 dispatcher，避免每次檢查都重新建立。"""
        if self._dispatcher_cache is not None:
            cached_settings, cached_dispatcher = self._dispatcher_cache
            if cached_settings == settings:
                return cached_dispatcher

        enabled_notifiers = self._notifier_factory(settings)
        if not enabled_notifiers:
            self._dispatcher_cache = None
            return None

        dispatcher = NotificationDispatcher(
            notifiers=tuple(enabled_notifiers),
            throttle=self._notification_throttle,
            cooldown_seconds_by_channel={
                "desktop": 60,
                "ntfy": 300,
                "discord": 300,
            },
        )
        self._dispatcher_cache = (settings, dispatcher)
        return dispatcher
