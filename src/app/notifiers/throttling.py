"""通知通道節流與分派協調。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.domain.entities import NotificationDispatchResult, NotificationThrottleState
from app.notifiers.base import Notifier
from app.notifiers.models import NotificationMessage


class NotificationThrottle(Protocol):
    """描述通知節流器需要提供的最小介面。"""

    def is_throttled(
        self,
        *,
        channel_name: str,
        message: NotificationMessage,
        attempted_at: datetime,
        cooldown_seconds: int,
    ) -> bool:
        """判斷指定通道是否仍在節流視窗內。"""

    def mark_delivered(
        self,
        *,
        channel_name: str,
        message: NotificationMessage,
        delivered_at: datetime,
    ) -> None:
        """在通道送出成功後更新節流狀態。"""


class NotificationThrottleStateStore(Protocol):
    """描述節流狀態持久化需要的最小資料介面。"""

    def get_notification_throttle_state(
        self,
        *,
        channel_name: str,
        dedupe_key: str,
    ) -> NotificationThrottleState | None:
        """讀出指定通道與 dedupe key 的節流狀態。"""

    def save_notification_throttle_state(
        self,
        state: NotificationThrottleState,
    ) -> None:
        """保存指定通道與 dedupe key 的節流狀態。"""


class InMemoryNotificationThrottle:
    """用記憶體保存各通道最近一次發送時間的簡單節流器。"""

    def __init__(self) -> None:
        self._last_sent_at_by_channel_key: dict[tuple[str, str], datetime] = {}

    def is_throttled(
        self,
        *,
        channel_name: str,
        message: NotificationMessage,
        attempted_at: datetime,
        cooldown_seconds: int,
    ) -> bool:
        """判斷指定通道對同一訊息 key 是否仍在冷卻期間內。"""
        key = (channel_name, message.dedupe_key)
        last_sent_at = self._last_sent_at_by_channel_key.get(key)
        if last_sent_at is not None and attempted_at < last_sent_at + timedelta(
            seconds=cooldown_seconds
        ):
            return True

        return False

    def mark_delivered(
        self,
        *,
        channel_name: str,
        message: NotificationMessage,
        delivered_at: datetime,
    ) -> None:
        """在通道實際送出成功後更新節流時間。"""
        key = (channel_name, message.dedupe_key)
        self._last_sent_at_by_channel_key[key] = delivered_at


class PersistentNotificationThrottle:
    """以持久化狀態保存通道級冷卻時間，避免重啟後重複通知。"""

    def __init__(self, state_store: NotificationThrottleStateStore) -> None:
        self._state_store = state_store

    def is_throttled(
        self,
        *,
        channel_name: str,
        message: NotificationMessage,
        attempted_at: datetime,
        cooldown_seconds: int,
    ) -> bool:
        """依持久化的最近成功發送時間判斷是否仍在冷卻期間內。"""
        state = self._state_store.get_notification_throttle_state(
            channel_name=channel_name,
            dedupe_key=message.dedupe_key,
        )
        if state is None:
            return False
        return attempted_at < state.last_sent_at + timedelta(seconds=cooldown_seconds)

    def mark_delivered(
        self,
        *,
        channel_name: str,
        message: NotificationMessage,
        delivered_at: datetime,
    ) -> None:
        """在送出成功後把通道級節流時間持久化。"""
        self._state_store.save_notification_throttle_state(
            NotificationThrottleState(
                channel_name=channel_name,
                dedupe_key=message.dedupe_key,
                last_sent_at=delivered_at,
            )
        )


class NotificationDispatcher:
    """協調多個 notifier 並套用通道級節流。"""

    def __init__(
        self,
        *,
        notifiers: tuple[Notifier, ...],
        throttle: NotificationThrottle | None = None,
        cooldown_seconds_by_channel: dict[str, int] | None = None,
    ) -> None:
        self._notifiers = notifiers
        self._throttle = throttle or InMemoryNotificationThrottle()
        self._cooldown_seconds_by_channel = cooldown_seconds_by_channel or {}

    def dispatch(
        self,
        *,
        message: NotificationMessage,
        attempted_at: datetime,
    ) -> NotificationDispatchResult:
        """依序嘗試各通知通道，並略過節流中的重複發送。"""
        sent_channels: list[str] = []
        throttled_channels: list[str] = []
        failed_channels: list[str] = []
        failure_details: dict[str, str] = {}

        for notifier in self._notifiers:
            channel_name = notifier.channel_name
            cooldown_seconds = self._cooldown_seconds_by_channel.get(channel_name, 0)
            if self._throttle.is_throttled(
                channel_name=channel_name,
                message=message,
                attempted_at=attempted_at,
                cooldown_seconds=cooldown_seconds,
            ):
                throttled_channels.append(channel_name)
                continue

            try:
                notifier.send(message)
            except Exception as exc:
                failed_channels.append(channel_name)
                failure_details[channel_name] = str(exc)
                continue

            self._throttle.mark_delivered(
                channel_name=channel_name,
                message=message,
                delivered_at=attempted_at,
            )
            sent_channels.append(channel_name)

        return NotificationDispatchResult(
            sent_channels=tuple(sent_channels),
            throttled_channels=tuple(throttled_channels),
            failed_channels=tuple(failed_channels),
            attempted_at=attempted_at,
            failure_details=failure_details or None,
        )
