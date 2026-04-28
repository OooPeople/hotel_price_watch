from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.enums import NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.main import create_app
from app.web.settings_presenters import (
    build_notification_channel_settings_presentation,
    build_settings_page_view_model,
    build_watch_notification_rule_presentation,
)
from app.web.views import (
    render_notification_channel_settings_page,
    render_notification_settings_page,
)

from .helpers import (
    _build_test_container,
    _build_watch_item,
    _build_watch_item_with_below_target_rule,
    _local_request_headers,
)


def test_render_notification_settings_page_shows_current_rule() -> None:
    """通知設定頁應顯示目前已保存的通知條件。"""
    html = render_notification_settings_page(
        watch_item=_build_watch_item_with_below_target_rule(),
        flash_message="已更新 通知設定",
    )

    assert "通知設定" in html
    assert "低於目標價" in html
    assert 'value="20000"' in html
    assert "已更新 通知設定" in html
    assert "Standard Twin / Room Only" not in html


def test_notification_channel_settings_presentation_handles_form_values() -> None:
    """設定 presenter 應集中表單回填、摘要與敏感值遮罩規則。"""
    presentation = build_notification_channel_settings_presentation(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=False,
            ntfy_server_url="https://ntfy.sh",
            ntfy_topic="saved-topic",
            discord_enabled=False,
            discord_webhook_url="https://discord.example.com/saved-webhook",
        ),
        display_settings=DisplaySettings(use_24_hour_time=True),
        form_values={
            "desktop_enabled": "",
            "ntfy_enabled": "on",
            "ntfy_server_url": "https://ntfy.example.com",
            "ntfy_topic": "form-topic",
            "discord_enabled": "on",
            "discord_webhook_url": "https://discord.example.com/form-webhook",
            "time_format_12h": "on",
        },
    )

    assert presentation.desktop_enabled is False
    assert presentation.ntfy_enabled is True
    assert presentation.discord_enabled is True
    assert presentation.use_24_hour_time is False
    assert presentation.ntfy_topic == "form-topic"
    assert presentation.masked_discord_webhook_url == "https://discord.ex...ebhook"
    assert [card.title for card in presentation.summary_cards] == [
        "時間顯示",
        "桌面通知",
        "ntfy",
        "Discord",
    ]


def test_settings_page_view_models_centralize_form_state() -> None:
    """設定頁 view model 應集中全域設定與單一 watch 通知規則表單狀態。"""
    settings_view_model = build_settings_page_view_model(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=False,
            ntfy_server_url="https://ntfy.sh",
            ntfy_topic="saved-topic",
            discord_enabled=False,
            discord_webhook_url=None,
        ),
        display_settings=DisplaySettings(use_24_hour_time=True),
        error_message="錯誤",
        form_values={"time_format_12h": "on"},
    )
    rule_view_model = build_watch_notification_rule_presentation(
        watch_item=_build_watch_item_with_below_target_rule(),
        form_values={"target_price": "abc"},
    )

    assert settings_view_model.error_message == "錯誤"
    assert settings_view_model.channel_settings.use_24_hour_time is False
    assert rule_view_model.selected_kind == NotificationLeafKind.BELOW_TARGET_PRICE
    assert rule_view_model.target_price_value == "abc"


def test_render_notification_channel_settings_page_shows_saved_values() -> None:
    """設定頁應顯示目前已保存的通道與顯示設定。"""
    html = render_notification_channel_settings_page(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=True,
            ntfy_server_url="https://ntfy.example.com",
            ntfy_topic="hotel-watch",
            discord_enabled=True,
            discord_webhook_url="https://discord.example.com/webhook",
        ),
        flash_message="已更新 通知通道設定",
    )

    assert "設定" in html
    assert "hotel-watch" in html
    assert "設定摘要" in html
    assert "編輯設定" in html
    assert "Webhook URL 摘要已遮罩" in html
    assert "https://discord.ex...ebhook" in html
    assert "https://discord.example.com/webhook" in html
    assert "已更新 通知通道設定" in html
    assert "發送測試通知" in html
    assert "12 小時制" in html
    assert "24 小時制" in html
    assert 'name="time_format_24h"' in html
    assert 'id="global-settings-form"' in html
    assert "尚未儲存" in html
    assert "beforeunload" in html


def test_render_notification_channel_settings_page_shows_structured_test_result() -> None:
    """測試通知結果應以結構化區塊呈現各通道狀態與失敗原因。"""
    html = render_notification_channel_settings_page(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=True,
            ntfy_server_url="https://ntfy.example.com",
            ntfy_topic="hotel-watch",
            discord_enabled=True,
            discord_webhook_url="https://discord.example.com/webhook",
        ),
        test_result_message=(
            "測試通知結果：sent=desktop；"
            "throttled=none；"
            "failed=ntfy, discord；"
            "details=ntfy: timed out | discord: HTTP Error 400"
        ),
    )

    assert "測試通知結果" in html
    assert "成功通道：desktop" in html
    assert "失敗通道：ntfy, discord" in html
    assert "失敗原因：ntfy: timed out | discord: HTTP Error 400" in html


