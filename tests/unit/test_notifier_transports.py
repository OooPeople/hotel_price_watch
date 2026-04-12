import json

from app.notifiers.desktop import DesktopNotifier
from app.notifiers.discord import DiscordWebhookNotifier
from app.notifiers.models import NotificationMessage
from app.notifiers.ntfy import NtfyNotifier


def test_desktop_notifier_builds_powershell_command() -> None:
    commands: list[list[str]] = []
    notifier = DesktopNotifier(command_runner=commands.append)

    notifier.send(_message())

    assert commands
    assert commands[0][0] == "powershell"
    assert "BalloonTipTitle" in commands[0][3]
    assert "價格下降：Ocean Hotel" in commands[0][3]


def test_ntfy_notifier_posts_plain_text_payload() -> None:
    requests: list[tuple[str, dict[str, str], bytes]] = []
    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="hotel-watch",
        http_poster=lambda url, headers, body: requests.append((url, headers, body)),
    )

    notifier.send(_message())

    assert requests == [
        (
            "https://ntfy.example.com/hotel-watch",
            {
                "Title": "價格下降：Ocean Hotel",
                "Tags": "price-drop",
                "Content-Type": "text/plain; charset=utf-8",
            },
            "價格：JPY 22000".encode("utf-8"),
        )
    ]


def test_discord_notifier_posts_json_payload() -> None:
    requests: list[tuple[str, dict[str, str], bytes]] = []
    notifier = DiscordWebhookNotifier(
        webhook_url="https://discord.example.com/webhook",
        http_poster=lambda url, headers, body: requests.append((url, headers, body)),
    )

    notifier.send(_message())

    assert len(requests) == 1
    url, headers, body = requests[0]
    assert url == "https://discord.example.com/webhook"
    assert headers == {"Content-Type": "application/json; charset=utf-8"}
    assert json.loads(body.decode("utf-8")) == {
        "username": "hotel_price_watch",
        "content": "**價格下降：Ocean Hotel**\n價格：JPY 22000",
    }


def _message() -> NotificationMessage:
    """建立通知通道測試共用的訊息。"""
    return NotificationMessage(
        watch_item_id="watch-1",
        dedupe_key="watch-1:price_drop:available:22000",
        title="價格下降：Ocean Hotel",
        body="價格：JPY 22000",
        tags=("price-drop",),
    )
