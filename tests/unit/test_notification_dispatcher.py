from datetime import datetime, timedelta

from app.domain.entities import NotificationThrottleState
from app.notifiers.models import NotificationMessage
from app.notifiers.throttling import (
    InMemoryNotificationThrottle,
    NotificationDispatcher,
    PersistentNotificationThrottle,
)


def test_dispatcher_sends_to_all_channels_when_not_throttled() -> None:
    desktop = FakeNotifier("desktop")
    discord = FakeNotifier("discord")
    dispatcher = NotificationDispatcher(
        notifiers=(desktop, discord),
        throttle=InMemoryNotificationThrottle(),
        cooldown_seconds_by_channel={"desktop": 300, "discord": 300},
    )

    result = dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 0, 0),
    )

    assert result.sent_channels == ("desktop", "discord")
    assert result.throttled_channels == ()
    assert result.failed_channels == ()
    assert len(desktop.messages) == 1
    assert len(discord.messages) == 1


def test_dispatcher_throttles_same_message_within_cooldown() -> None:
    desktop = FakeNotifier("desktop")
    dispatcher = NotificationDispatcher(
        notifiers=(desktop,),
        throttle=InMemoryNotificationThrottle(),
        cooldown_seconds_by_channel={"desktop": 300},
    )

    first_result = dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 0, 0),
    )
    second_result = dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 1, 0),
    )
    third_result = dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 0, 0) + timedelta(minutes=6),
    )

    assert first_result.sent_channels == ("desktop",)
    assert second_result.sent_channels == ()
    assert second_result.throttled_channels == ("desktop",)
    assert second_result.failed_channels == ()
    assert third_result.sent_channels == ("desktop",)
    assert len(desktop.messages) == 2


def test_dispatcher_continues_when_one_channel_fails() -> None:
    """驗證單一通道失敗不會阻止後續通道發送。"""
    failing = FailingNotifier("discord")
    desktop = FakeNotifier("desktop")
    dispatcher = NotificationDispatcher(
        notifiers=(failing, desktop),
        throttle=InMemoryNotificationThrottle(),
        cooldown_seconds_by_channel={"discord": 300, "desktop": 300},
    )

    result = dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 0, 0),
    )
    second_result = dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 1, 0),
    )

    assert result.sent_channels == ("desktop",)
    assert result.failed_channels == ("discord",)
    assert result.throttled_channels == ()
    assert result.failure_details == {"discord": "discord failed for watch-1"}
    assert second_result.failed_channels == ("discord",)
    assert second_result.throttled_channels == ("desktop",)
    assert len(desktop.messages) == 1


def test_persistent_throttle_survives_new_dispatcher_instance() -> None:
    """驗證通道級節流狀態會跨 dispatcher 實例持續存在。"""
    desktop = FakeNotifier("desktop")
    state_store = FakeThrottleStateStore()
    first_dispatcher = NotificationDispatcher(
        notifiers=(desktop,),
        throttle=PersistentNotificationThrottle(state_store),
        cooldown_seconds_by_channel={"desktop": 300},
    )
    second_dispatcher = NotificationDispatcher(
        notifiers=(desktop,),
        throttle=PersistentNotificationThrottle(state_store),
        cooldown_seconds_by_channel={"desktop": 300},
    )

    first_result = first_dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 0, 0),
    )
    second_result = second_dispatcher.dispatch(
        message=_message(),
        attempted_at=datetime(2026, 4, 12, 10, 1, 0),
    )

    assert first_result.sent_channels == ("desktop",)
    assert second_result.sent_channels == ()
    assert second_result.throttled_channels == ("desktop",)
    assert len(desktop.messages) == 1


class FakeNotifier:
    """用於驗證 dispatcher 行為的假 notifier。"""

    def __init__(self, channel_name: str) -> None:
        self.channel_name = channel_name
        self.messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        """記錄收到的通知訊息。"""
        self.messages.append(message)


class FailingNotifier:
    """用於驗證 dispatcher 例外隔離的假 notifier。"""

    def __init__(self, channel_name: str) -> None:
        self.channel_name = channel_name

    def send(self, message: NotificationMessage) -> None:
        """模擬通道發送失敗。"""
        raise RuntimeError(f"{self.channel_name} failed for {message.watch_item_id}")


class FakeThrottleStateStore:
    """用於驗證持久化節流行為的記憶體 state store。"""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], NotificationThrottleState] = {}

    def get_notification_throttle_state(
        self,
        *,
        channel_name: str,
        dedupe_key: str,
    ) -> NotificationThrottleState | None:
        """讀出指定通道與 dedupe key 的節流狀態。"""
        return self._states.get((channel_name, dedupe_key))

    def save_notification_throttle_state(
        self,
        state: NotificationThrottleState,
    ) -> None:
        """保存指定通道與 dedupe key 的節流狀態。"""
        self._states[(state.channel_name, state.dedupe_key)] = state


def _message() -> NotificationMessage:
    """建立 dispatcher 測試共用的通知訊息。"""
    return NotificationMessage(
        watch_item_id="watch-1",
        dedupe_key="watch-1:price_drop:available:22000",
        title="價格下降：Ocean Hotel",
        body="價格：JPY 22000",
        tags=("price-drop",),
    )
