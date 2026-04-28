from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    CheckResult,
    NotificationDecision,
    NotificationState,
    PriceSnapshot,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    NotificationEventKind,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.monitor.notification_dispatch import NotificationDispatchCoordinator
from app.notifiers.models import NotificationMessage
from app.notifiers.throttling import InMemoryNotificationThrottle


def test_notification_dispatch_returns_none_when_no_channels_are_enabled() -> None:
    """沒有可用通知通道時，通知協調器應回傳 None 並避免建立 dispatcher。"""
    settings_service = _MutableSettingsService(
        NotificationChannelSettings(desktop_enabled=False)
    )
    factory = _RecordingNotifierFactory()
    coordinator = NotificationDispatchCoordinator(
        app_settings_service=settings_service,
        notifier_factory=factory,
        notification_throttle=InMemoryNotificationThrottle(),
    )

    result = coordinator.dispatch_notification(
        watch_item=_watch_item(),
        check_result=_check_result(),
        notification_decision=_notification_decision(),
        attempted_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )

    assert result is None
    assert factory.call_count == 1


def test_notification_dispatch_reuses_dispatcher_when_settings_do_not_change() -> None:
    """設定未改變時，通知協調器應重用 dispatcher 與 notifier 實例。"""
    settings_service = _MutableSettingsService(NotificationChannelSettings())
    factory = _RecordingNotifierFactory()
    coordinator = NotificationDispatchCoordinator(
        app_settings_service=settings_service,
        notifier_factory=factory,
        notification_throttle=InMemoryNotificationThrottle(),
    )

    first_result = coordinator.dispatch_notification(
        watch_item=_watch_item(),
        check_result=_check_result(),
        notification_decision=_notification_decision(),
        attempted_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )
    second_result = coordinator.dispatch_notification(
        watch_item=_watch_item(),
        check_result=_check_result(),
        notification_decision=_notification_decision(),
        attempted_at=datetime(2026, 4, 13, 10, 2, tzinfo=UTC),
    )

    assert first_result is not None
    assert second_result is not None
    assert first_result.sent_channels == ("desktop",)
    assert second_result.sent_channels == ("desktop",)
    assert factory.call_count == 1
    assert len(factory.notifiers[0].messages) == 2


def test_notification_dispatch_rebuilds_dispatcher_when_settings_change() -> None:
    """設定變更時，通知協調器應重建 dispatcher 以套用新的通道組合。"""
    settings_service = _MutableSettingsService(NotificationChannelSettings())
    factory = _RecordingNotifierFactory()
    coordinator = NotificationDispatchCoordinator(
        app_settings_service=settings_service,
        notifier_factory=factory,
        notification_throttle=InMemoryNotificationThrottle(),
    )

    coordinator.dispatch_notification(
        watch_item=_watch_item(),
        check_result=_check_result(),
        notification_decision=_notification_decision(),
        attempted_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )
    settings_service.settings = NotificationChannelSettings(
        desktop_enabled=True,
        discord_enabled=True,
        discord_webhook_url="https://discord.example/webhook",
    )
    second_result = coordinator.dispatch_notification(
        watch_item=_watch_item(),
        check_result=_check_result(),
        notification_decision=_notification_decision(),
        attempted_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC) + timedelta(minutes=2),
    )

    assert second_result is not None
    assert second_result.sent_channels == ("desktop", "discord")
    assert factory.call_count == 2


class _MutableSettingsService:
    """提供通知協調器測試用的可變設定來源。"""

    def __init__(self, settings: NotificationChannelSettings) -> None:
        self.settings = settings

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """回傳目前測試指定的通知通道設定。"""
        return self.settings


class _RecordingNotifierFactory:
    """記錄 notifier 建立次數並依設定回傳假通知通道。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.notifiers: list[_RecordingNotifier] = []

    def __call__(
        self,
        settings: NotificationChannelSettings,
    ) -> tuple[_RecordingNotifier, ...]:
        """依測試設定建立啟用通道。"""
        self.call_count += 1
        notifiers: list[_RecordingNotifier] = []
        if settings.desktop_enabled:
            notifiers.append(_RecordingNotifier("desktop"))
        if settings.discord_enabled:
            notifiers.append(_RecordingNotifier("discord"))
        self.notifiers = notifiers
        return tuple(notifiers)


class _RecordingNotifier:
    """記錄收到訊息的假通知通道。"""

    def __init__(self, channel_name: str) -> None:
        self.channel_name = channel_name
        self.messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        """保存通知訊息，供測試斷言。"""
        self.messages.append(message)


def _watch_item() -> WatchItem:
    """建立通知協調器測試用 watch item。"""
    return WatchItem(
        id="watch-notification-dispatch",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime(2026, 4, 13, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 13, 9, 0, tzinfo=UTC),
    )


def _check_result() -> CheckResult:
    """建立通知協調器測試用 check result。"""
    return CheckResult(
        checked_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        current_snapshot=PriceSnapshot(
            display_price_text="JPY 22990",
            normalized_price_amount=Decimal("22990"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        ),
        previous_snapshot=PriceSnapshot(
            display_price_text="JPY 25000",
            normalized_price_amount=Decimal("25000"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        ),
        price_changed=True,
        availability_changed=False,
        price_dropped=True,
        became_available=False,
        parse_failed=False,
    )


def _notification_decision() -> NotificationDecision:
    """建立通知協調器測試用 notification decision。"""
    return NotificationDecision(
        event_kinds=(NotificationEventKind.PRICE_DROP,),
        next_state=NotificationState(watch_item_id="watch-notification-dispatch"),
    )
