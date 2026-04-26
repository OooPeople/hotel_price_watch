"""集中建立本機 app 需要的主要依賴。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.application.app_settings import AppSettingsService
from app.application.chrome_tab_preview import ChromeTabPreviewService
from app.application.notification_channel_test import NotificationChannelTestService
from app.application.preview_guard import PreviewAttemptGuard
from app.application.watch_creation_cache import WatchCreationPreviewCache
from app.application.watch_editor import WatchEditorService
from app.application.watch_lifecycle import WatchLifecycleCoordinator
from app.bootstrap.site_wiring import register_default_sites
from app.infrastructure.browser import ChromeCdpHtmlFetcher
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.monitor.runtime import ChromeDrivenMonitorRuntime
from app.notifiers import DesktopNotifier, DiscordWebhookNotifier, NtfyNotifier
from app.sites.registry import SiteRegistry

DEFAULT_DATABASE_PATH = Path("data") / "hotel_price_watch.db"


@dataclass(slots=True)
class AppContainer:
    """封裝目前 FastAPI GUI 會用到的主要依賴。"""

    instance_id: str
    database: SqliteDatabase
    app_settings_repository: SqliteAppSettingsRepository
    watch_item_repository: SqliteWatchItemRepository
    runtime_repository: SqliteRuntimeRepository
    site_registry: SiteRegistry
    app_settings_service: AppSettingsService
    notification_channel_test_service: NotificationChannelTestService
    watch_editor_service: WatchEditorService
    watch_lifecycle_coordinator: WatchLifecycleCoordinator
    chrome_tab_preview_service: ChromeTabPreviewService
    chrome_cdp_fetcher: ChromeCdpHtmlFetcher
    preview_attempt_guard: PreviewAttemptGuard
    watch_creation_preview_cache: WatchCreationPreviewCache
    monitor_runtime: ChromeDrivenMonitorRuntime | None = None
    monitor_runtime_auto_start_enabled: bool = True


def build_app_container(db_path: str | Path | None = None) -> AppContainer:
    """建立本機 app 的依賴容器，並初始化 SQLite。"""
    instance_id = os.getenv("HOTEL_PRICE_WATCH_INSTANCE_ID", "standalone")
    runtime_auto_start_enabled = os.getenv("HOTEL_PRICE_WATCH_RUNTIME_ENABLED", "1") != "0"
    database = SqliteDatabase(db_path or _resolve_database_path())
    database.initialize()

    app_settings_repository = SqliteAppSettingsRepository(database)
    watch_item_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)

    site_registry = SiteRegistry()
    chrome_cdp_fetcher = ChromeCdpHtmlFetcher()
    register_default_sites(site_registry, browser_fallback=chrome_cdp_fetcher)

    watch_editor_service = WatchEditorService(
        site_registry=site_registry,
        watch_item_repository=watch_item_repository,
    )
    app_settings_service = AppSettingsService(
        settings_repository=app_settings_repository,
    )
    notification_channel_test_service = NotificationChannelTestService(
        app_settings_service=app_settings_service,
        notifier_factory=_build_enabled_notifiers,
    )
    chrome_tab_preview_service = ChromeTabPreviewService(
        chrome_fetcher=chrome_cdp_fetcher,
        site_registry=site_registry,
    )
    monitor_runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_item_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=chrome_cdp_fetcher,
        app_settings_service=app_settings_service,
    )
    watch_lifecycle_coordinator = WatchLifecycleCoordinator(
        watch_item_repository=watch_item_repository,
        runtime_repository=runtime_repository,
        monitor_runtime=monitor_runtime,
    )

    return AppContainer(
        instance_id=instance_id,
        database=database,
        app_settings_repository=app_settings_repository,
        watch_item_repository=watch_item_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        app_settings_service=app_settings_service,
        notification_channel_test_service=notification_channel_test_service,
        watch_editor_service=watch_editor_service,
        watch_lifecycle_coordinator=watch_lifecycle_coordinator,
        chrome_tab_preview_service=chrome_tab_preview_service,
        chrome_cdp_fetcher=chrome_cdp_fetcher,
        preview_attempt_guard=PreviewAttemptGuard(),
        watch_creation_preview_cache=WatchCreationPreviewCache(),
        monitor_runtime=monitor_runtime,
        monitor_runtime_auto_start_enabled=runtime_auto_start_enabled,
    )


def _resolve_database_path() -> Path:
    """讀取本機 GUI 預設使用的 SQLite 路徑。"""
    return Path(os.getenv("HOTEL_PRICE_WATCH_DB_PATH", str(DEFAULT_DATABASE_PATH)))


def _build_enabled_notifiers(settings) -> tuple:
    """依全域設定建立通知測試與 runtime 共用的 notifier 清單。"""
    notifiers: list = []
    if settings.desktop_enabled:
        notifiers.append(DesktopNotifier())
    if settings.ntfy_enabled and settings.ntfy_topic is not None:
        notifiers.append(
            NtfyNotifier(
                server_url=settings.ntfy_server_url,
                topic=settings.ntfy_topic,
            )
        )
    if settings.discord_enabled and settings.discord_webhook_url is not None:
        notifiers.append(
            DiscordWebhookNotifier(
                webhook_url=settings.discord_webhook_url,
            )
        )
    return tuple(notifiers)
