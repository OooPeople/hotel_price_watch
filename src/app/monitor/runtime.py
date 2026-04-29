"""Chrome-driven background monitor runtime。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import WatchItem
from app.infrastructure.browser import ChromeCdpHtmlFetcher
from app.infrastructure.db.repositories import (
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
    SqliteWatchItemRepository,
)
from app.monitor.assignment_coordinator import WatchAssignmentCoordinator
from app.monitor.check_executor import WatchCheckExecutor
from app.monitor.notification_dispatch import (
    NotificationDispatchCoordinator,
    NotifierFactory,
)
from app.monitor.runtime_outcomes import WatchCheckOutcome
from app.monitor.scheduler import MonitorScheduler
from app.monitor.startup_restore import BrowserAssignmentRestorer
from app.monitor.watch_sync_coordinator import WatchDefinitionSyncCoordinator
from app.notifiers import (
    DesktopNotifier,
    DiscordWebhookNotifier,
    NtfyNotifier,
    PersistentNotificationThrottle,
)
from app.notifiers.base import Notifier
from app.sites.registry import SiteRegistry


@dataclass(frozen=True, slots=True)
class MonitorRuntimeStatus:
    """提供 GUI 與 health endpoint 使用的 background monitor 狀態摘要。"""

    is_running: bool
    enabled_watch_count: int
    registered_watch_count: int
    inflight_watch_count: int
    chrome_debuggable: bool
    last_tick_at: datetime | None
    last_watch_sync_at: datetime | None


class ChromeDrivenMonitorRuntime:
    """負責以專用 Chrome session 執行背景輪詢與通知。"""

    def __init__(
        self,
        *,
        watch_item_repository: SqliteWatchItemRepository,
        site_registry: SiteRegistry,
        chrome_fetcher: ChromeCdpHtmlFetcher,
        app_settings_service: AppSettingsService,
        runtime_write_repository: SqliteRuntimeWriteRepository | None = None,
        runtime_history_repository: SqliteRuntimeHistoryQueryRepository | None = None,
        scheduler: MonitorScheduler | None = None,
        notifier_factory: NotifierFactory | None = None,
        notification_throttle: PersistentNotificationThrottle | None = None,
        tick_seconds: float = 1.0,
        max_workers: int = 2,
        debug_retention_limit: int = 20,
        wakeup_rescan_threshold_seconds: float = 120.0,
        startup_restore_tabs: bool = True,
        restore_delay_seconds: float = 2.5,
    ) -> None:
        """建立 background monitor runtime 所需的主要依賴。"""
        self._watch_item_repository = watch_item_repository
        if runtime_write_repository is None or runtime_history_repository is None:
            raise ValueError("runtime write/history repositories are required")
        self._runtime_write_repository = runtime_write_repository
        self._runtime_history_repository = runtime_history_repository
        self._site_registry = site_registry
        self._chrome_fetcher = chrome_fetcher
        self._scheduler = scheduler or MonitorScheduler()
        self._notifier_factory = notifier_factory or _build_enabled_notifiers
        self._notification_throttle = (
            notification_throttle
            or PersistentNotificationThrottle(self._runtime_write_repository)
        )
        self._tick_seconds = tick_seconds
        self._max_workers = max_workers
        self._debug_retention_limit = debug_retention_limit
        self._wakeup_rescan_threshold = timedelta(
            seconds=wakeup_rescan_threshold_seconds
        )
        self._startup_restore_tabs = startup_restore_tabs
        self._restore_delay_seconds = restore_delay_seconds
        self._loop_task: asyncio.Task[None] | None = None
        self._startup_restore_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._inflight_tasks: dict[str, asyncio.Task[None]] = {}
        self._assignment_tasks: set[asyncio.Task[None]] = set()
        self._last_tick_at: datetime | None = None
        self._last_watch_sync_at: datetime | None = None
        self._notification_dispatch_coordinator = NotificationDispatchCoordinator(
            app_settings_service=app_settings_service,
            notifier_factory=self._notifier_factory,
            notification_throttle=self._notification_throttle,
        )
        self._check_executor = WatchCheckExecutor(
            watch_item_repository=self._watch_item_repository,
            site_registry=self._site_registry,
            chrome_fetcher=self._chrome_fetcher,
            runtime_write_repository=self._runtime_write_repository,
            runtime_history_repository=self._runtime_history_repository,
            notification_dispatch_coordinator=self._notification_dispatch_coordinator,
            remove_from_schedule=self._scheduler.remove_watch,
            debug_retention_limit=self._debug_retention_limit,
            now=_utcnow,
        )
        self._assignment_coordinator = WatchAssignmentCoordinator(
            scheduler=self._scheduler,
            check_runner=self.run_watch_check_once,
            latest_snapshot_reader=self._runtime_history_repository,
            now=_utcnow,
        )
        self._watch_sync_coordinator = WatchDefinitionSyncCoordinator(
            watch_item_reader=self._watch_item_repository,
            latest_snapshot_reader=self._runtime_history_repository,
            scheduler=self._scheduler,
            now=_utcnow,
        )
        self._startup_restorer = BrowserAssignmentRestorer(
            draft_reader=self._watch_item_repository,
            site_registry=self._site_registry,
            scheduler=self._scheduler,
            check_runner=self._run_watch_check_once,
            stop_event=self._stop_event,
            restore_delay_seconds=self._restore_delay_seconds,
            now=_utcnow,
        )
        self._inflight_tasks = self._assignment_coordinator.inflight_tasks
        self._assignment_tasks = self._assignment_coordinator.assignment_tasks

    async def start(self) -> None:
        """啟動 background monitor loop。"""
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        active_watch_items = await self._sync_watch_definitions()
        if self._startup_restore_tabs:
            self._startup_restore_task = asyncio.create_task(
                self._restore_active_watch_tabs(active_watch_items)
            )
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """停止 background monitor loop，並等待所有進行中的工作結束。"""
        self._stop_event.set()
        if self._startup_restore_task is not None:
            self._startup_restore_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._startup_restore_task
        self._startup_restore_task = None

        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        self._loop_task = None

        await self._assignment_coordinator.cancel_assignment_tasks()
        await self._assignment_coordinator.cancel_inflight_tasks()
        self._scheduler.clear()

    def get_status(self) -> MonitorRuntimeStatus:
        """回傳目前 background runtime 的可觀測性摘要。"""
        enabled_watch_count = sum(
            1
            for watch_item in self._watch_item_repository.list_all()
            if watch_item.enabled and watch_item.paused_reason is None
        )
        return MonitorRuntimeStatus(
            is_running=self._loop_task is not None and not self._loop_task.done(),
            enabled_watch_count=enabled_watch_count,
            registered_watch_count=len(self._scheduler.list_registered_ids()),
            inflight_watch_count=len(self._inflight_tasks),
            chrome_debuggable=self._chrome_fetcher.is_debuggable_chrome_running(),
            last_tick_at=self._last_tick_at,
            last_watch_sync_at=self._last_watch_sync_at,
        )

    async def run_watch_check_once(self, watch_item_id: str) -> None:
        """執行單一 watch item 的刷新、解析、持久化與通知流程。"""
        await self._run_watch_check_once(
            watch_item_id,
            reload_page=True,
            excluded_tab_ids=(),
        )

    async def _run_watch_check_once(
        self,
        watch_item_id: str,
        *,
        reload_page: bool,
        excluded_tab_ids: tuple[str, ...],
    ) -> WatchCheckOutcome:
        """委派單次檢查 executor，保留啟動恢復與測試使用的舊入口。"""
        return await self._check_executor.run_watch_check_once(
            watch_item_id,
            reload_page=reload_page,
            excluded_tab_ids=excluded_tab_ids,
        )

    async def request_check_now(self, watch_item_id: str) -> None:
        """提供 GUI 立即檢查入口，並與背景排程共用同一個互斥執行任務。"""
        await self._assignment_coordinator.request_check_now(watch_item_id)

    def remove_watch_from_schedule(self, watch_item_id: str) -> None:
        """依 lifecycle state machine 決策立即移除 scheduler active set。"""
        self._scheduler.remove_watch(watch_item_id)

    async def _run_loop(self) -> None:
        """持續同步 watch 定義並取出到期工作。"""
        while not self._stop_event.is_set():
            now = _utcnow()
            resumed_after_sleep = (
                self._last_tick_at is not None
                and now - self._last_tick_at >= self._wakeup_rescan_threshold
            )
            self._last_tick_at = now
            await self._sync_watch_definitions(resumed_after_sleep=resumed_after_sleep)
            startup_restore_task = self._startup_restore_task
            if startup_restore_task is not None and not startup_restore_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(startup_restore_task),
                        timeout=self._tick_seconds,
                    )
                except TimeoutError:
                    continue
            self._assignment_coordinator.dispatch_due_assignments(
                now=now,
                max_workers=self._max_workers,
            )
            await asyncio.sleep(self._tick_seconds)

    async def _run_assignment(self, watch_item_id: str) -> None:
        """執行單次排程工作，並在完成後更新下一次執行時間。"""
        await self._assignment_coordinator.run_assignment(watch_item_id)

    async def _sync_watch_definitions(
        self,
        *,
        resumed_after_sleep: bool = False,
        now: datetime | None = None,
    ) -> dict[str, WatchItem]:
        """把 DB 內 watch item 的實際狀態同步到 scheduler。"""
        active_watch_items, synced_at = (
            await self._watch_sync_coordinator.sync_watch_definitions(
                resumed_after_sleep=resumed_after_sleep,
                now=now,
            )
        )
        self._last_watch_sync_at = synced_at
        return active_watch_items

    async def _restore_active_watch_tabs(
        self,
        active_watch_items: dict[str, WatchItem],
    ) -> None:
        """委派啟動恢復協調器恢復 enabled watch 對應的 Chrome 分頁。"""
        await self._startup_restorer.restore_active_watch_tabs(active_watch_items)


def _build_enabled_notifiers(
    settings: NotificationChannelSettings,
) -> tuple[Notifier, ...]:
    """依全域設定建立目前啟用的 notifier 清單。"""
    notifiers: list[Notifier] = []
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


def _utcnow() -> datetime:
    """集中建立 runtime 使用的 UTC 現在時間。"""
    return datetime.now(UTC)
