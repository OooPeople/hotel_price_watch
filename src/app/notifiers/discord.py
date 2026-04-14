"""Discord webhook 通知實作。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from app.notifiers.models import NotificationMessage
from app.notifiers.ntfy import DEFAULT_NOTIFICATION_HTTP_TIMEOUT_SECONDS

HttpPoster = Callable[[str, dict[str, str], bytes, float], None]


class DiscordWebhookNotifier:
    """把通知送到 Discord webhook。"""

    channel_name = "discord"

    def __init__(
        self,
        *,
        webhook_url: str,
        username: str = "hotel_price_watch",
        http_poster: HttpPoster | None = None,
        timeout_seconds: float = DEFAULT_NOTIFICATION_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        """建立 Discord webhook notifier，並設定單次 HTTP 請求的最長等待時間。"""
        self._webhook_url = webhook_url
        self._username = username
        self._http_poster = http_poster or _post_http_request
        self._timeout_seconds = timeout_seconds

    def send(self, message: NotificationMessage) -> None:
        """送出 Discord webhook payload。"""
        payload = {
            "username": self._username,
            "content": f"**{message.title}**\n{message.body}",
        }
        try:
            self._http_poster(
                self._webhook_url,
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "*/*",
                    "User-Agent": "python-requests/2.32.3",
                },
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                self._timeout_seconds,
            )
        except urllib.error.HTTPError as exc:
            raise _build_http_error(exc) from exc


def _post_http_request(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout_seconds: float,
) -> None:
    """以內建 HTTP client 發送 webhook 請求。"""
    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds):
            return None
    except urllib.error.HTTPError as exc:
        raise _build_http_error(exc) from exc


def _build_http_error(exc: urllib.error.HTTPError) -> RuntimeError:
    """把 Discord webhook 的 HTTPError 轉成較可讀的錯誤訊息。"""
    error_body = exc.read().decode("utf-8", errors="replace").strip()
    if error_body:
        return RuntimeError(f"Discord webhook 回應 {exc.code} {exc.reason}: {error_body}")
    return RuntimeError(f"Discord webhook 回應 {exc.code} {exc.reason}")
