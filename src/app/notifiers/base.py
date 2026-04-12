"""通知通道的抽象介面。"""

from __future__ import annotations

from typing import Protocol

from app.notifiers.models import NotificationMessage


class Notifier(Protocol):
    """定義各通知通道需實作的最小發送介面。"""

    channel_name: str

    def send(self, message: NotificationMessage) -> None:
        """將標準化訊息送往實際通知通道。"""
