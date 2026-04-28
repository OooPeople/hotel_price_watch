"""設定頁面的 page context 與測試通知摘要組裝服務。"""

from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.container import AppContainer
from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.entities import NotificationDispatchResult, WatchItem


@dataclass(frozen=True, slots=True)
class NotificationChannelSettingsPageContext:
    """全域通知設定頁 renderer 所需的資料集合。"""

    settings: NotificationChannelSettings
    display_settings: DisplaySettings
    error_message: str | None = None
    flash_message: str | None = None
    test_result_message: str | None = None
    form_values: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class WatchNotificationSettingsPageContext:
    """單一 watch 通知設定頁 renderer 所需的資料集合。"""

    watch_item: WatchItem
    error_message: str | None = None
    flash_message: str | None = None
    form_values: dict[str, str] | None = None


class SettingsPageService:
    """集中設定頁 route 需要的 page context 與顯示摘要組裝。"""

    def __init__(self, container: AppContainer) -> None:
        """保存 route 層提供的依賴容器。"""
        self._container = container

    def build_notification_channel_settings_context(
        self,
        *,
        error_message: str | None = None,
        flash_message: str | None = None,
        test_result_message: str | None = None,
        form_values: dict[str, str] | None = None,
    ) -> NotificationChannelSettingsPageContext:
        """建立全域通知設定頁 renderer 需要的完整 context。"""
        return NotificationChannelSettingsPageContext(
            settings=self._container.app_settings_service.get_notification_channel_settings(),
            display_settings=self._container.app_settings_service.get_display_settings(),
            error_message=error_message,
            flash_message=flash_message,
            test_result_message=test_result_message,
            form_values=form_values,
        )

    def build_watch_notification_settings_context(
        self,
        *,
        watch_item: WatchItem,
        error_message: str | None = None,
        flash_message: str | None = None,
        form_values: dict[str, str] | None = None,
    ) -> WatchNotificationSettingsPageContext:
        """建立單一 watch 通知設定頁 renderer 需要的完整 context。"""
        return WatchNotificationSettingsPageContext(
            watch_item=watch_item,
            error_message=error_message,
            flash_message=flash_message,
            form_values=form_values,
        )

    def format_test_notification_result(
        self,
        dispatch_result: NotificationDispatchResult,
    ) -> str:
        """把測試通知 dispatch 結果整理成 redirect 後可顯示的摘要字串。"""
        sent_channels = _join_channels(dispatch_result.sent_channels)
        throttled_channels = _join_channels(dispatch_result.throttled_channels)
        failed_channels = _join_channels(dispatch_result.failed_channels)
        failure_details = _format_failure_details(dispatch_result.failure_details)
        return (
            f"測試通知結果：sent={sent_channels}；"
            f"throttled={throttled_channels}；failed={failed_channels}；"
            f"details={failure_details}"
        )


def _join_channels(channels: tuple[str, ...]) -> str:
    """把通知通道 tuple 轉成畫面摘要使用的文字。"""
    return ", ".join(channels) or "none"


def _format_failure_details(failure_details: dict[str, str] | None) -> str:
    """把通知失敗明細轉成穩定且易讀的摘要文字。"""
    if not failure_details:
        return "none"
    return " | ".join(
        f"{channel}: {detail}"
        for channel, detail in failure_details.items()
    )
