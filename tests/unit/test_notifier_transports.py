import json
import urllib.error

from app.notifiers.desktop import DesktopNotifier
from app.notifiers.discord import DiscordWebhookNotifier
from app.notifiers.models import NotificationMessage
from app.notifiers.ntfy import NtfyNotifier


def test_desktop_notifier_builds_powershell_command() -> None:
    """驗證桌面通知通道會組出 Windows PowerShell balloon command。"""
    commands: list[list[str]] = []
    notifier = DesktopNotifier(command_runner=commands.append)

    notifier.send(_message())

    assert commands
    assert commands[0][0] == "powershell"
    assert "BalloonTipTitle" in commands[0][3]
    assert "價格下降：Ocean Hotel" in commands[0][3]


def test_ntfy_notifier_posts_plain_text_payload() -> None:
    """驗證 ntfy 通道會送出 UTF-8 JSON payload。"""
    requests: list[tuple[str, dict[str, str], bytes, float]] = []
    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="hotel-watch",
        http_poster=lambda url, headers, body, timeout: requests.append(
            (url, headers, body, timeout)
        ),
    )

    notifier.send(_message())

    assert requests == [
        (
            "https://ntfy.example.com",
            {
                "Content-Type": "application/json; charset=utf-8",
            },
            json.dumps(
                {
                    "topic": "hotel-watch",
                    "title": "價格下降：Ocean Hotel",
                    "message": "價格：JPY 22000",
                    "tags": ["price-drop"],
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            10.0,
        )
    ]


def test_discord_notifier_posts_json_payload() -> None:
    """驗證 Discord webhook 通道會送出相容 webhook 的 JSON payload。"""
    requests: list[tuple[str, dict[str, str], bytes, float]] = []
    notifier = DiscordWebhookNotifier(
        webhook_url="https://discord.example.com/webhook",
        http_poster=lambda url, headers, body, timeout: requests.append(
            (url, headers, body, timeout)
        ),
    )

    notifier.send(_message())

    assert len(requests) == 1
    url, headers, body, timeout = requests[0]
    assert url == "https://discord.example.com/webhook"
    assert headers == {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "*/*",
        "User-Agent": "python-requests/2.32.3",
    }
    assert timeout == 10.0
    assert json.loads(body.decode("utf-8")) == {
        "username": "hotel_price_watch",
        "content": "**價格下降：Ocean Hotel**\n價格：JPY 22000",
    }


def test_discord_notifier_raises_readable_http_error() -> None:
    """Discord webhook 若回應 HTTPError，應附帶較可讀的錯誤內容。"""

    def failing_poster(
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> None:
        del url, headers, body, timeout
        raise urllib.error.HTTPError(
            url="https://discord.example.com/webhook",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )

    notifier = DiscordWebhookNotifier(
        webhook_url="https://discord.example.com/webhook",
        http_poster=failing_poster,
    )

    try:
        notifier.send(_message())
    except urllib.error.HTTPError:
        raise AssertionError("should not leak raw HTTPError") from None
    except Exception as exc:  # noqa: BLE001
        assert "403" in str(exc)
        assert "Forbidden" in str(exc)
    else:
        raise AssertionError("expected discord notifier to raise")


def _message() -> NotificationMessage:
    """建立通知通道測試共用的訊息。"""
    return NotificationMessage(
        watch_item_id="watch-1",
        dedupe_key="watch-1:price_drop:available:22000",
        title="價格下降：Ocean Hotel",
        body="價格：JPY 22000",
        tags=("price-drop",),
    )
