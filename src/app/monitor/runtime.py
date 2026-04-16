"""Chrome-driven background monitor runtime。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    DebugArtifact,
    NotificationState,
    PriceSnapshot,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    RuntimeStateEventKind,
    SourceKind,
)
from app.domain.notification_engine import compare_snapshots, evaluate_notification_rule
from app.domain.watch_runtime_state import derive_watch_runtime_state
from app.infrastructure.browser import ChromeCdpHtmlFetcher
from app.infrastructure.browser.ikyu_page_guards import IkyuBlockedPageError
from app.infrastructure.db.repositories import (
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.monitor.policies import (
    build_monitor_check_artifacts,
    decide_error_handling,
    reset_notification_state_after_success,
    should_trigger_wakeup_rescan,
)
from app.monitor.scheduler import MonitorScheduler
from app.notifiers import (
    DesktopNotifier,
    DiscordWebhookNotifier,
    NotificationDispatcher,
    NtfyNotifier,
    PersistentNotificationThrottle,
    build_notification_message,
)
from app.notifiers.base import Notifier
from app.sites.registry import SiteRegistry

NotifierFactory = Callable[[NotificationChannelSettings], tuple[Notifier, ...]]


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
        runtime_repository: SqliteRuntimeRepository,
        site_registry: SiteRegistry,
        chrome_fetcher: ChromeCdpHtmlFetcher,
        app_settings_service: AppSettingsService,
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
        self._runtime_repository = runtime_repository
        self._site_registry = site_registry
        self._chrome_fetcher = chrome_fetcher
        self._app_settings_service = app_settings_service
        self._scheduler = scheduler or MonitorScheduler()
        self._notifier_factory = notifier_factory or _build_enabled_notifiers
        self._notification_throttle = (
            notification_throttle or PersistentNotificationThrottle(runtime_repository)
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
        self._stop_event = asyncio.Event()
        self._inflight_tasks: dict[str, asyncio.Task[None]] = {}
        self._assignment_tasks: set[asyncio.Task[None]] = set()
        self._last_tick_at: datetime | None = None
        self._last_watch_sync_at: datetime | None = None
        self._dispatcher_cache: (
            tuple[NotificationChannelSettings, NotificationDispatcher] | None
        ) = None

    async def start(self) -> None:
        """啟動 background monitor loop。"""
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        active_watch_items = await self._sync_watch_definitions(now=_utcnow())
        if self._startup_restore_tabs:
            await self._restore_active_watch_tabs(active_watch_items)
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """停止 background monitor loop，並等待所有進行中的工作結束。"""
        self._stop_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        self._loop_task = None

        assignment_tasks = tuple(self._assignment_tasks)
        for task in assignment_tasks:
            task.cancel()
        for task in assignment_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._assignment_tasks.clear()

        inflight_tasks = tuple(self._inflight_tasks.values())
        for task in inflight_tasks:
            task.cancel()
        for task in inflight_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._inflight_tasks.clear()
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
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None or not watch_item.enabled or watch_item.paused_reason is not None:
            return

        draft = self._watch_item_repository.get_draft(watch_item_id)
        adapter = self._site_registry.for_url(
            draft.seed_url if draft else watch_item.canonical_url
        )

        latest_snapshot = self._runtime_repository.get_latest_check_snapshot(watch_item_id)
        previous_snapshot = _previous_snapshot_from_latest(latest_snapshot)
        previous_effective_availability = (
            self._runtime_repository.get_last_effective_availability(watch_item_id)
        )
        notification_state = (
            self._runtime_repository.get_notification_state(watch_item_id)
            or NotificationState(watch_item_id=watch_item_id)
        )
        checked_at = _utcnow()
        capture = None
        error_code: CheckErrorCode | None = None
        debug_artifact: DebugArtifact | None = None

        try:
            capture = await asyncio.to_thread(
                self._chrome_fetcher.refresh_capture_for_url,
                expected_url=watch_item.canonical_url,
                fallback_url=(
                    draft.browser_page_url
                    if draft is not None and draft.browser_page_url is not None
                    else draft.seed_url if draft is not None else watch_item.canonical_url
                ),
                preferred_tab_id=(
                    draft.browser_tab_id
                    if draft is not None and draft.browser_tab_id is not None
                    else None
                ),
            )
            current_snapshot = adapter.build_snapshot_from_browser_page(
                page_url=capture.tab.url,
                html=capture.html,
                target=watch_item.target,
            )
            error_code = _map_snapshot_error(current_snapshot)
            debug_artifact = _build_optional_debug_artifact(
                watch_item_id=watch_item_id,
                capture_html=capture.html,
                capture_url=capture.tab.url,
                capture_possible_throttling=capture.tab.possible_throttling,
                capture_was_discarded=capture.tab.was_discarded,
                error_code=error_code,
                checked_at=checked_at,
            )
        except Exception as exc:
            error_code = _map_runtime_exception_to_error_code_typed(exc)
            current_snapshot = PriceSnapshot(
                display_price_text=None,
                normalized_price_amount=None,
                currency=None,
                availability=Availability.UNKNOWN,
                source_kind=SourceKind.BROWSER,
            )
            debug_artifact = DebugArtifact(
                watch_item_id=watch_item_id,
                captured_at=checked_at,
                reason=error_code.value,
                payload_text=str(exc),
                source_url=(draft.seed_url if draft is not None else watch_item.canonical_url),
            )

        previous_failures = latest_snapshot.consecutive_failures if latest_snapshot else 0
        consecutive_failures = 0 if error_code is None else previous_failures + 1
        error_handling = decide_error_handling(
            checked_at=checked_at,
            error_code=error_code,
            consecutive_failures=consecutive_failures,
        )
        current_control_watch = await asyncio.to_thread(
            self._watch_item_repository.get,
            watch_item_id,
        )
        if (
            current_control_watch is None
            or not current_control_watch.enabled
            or current_control_watch.paused_reason is not None
        ):
            return

        check_result = compare_snapshots(
            checked_at=checked_at,
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
            previous_effective_availability=previous_effective_availability,
        )
        notification_decision = evaluate_notification_rule(
            rule=watch_item.notification_rule,
            check_result=check_result,
            notification_state=notification_state,
        )
        next_notification_state = replace(
            notification_decision.next_state,
            consecutive_failures=consecutive_failures,
        )
        if error_code is None:
            next_notification_state = reset_notification_state_after_success(
                next_notification_state
            )

        dispatch_result = None
        if notification_decision.should_notify:
            dispatch_result = await asyncio.to_thread(
                self._dispatch_notification,
                watch_item,
                check_result,
                replace(notification_decision, next_state=next_notification_state),
                checked_at,
            )

        artifacts = build_monitor_check_artifacts(
            watch_item_id=watch_item_id,
            check_result=check_result,
            notification_decision=replace(
                notification_decision,
                next_state=next_notification_state,
            ),
            error_code=error_code,
            error_handling=error_handling,
            dispatch_result=dispatch_result,
        )

        await asyncio.to_thread(
            self._runtime_repository.persist_check_outcome,
            latest_snapshot=artifacts.latest_check_snapshot,
            check_event=artifacts.check_event,
            notification_state=next_notification_state,
            price_history_entry=artifacts.price_history_entry,
            debug_artifact=debug_artifact,
            runtime_state_events=_build_runtime_state_events(
                watch_item=watch_item,
                latest_snapshot=latest_snapshot,
                next_snapshot=artifacts.latest_check_snapshot,
                error_handling=error_handling,
                error_code=error_code,
                checked_at=checked_at,
            ),
            debug_retention_limit=self._debug_retention_limit,
        )

        if error_handling.should_pause:
            paused_watch = replace(
                watch_item,
                enabled=True,
                paused_reason=(
                    error_handling.paused_reason.value
                    if error_handling.paused_reason is not None
                    else error_code.value if error_code is not None else "paused"
                ),
            )
            await asyncio.to_thread(self._watch_item_repository.save, paused_watch)
            self._scheduler.remove_watch(watch_item_id)

    async def request_check_now(self, watch_item_id: str) -> None:
        """提供 GUI 立即檢查入口，並與背景排程共用同一個互斥執行任務。"""
        task = self._get_or_create_watch_check_task(watch_item_id)
        await asyncio.shield(task)

    async def _run_loop(self) -> None:
        """持續同步 watch 定義並取出到期工作。"""
        while not self._stop_event.is_set():
            now = _utcnow()
            resumed_after_sleep = (
                self._last_tick_at is not None
                and now - self._last_tick_at >= self._wakeup_rescan_threshold
            )
            self._last_tick_at = now
            await self._sync_watch_definitions(
                now=now,
                resumed_after_sleep=resumed_after_sleep,
            )
            assignments = self._scheduler.dequeue_due_work(
                now=now,
                max_workers=self._max_workers,
            )
            for assignment in assignments:
                task = asyncio.create_task(
                    self._run_assignment(assignment.watch_item_id),
                    name=f"watch-assignment:{assignment.watch_item_id}",
                )
                self._assignment_tasks.add(task)

                def _forget_assignment_task(
                    completed: asyncio.Task[None],
                    *,
                    assignment_task: asyncio.Task[None] = task,
                ) -> None:
                    """在 assignment task 結束後清理背景 worker 追蹤。"""
                    del completed
                    self._assignment_tasks.discard(assignment_task)

                task.add_done_callback(_forget_assignment_task)
            await asyncio.sleep(self._tick_seconds)

    async def _run_assignment(self, watch_item_id: str) -> None:
        """執行單次排程工作，並在完成後更新下一次執行時間。"""
        task = self._get_or_create_watch_check_task(watch_item_id)
        try:
            await asyncio.shield(task)
        finally:
            latest_snapshot = self._runtime_repository.get_latest_check_snapshot(watch_item_id)
            backoff_until = latest_snapshot.backoff_until if latest_snapshot is not None else None
            with suppress(LookupError):
                self._scheduler.mark_finished(
                    watch_item_id=watch_item_id,
                    finished_at=_utcnow(),
                    backoff_until=backoff_until,
                )

    def _get_or_create_watch_check_task(
        self,
        watch_item_id: str,
    ) -> asyncio.Task[None]:
        """回傳同一個 watch 共用的檢查 task，避免背景排程與手動檢查並行執行。"""
        existing_task = self._inflight_tasks.get(watch_item_id)
        if existing_task is not None and not existing_task.done():
            return existing_task

        task = asyncio.create_task(
            self.run_watch_check_once(watch_item_id),
            name=f"watch-check:{watch_item_id}",
        )
        self._inflight_tasks[watch_item_id] = task

        def _forget_inflight_task(completed: asyncio.Task[None]) -> None:
            """在單次 watch 檢查結束後清理 inflight 追蹤。"""
            del completed
            self._inflight_tasks.pop(watch_item_id, None)

        task.add_done_callback(_forget_inflight_task)
        return task

    async def _sync_watch_definitions(
        self,
        *,
        now: datetime,
        resumed_after_sleep: bool = False,
    ) -> dict[str, WatchItem]:
        """把 DB 內 watch item 的實際狀態同步到 scheduler。"""
        watch_items = await asyncio.to_thread(self._watch_item_repository.list_all)
        self._last_watch_sync_at = now
        active_watch_items = {
            watch_item.id: watch_item
            for watch_item in watch_items
            if watch_item.enabled and watch_item.paused_reason is None
        }
        registered_ids = set(self._scheduler.list_registered_ids())

        for watch_item_id in tuple(registered_ids - set(active_watch_items.keys())):
            self._scheduler.remove_watch(watch_item_id)

        for watch_item in active_watch_items.values():
            latest_snapshot = await asyncio.to_thread(
                self._runtime_repository.get_latest_check_snapshot,
                watch_item.id,
            )
            if resumed_after_sleep and should_trigger_wakeup_rescan(
                resumed_at=now,
                last_checked_at=(
                    latest_snapshot.checked_at if latest_snapshot is not None else None
                ),
                backoff_until=(
                    latest_snapshot.backoff_until if latest_snapshot is not None else None
                ),
            ):
                self._scheduler.reschedule_now(
                    watch_item_id=watch_item.id,
                    now=now,
                )
            desired_next_run_at = _compute_next_run_at(
                latest_snapshot=latest_snapshot,
                interval_seconds=watch_item.scheduler_interval_seconds,
                now=now,
            )
            if watch_item.id not in registered_ids:
                self._scheduler.register_watch(
                    watch_item_id=watch_item.id,
                    interval_seconds=watch_item.scheduler_interval_seconds,
                    now=now,
                    next_run_at=desired_next_run_at,
                )
                continue
            self._scheduler.update_interval(
                watch_item_id=watch_item.id,
                interval_seconds=watch_item.scheduler_interval_seconds,
            )
        return active_watch_items

    async def _restore_active_watch_tabs(
        self,
        active_watch_items: dict[str, WatchItem],
    ) -> None:
        """在 runtime 啟動時低速恢復 enabled watch 對應的 Chrome 分頁。"""
        claimed_tab_ids: set[str] = set()
        for watch_item in active_watch_items.values():
            if self._stop_event.is_set():
                break
            draft = await asyncio.to_thread(
                self._watch_item_repository.get_draft,
                watch_item.id,
            )
            try:
                summary = await asyncio.to_thread(
                    self._chrome_fetcher.ensure_tab_for_url,
                    expected_url=watch_item.canonical_url,
                    fallback_url=(
                        draft.browser_page_url
                        if draft is not None and draft.browser_page_url is not None
                        else draft.seed_url if draft is not None else watch_item.canonical_url
                    ),
                    preferred_tab_id=(
                        draft.browser_tab_id
                        if draft is not None and draft.browser_tab_id is not None
                        else None
                    ),
                    excluded_tab_ids=tuple(claimed_tab_ids),
                )
                claimed_tab_ids.add(summary.tab_id)
            except Exception:
                continue
            if self._restore_delay_seconds > 0 and not self._stop_event.is_set():
                await asyncio.sleep(self._restore_delay_seconds)

    def _dispatch_notification(
        self,
        watch_item: WatchItem,
        check_result,
        notification_decision,
        attempted_at: datetime,
    ):
        """依全域設定建立 notifier 並實際送出通知。"""
        settings = self._app_settings_service.get_notification_channel_settings()
        dispatcher = self._get_or_build_dispatcher(settings)
        if dispatcher is None:
            return None
        message = build_notification_message(
            watch_item=watch_item,
            check_result=check_result,
            decision=notification_decision,
        )
        return dispatcher.dispatch(
            message=message,
            attempted_at=attempted_at,
        )

    def _get_or_build_dispatcher(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationDispatcher | None:
        """在設定未變動時重用 dispatcher，避免每次檢查都重新建立。"""
        if self._dispatcher_cache is not None:
            cached_settings, cached_dispatcher = self._dispatcher_cache
            if cached_settings == settings:
                return cached_dispatcher

        enabled_notifiers = self._notifier_factory(settings)
        if not enabled_notifiers:
            self._dispatcher_cache = None
            return None

        dispatcher = NotificationDispatcher(
            notifiers=tuple(enabled_notifiers),
            throttle=self._notification_throttle,
            cooldown_seconds_by_channel={
                "desktop": 60,
                "ntfy": 300,
                "discord": 300,
            },
        )
        self._dispatcher_cache = (settings, dispatcher)
        return dispatcher


def _previous_snapshot_from_latest(latest_snapshot) -> PriceSnapshot | None:
    """把 latest snapshot 摘要還原成 compare engine 可接受的前次快照。"""
    if latest_snapshot is None:
        return None
    return PriceSnapshot(
        display_price_text=None,
        normalized_price_amount=latest_snapshot.normalized_price_amount,
        currency=latest_snapshot.currency,
        availability=latest_snapshot.availability,
        source_kind=SourceKind.BROWSER,
    )


def _compute_next_run_at(
    *,
    latest_snapshot,
    interval_seconds: int,
    now: datetime,
) -> datetime:
    """依最新檢查摘要決定 runtime 啟動後的下一次執行時間。"""
    if latest_snapshot is None:
        return now
    if latest_snapshot.backoff_until is not None and latest_snapshot.backoff_until > now:
        return latest_snapshot.backoff_until
    due_at = latest_snapshot.checked_at + timedelta(seconds=interval_seconds)
    return due_at if due_at > now else now


def _map_snapshot_error(snapshot: PriceSnapshot) -> CheckErrorCode | None:
    """把 snapshot 狀態映射成 monitor 層的錯誤代碼。"""
    if snapshot.availability is Availability.PARSE_ERROR:
        return CheckErrorCode.PARSE_FAILED
    if snapshot.availability is Availability.TARGET_MISSING:
        return CheckErrorCode.TARGET_MISSING
    return None


def _map_runtime_exception_to_error_code(exc: Exception) -> CheckErrorCode:
    """把 runtime 例外粗略映射成目前可用的錯誤代碼。"""
    message = str(exc)
    if "阻擋頁面" in message or "403" in message:
        return CheckErrorCode.FORBIDDEN_403
    if "timeout" in message.lower() or "逾時" in message:
        return CheckErrorCode.NETWORK_TIMEOUT
    return CheckErrorCode.NETWORK_ERROR


def _map_runtime_exception_to_error_code_typed(exc: Exception) -> CheckErrorCode:
    """將 runtime 例外映射為監看錯誤代碼。"""
    if isinstance(exc, IkyuBlockedPageError):
        return CheckErrorCode.FORBIDDEN_403
    if isinstance(exc, (TimeoutError, PlaywrightTimeoutError)):
        return CheckErrorCode.NETWORK_TIMEOUT
    if isinstance(exc, PlaywrightError):
        return CheckErrorCode.NETWORK_ERROR
    return CheckErrorCode.NETWORK_ERROR


def _build_optional_debug_artifact(
    *,
    watch_item_id: str,
    capture_html: str,
    capture_url: str,
    capture_possible_throttling: bool,
    capture_was_discarded: bool | None,
    error_code: CheckErrorCode | None,
    checked_at: datetime,
) -> DebugArtifact | None:
    """依本次檢查訊號決定是否保存 runtime debug artifact。"""
    reason = None
    if error_code is not None:
        reason = error_code.value
    elif capture_was_discarded is True:
        reason = "page_was_discarded"
    elif capture_possible_throttling:
        reason = "possible_throttling"

    if reason is None:
        return None

    return DebugArtifact(
        watch_item_id=watch_item_id,
        captured_at=checked_at,
        reason=reason,
        payload_text=capture_html,
        source_url=capture_url,
    )


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


def _build_runtime_state_events(
    *,
    watch_item: WatchItem,
    latest_snapshot,
    next_snapshot,
    error_handling,
    error_code: CheckErrorCode | None,
    checked_at: datetime,
) -> tuple[RuntimeStateEvent, ...]:
    """依前後狀態差異整理正式 runtime 狀態轉移事件。"""
    events: list[RuntimeStateEvent] = []
    previous_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        now=checked_at,
    )
    next_watch_item = (
        replace(
            watch_item,
            enabled=True,
            paused_reason=(
                error_handling.paused_reason.value
                if error_handling.paused_reason is not None
                else error_code.value if error_code is not None else "paused"
            ),
        )
        if error_handling.should_pause
        else watch_item
    )
    current_state = derive_watch_runtime_state(
        watch_item=next_watch_item,
        latest_snapshot=next_snapshot,
        now=checked_at,
    )

    if error_handling.should_pause and error_handling.paused_reason is CheckErrorCode.FORBIDDEN_403:
        events.append(
            RuntimeStateEvent(
                watch_item_id=watch_item.id,
                occurred_at=checked_at,
                event_kind=RuntimeStateEventKind.PAUSE_DUE_TO_HTTP_403,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    previous_backoff = latest_snapshot.backoff_until if latest_snapshot is not None else None
    next_backoff = next_snapshot.backoff_until
    if previous_backoff is None and next_backoff is not None:
        events.append(
            RuntimeStateEvent(
                watch_item_id=watch_item.id,
                occurred_at=checked_at,
                event_kind=RuntimeStateEventKind.ENTERED_BACKOFF,
                from_state=previous_state,
                to_state=current_state,
            )
        )
    elif previous_backoff is not None and next_backoff is None:
        events.append(
            RuntimeStateEvent(
                watch_item_id=watch_item.id,
                occurred_at=checked_at,
                event_kind=RuntimeStateEventKind.CLEARED_BACKOFF,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    previous_degraded = latest_snapshot.is_degraded if latest_snapshot is not None else False
    next_degraded = next_snapshot.is_degraded
    if not previous_degraded and next_degraded:
        events.append(
            RuntimeStateEvent(
                watch_item_id=watch_item.id,
                occurred_at=checked_at,
                event_kind=RuntimeStateEventKind.ENTERED_DEGRADED,
                from_state=previous_state,
                to_state=current_state,
            )
        )
    elif previous_degraded and not next_degraded:
        events.append(
            RuntimeStateEvent(
                watch_item_id=watch_item.id,
                occurred_at=checked_at,
                event_kind=RuntimeStateEventKind.CLEARED_DEGRADED,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    if (
        latest_snapshot is not None
        and latest_snapshot.last_error_code == CheckErrorCode.FORBIDDEN_403.value
        and error_code is None
    ):
        events.append(
            RuntimeStateEvent(
                watch_item_id=watch_item.id,
                occurred_at=checked_at,
                event_kind=RuntimeStateEventKind.RECOVERED_AFTER_SUCCESS,
                from_state=previous_state,
                to_state=current_state,
            )
        )

    return tuple(events)
