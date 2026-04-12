"""通知通道與節流邏輯的公開入口。"""

from app.domain.entities import NotificationDispatchResult
from app.notifiers.base import Notifier
from app.notifiers.desktop import DesktopNotifier
from app.notifiers.discord import DiscordWebhookNotifier
from app.notifiers.formatters import build_notification_message
from app.notifiers.models import NotificationMessage
from app.notifiers.ntfy import NtfyNotifier
from app.notifiers.throttling import InMemoryNotificationThrottle, NotificationDispatcher

__all__ = [
    "DesktopNotifier",
    "DiscordWebhookNotifier",
    "InMemoryNotificationThrottle",
    "NotificationDispatchResult",
    "NotificationDispatcher",
    "NotificationMessage",
    "Notifier",
    "NtfyNotifier",
    "build_notification_message",
]
