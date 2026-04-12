"""全域設定模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NotificationChannelSettings:
    """表示全域通知通道設定，不與單一 watch 綁定。"""

    desktop_enabled: bool = True
    ntfy_enabled: bool = False
    ntfy_server_url: str = "https://ntfy.sh"
    ntfy_topic: str | None = None
    discord_enabled: bool = False
    discord_webhook_url: str | None = None
