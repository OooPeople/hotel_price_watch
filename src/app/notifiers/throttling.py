"""通知通道節流與分派協調。"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.entities import NotificationDispatchResult
from app.notifiers.base import Notifier
from app.notifiers.models import NotificationMessage


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


class NotificationDispatcher:
    """協調多個 notifier 並套用通道級節流。"""

    def __init__(
        self,
        *,
        notifiers: tuple[Notifier, ...],
        throttle: InMemoryNotificationThrottle | None = None,
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
            except Exception:
                failed_channels.append(channel_name)
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
        )
