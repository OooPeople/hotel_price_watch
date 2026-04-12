"""`ntfy` 通知通道實作。"""

from __future__ import annotations

import urllib.request
from typing import Callable

from app.notifiers.models import NotificationMessage

HttpPoster = Callable[[str, dict[str, str], bytes], None]


class NtfyNotifier:
    """把通知送到指定的 `ntfy` topic。"""

    channel_name = "ntfy"

    def __init__(
        self,
        *,
        server_url: str,
        topic: str,
        http_poster: HttpPoster | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._topic = topic
        self._http_poster = http_poster or _post_http_request

    def send(self, message: NotificationMessage) -> None:
        """送出 `ntfy` HTTP 請求。"""
        url = f"{self._server_url}/{self._topic}"
        headers = {
            "Title": message.title,
            "Tags": ",".join(message.tags),
            "Content-Type": "text/plain; charset=utf-8",
        }
        self._http_poster(url, headers, message.body.encode("utf-8"))


def _post_http_request(url: str, headers: dict[str, str], body: bytes) -> None:
    """以內建 HTTP client 發送通知請求。"""
    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request):
        return None
