"""Discord webhook 通知實作。"""

from __future__ import annotations

import json
import urllib.request
from typing import Callable

from app.notifiers.models import NotificationMessage

HttpPoster = Callable[[str, dict[str, str], bytes], None]


class DiscordWebhookNotifier:
    """把通知送到 Discord webhook。"""

    channel_name = "discord"

    def __init__(
        self,
        *,
        webhook_url: str,
        username: str = "hotel_price_watch",
        http_poster: HttpPoster | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._username = username
        self._http_poster = http_poster or _post_http_request

    def send(self, message: NotificationMessage) -> None:
        """送出 Discord webhook payload。"""
        payload = {
            "username": self._username,
            "content": f"**{message.title}**\n{message.body}",
        }
        self._http_poster(
            self._webhook_url,
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )


def _post_http_request(url: str, headers: dict[str, str], body: bytes) -> None:
    """以內建 HTTP client 發送 webhook 請求。"""
    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request):
        return None