def test_render_notification_settings_page_shows_any_drop_hint() -> None:
    """價格下降規則時，畫面應明示目標價會被忽略。"""
    html = render_notification_settings_page(
        watch_item=_build_watch_item(),
    )

    assert "目標價欄位會被忽略" in html
    assert 'id="notification-target-price-wrapper"' in html
    assert "display:none" in html

def test_post_notification_settings_allows_any_drop_with_target_price_input(tmp_path) -> None:
    """通知設定頁在 any_drop 下應忽略 target_price，而不是回 400。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("18000"),
    )
    client = TestClient(create_app(container))

    response = client.post(
        f"/watches/{watch_item.id}/notification-settings",
        data={
            "notification_rule_kind": NotificationLeafKind.ANY_DROP.value,
            "target_price": "20000",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated_watch_item = container.watch_item_repository.get(watch_item.id)
    assert updated_watch_item is not None
    assert updated_watch_item.notification_rule == RuleLeaf(
        kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )


def test_post_notification_settings_preserves_invalid_form_value(tmp_path) -> None:
    """通知設定儲存失敗時應保留使用者剛輸入的表單值。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("18000"),
    )
    client = TestClient(create_app(container))

    response = client.post(
        f"/watches/{watch_item.id}/notification-settings",
        data={
            "notification_rule_kind": NotificationLeafKind.BELOW_TARGET_PRICE.value,
            "target_price": "abc",
        },
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert 'value="abc"' in response.text
    assert "目標價格式不正確" in response.text


def test_post_global_notification_settings_updates_channels(tmp_path) -> None:
    """全域設定頁應可保存通知通道與顯示偏好。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_enabled": "on",
            "ntfy_server_url": "https://ntfy.example.com",
            "ntfy_topic": "hotel-watch",
            "discord_enabled": "on",
            "discord_webhook_url": "https://discord.example.com/webhook",
            "time_format_24h": "on",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = container.app_settings_service.get_notification_channel_settings()
    assert settings == NotificationChannelSettings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_server_url="https://ntfy.example.com",
        ntfy_topic="hotel-watch",
        discord_enabled=True,
        discord_webhook_url="https://discord.example.com/webhook",
    )
    assert container.app_settings_service.get_display_settings() == DisplaySettings(
        use_24_hour_time=True,
    )


def test_post_global_settings_can_switch_to_12_hour_time(tmp_path) -> None:
    """取消 24 小時制 checkbox 後，應保存為 12 小時制偏好。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_server_url": "https://ntfy.sh",
            "time_format_12h": "on",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert container.app_settings_service.get_display_settings() == DisplaySettings(
        use_24_hour_time=False,
    )


def test_post_global_settings_rejects_multiple_time_formats(tmp_path) -> None:
    """時間格式設定若同時勾選兩項，後端應拒絕保存。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_server_url": "https://ntfy.sh",
            "time_format_12h": "on",
            "time_format_24h": "on",
        },
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert "請選擇 12 小時制或 24 小時制其中一項" in response.text


def test_post_global_notification_test_uses_saved_dispatch_path(tmp_path) -> None:
    """測試通知應走正式 dispatcher / notifier 路徑，並回報各通道結果。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings/test-notification",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    test_message = parse_qs(urlparse(location).query)["test_message"][0]
    assert "sent=desktop" in test_message
    assert "details=none" in test_message


def test_post_global_notification_test_requires_enabled_channel(tmp_path) -> None:
    """若沒有任何已啟用通道，測試通知應直接回報錯誤。"""
    container = _build_test_container(tmp_path)
    container.notification_channel_test_service.enabled = False
    client = TestClient(create_app(container))

    response = client.post(
        "/settings/test-notification",
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert "目前沒有任何已啟用的通知通道可供測試" in response.text


def test_post_global_notification_settings_preserves_invalid_form_value(tmp_path) -> None:
    """設定儲存失敗時應保留使用者剛輸入的值。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_enabled": "on",
            "ntfy_server_url": "https://ntfy.example.com",
            "ntfy_topic": "",
            "discord_enabled": "on",
            "discord_webhook_url": "https://discord.example.com/webhook",
            "time_format_24h": "on",
        },
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert "必須填寫 topic" in response.text
    assert 'value="https://ntfy.example.com"' in response.text
    assert 'value="https://discord.example.com/webhook"' in response.text
