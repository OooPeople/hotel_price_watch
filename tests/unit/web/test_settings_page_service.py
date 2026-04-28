from __future__ import annotations

from datetime import UTC, datetime

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.entities import NotificationDispatchResult
from app.web.settings_page_service import SettingsPageService

from .helpers import _build_test_container, _build_watch_item


def test_settings_page_service_builds_global_settings_context(tmp_path) -> None:
    """SettingsPageService 應集中讀取全域設定頁需要的 context。"""
    container = _build_test_container(tmp_path)
    container.app_settings_service.update_notification_channel_settings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_server_url="https://ntfy.example.com",
        ntfy_topic="hotel-watch",
        discord_enabled=False,
        discord_webhook_url=None,
    )
    container.app_settings_service.update_display_settings(use_24_hour_time=False)
    service = SettingsPageService(container)

    context = service.build_notification_channel_settings_context(
        flash_message="已更新 設定",
        test_result_message="測試通知結果：sent=desktop",
    )

    assert context.settings == NotificationChannelSettings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_server_url="https://ntfy.example.com",
        ntfy_topic="hotel-watch",
        discord_enabled=False,
        discord_webhook_url=None,
    )
    assert context.display_settings == DisplaySettings(use_24_hour_time=False)
    assert context.flash_message == "已更新 設定"
    assert context.test_result_message == "測試通知結果：sent=desktop"


def test_settings_page_service_builds_watch_notification_context(tmp_path) -> None:
    """SettingsPageService 應集中組出單一 watch 通知設定頁 context。"""
    container = _build_test_container(tmp_path)
    watch_item = _build_watch_item()
    service = SettingsPageService(container)

    context = service.build_watch_notification_settings_context(
        watch_item=watch_item,
        error_message="目標價格式不正確",
        form_values={"target_price": "abc"},
    )

    assert context.watch_item is watch_item
    assert context.error_message == "目標價格式不正確"
    assert context.form_values == {"target_price": "abc"}


def test_settings_page_service_formats_test_notification_result(tmp_path) -> None:
    """測試通知結果摘要應由 service 統一格式化，避免 route 分散字串規則。"""
    service = SettingsPageService(_build_test_container(tmp_path))

    message = service.format_test_notification_result(
        NotificationDispatchResult(
            sent_channels=("desktop",),
            throttled_channels=("ntfy",),
            failed_channels=("discord",),
            attempted_at=datetime(2026, 4, 13, 12, 0, tzinfo=UTC),
            failure_details={"discord": "HTTP Error 400"},
        )
    )

    assert message == (
        "測試通知結果：sent=desktop；"
        "throttled=ntfy；failed=discord；"
        "details=discord: HTTP Error 400"
    )
