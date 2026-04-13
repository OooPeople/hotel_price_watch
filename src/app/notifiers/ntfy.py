"""`ntfy` 通知通道實作。"""

from __future__ import annotations

import json
import urllib.error
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
        """以 JSON publish API 送出 `ntfy` HTTP 請求。"""
        url = self._server_url
        payload = {
            "topic": self._topic,
            "title": message.title,
            "message": message.body,
            "tags": list(message.tags),
        }
        headers = {"Content-Type": "application/json; charset=utf-8"}
        try:
            self._http_poster(
                url,
                headers,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
        except urllib.error.HTTPError as exc:
            raise _build_http_error(exc) from exc


def _post_http_request(url: str, headers: dict[str, str], body: bytes) -> None:
    """以內建 HTTP client 發送通知請求。"""
    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request):
            return None
    except urllib.error.HTTPError as exc:
        raise _build_http_error(exc) from exc


def _build_http_error(exc: urllib.error.HTTPError) -> RuntimeError:
    """把 ntfy 的 HTTPError 轉成較可讀的錯誤訊息。"""
    error_body = exc.read().decode("utf-8", errors="replace").strip()
    if error_body:
        return RuntimeError(f"ntfy 回應 {exc.code} {exc.reason}: {error_body}")
    return RuntimeError(f"ntfy 回應 {exc.code} {exc.reason}")
