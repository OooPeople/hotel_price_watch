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
    WatchItem,
)
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    SourceKind,
)
from app.domain.notification_engine import compare_snapshots, evaluate_notification_rule
from app.domain.value_objects import SearchDraft
from app.domain.watch_lifecycle_state_machine import (
    WatchLifecycleContext,
    build_runtime_lifecycle_events,
)
from app.infrastructure.browser import ChromeCdpHtmlFetcher
from app.infrastructure.browser.page_strategy import (
    BrowserBlockedPageError,
    BrowserBlockingOutcome,
)
from app.infrastructure.db.repositories import (
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.monitor.policies import (
    TaskLifecycleCheckpoint,
    TaskLifecycleDisposition,
    build_monitor_check_artifacts,
    build_runtime_control_recommendation,
    decide_error_handling,
    evaluate_task_lifecycle_disposition,
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


@dataclass(frozen=True, slots=True)
class _WatchCheckOutcome:
    """描述一次 watch 檢查完成後，runtime 需要回饋給調度流程的摘要。"""

    persisted: bool
    tab_id: str | None = None
    tab_url: str | None = None
    backoff_until: datetime | None = None
    removed_from_scheduler: bool = False
    failure_detail: str | None = None


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
        self._startup_restore_task: asyncio.Task[None] | None = None
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
    ) -> _WatchCheckOutcome:
        """執行單一 watch item 檢查，並可選擇是否先重新整理頁面。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None or not watch_item.enabled or watch_item.paused_reason is not None:
            return _WatchCheckOutcome(persisted=False)

        draft = self._watch_item_repository.get_draft(watch_item_id)
        adapter = self._site_registry.for_url(
            draft.seed_url if draft else watch_item.canonical_url
        )
        operation_url = adapter.build_browser_operation_url(
            watch_item=watch_item,
            draft=draft,
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
        browser_blocking_outcome: BrowserBlockingOutcome | None = None
        failure_detail: str | None = None

        try:
            capture = await asyncio.to_thread(
                self._chrome_fetcher.capture_for_url,
                expected_url=operation_url,
                fallback_url=operation_url,
                preferred_tab_id=_resolve_watch_preferred_tab_id(draft),
                excluded_tab_ids=excluded_tab_ids,
                page_strategy=adapter.browser_page_strategy,
                reload=reload_page,
            )
            await self._save_browser_assignment(
                watch_item_id=watch_item_id,
                draft=draft,
                tab_id=capture.tab.tab_id,
                tab_url=capture.tab.url,
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
            if isinstance(exc, BrowserBlockedPageError):
                browser_blocking_outcome = exc.outcome
            failure_detail = f"{exc.__class__.__name__}: {exc}"
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
        if (
            await self._evaluate_task_disposition(
                watch_item_id,
                TaskLifecycleCheckpoint.AFTER_CAPTURE,
            )
        ).should_discard:
            return _WatchCheckOutcome(
                persisted=False,
                tab_id=capture.tab.tab_id if capture is not None else None,
                tab_url=capture.tab.url if capture is not None else None,
            )

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
            if (
                await self._evaluate_task_disposition(
                    watch_item_id,
                    TaskLifecycleCheckpoint.BEFORE_NOTIFICATION_DISPATCH,
                )
            ).should_discard:
                return _WatchCheckOutcome(
                    persisted=False,
                    tab_id=capture.tab.tab_id if capture is not None else None,
                    tab_url=capture.tab.url if capture is not None else None,
                )
            dispatch_result = await asyncio.to_thread(
                self._dispatch_notification,
                watch_item,
                check_result,
                replace(notification_decision, next_state=next_notification_state),
                checked_at,
            )

        if (
            await self._evaluate_task_disposition(
                watch_item_id,
                TaskLifecycleCheckpoint.BEFORE_PERSIST_RESULT,
            )
        ).should_discard:
            return _WatchCheckOutcome(
                persisted=False,
                tab_id=capture.tab.tab_id if capture is not None else None,
                tab_url=capture.tab.url if capture is not None else None,
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
        control_recommendation = build_runtime_control_recommendation(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
            next_snapshot=artifacts.latest_check_snapshot,
            error_handling=error_handling,
            error_code=error_code,
            occurred_at=checked_at,
            detail_text=_format_browser_blocking_detail(browser_blocking_outcome),
        )

        await asyncio.to_thread(
            self._runtime_repository.persist_check_outcome,
            latest_snapshot=artifacts.latest_check_snapshot,
            check_event=artifacts.check_event,
            notification_state=next_notification_state,
            control_watch_item=control_recommendation.watch_item,
            price_history_entry=artifacts.price_history_entry,
            debug_artifact=debug_artifact,
            runtime_state_events=build_runtime_lifecycle_events(
                context=WatchLifecycleContext(
                    watch_item=watch_item,
                    latest_snapshot=latest_snapshot,
                    next_snapshot=artifacts.latest_check_snapshot,
                ),
                control_decision=control_recommendation.lifecycle_decision,
                error_code=error_code,
                occurred_at=checked_at,
            ),
            debug_retention_limit=self._debug_retention_limit,
        )

        if control_recommendation.remove_from_scheduler:
            self._scheduler.remove_watch(watch_item_id)
        return _WatchCheckOutcome(
            persisted=True,
            tab_id=capture.tab.tab_id if capture is not None else None,
            tab_url=capture.tab.url if capture is not None else None,
            backoff_until=artifacts.latest_check_snapshot.backoff_until,
            removed_from_scheduler=control_recommendation.remove_from_scheduler,
            failure_detail=failure_detail,
        )

    async def _evaluate_task_disposition(
        self,
        watch_item_id: str,
        checkpoint: TaskLifecycleCheckpoint,
    ) -> TaskLifecycleDisposition:
        """重新讀取 control state，套用 continue-and-gate task lifecycle policy。"""
        current_watch = await asyncio.to_thread(
            self._watch_item_repository.get,
            watch_item_id,
        )
        return evaluate_task_lifecycle_disposition(
            watch_item=current_watch,
            checkpoint=checkpoint,
        )

    async def request_check_now(self, watch_item_id: str) -> None:
        """提供 GUI 立即檢查入口，並與背景排程共用同一個互斥執行任務。"""
        task = self._get_or_create_watch_check_task(watch_item_id)
        await asyncio.shield(task)

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
            await self._sync_watch_definitions(
                now=now,
                resumed_after_sleep=resumed_after_sleep,
            )
            startup_restore_task = self._startup_restore_task
            if startup_restore_task is not None and not startup_restore_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(startup_restore_task),
                        timeout=self._tick_seconds,
                    )
                except TimeoutError:
                    continue
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
                    assignment_watch_item_id: str = assignment.watch_item_id,
                ) -> None:
                    """在 assignment task 結束後清理背景 worker 追蹤。"""
                    if not completed.cancelled():
                        exc = completed.exception()
                        if exc is not None:
                            print(
                                "背景監視工作失敗："
                                f"watch_id={assignment_watch_item_id}；"
                                f"error={_compact_log_value(f'{exc.__class__.__name__}: {exc}')}"
                            )
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
        if not active_watch_items:
            print("啟動恢復監視分頁：沒有啟用且未暫停的監視。")
            return

        print(f"啟動恢復監視分頁：準備恢復 {len(active_watch_items)} 筆監視。")
        claimed_tab_ids: set[str] = set()
        for watch_item in active_watch_items.values():
            if self._stop_event.is_set():
                break
            fallback_url = watch_item.canonical_url
            preferred_tab_id = None
            try:
                draft = await asyncio.to_thread(
                    self._watch_item_repository.get_draft,
                    watch_item.id,
                )
                adapter = self._site_registry.for_url(
                    draft.seed_url if draft else watch_item.canonical_url
                )
                operation_url = adapter.build_browser_operation_url(
                    watch_item=watch_item,
                    draft=draft,
                )
                fallback_url = operation_url
                preferred_tab_id = _resolve_watch_preferred_tab_id(draft)
                print(
                    _format_startup_restore_attempt(
                        watch_item=watch_item,
                        fallback_url=fallback_url,
                        preferred_tab_id=preferred_tab_id,
                    )
                )
                outcome = await self._run_watch_check_once(
                    watch_item.id,
                    reload_page=False,
                    excluded_tab_ids=tuple(claimed_tab_ids),
                )
                if outcome.persisted and not outcome.removed_from_scheduler:
                    with suppress(LookupError):
                        self._scheduler.mark_check_completed(
                            watch_item_id=watch_item.id,
                            completed_at=_utcnow(),
                            backoff_until=outcome.backoff_until,
                        )
                if outcome.tab_id is None or outcome.tab_url is None:
                    raise RuntimeError(
                        outcome.failure_detail
                        or "startup capture did not return a Chrome tab"
                    )
                claimed_tab_ids.add(outcome.tab_id)
                print(
                    _format_startup_restore_success(
                        watch_item=watch_item,
                        tab_id=outcome.tab_id,
                        tab_url=outcome.tab_url,
                    )
                )
            except Exception as exc:
                print(
                    _format_startup_restore_failure(
                        watch_item=watch_item,
                        fallback_url=fallback_url,
                        preferred_tab_id=preferred_tab_id,
                        exc=exc,
                    )
                )
                continue
            if self._restore_delay_seconds > 0 and not self._stop_event.is_set():
                await asyncio.sleep(self._restore_delay_seconds)

    async def _save_browser_assignment(
        self,
        *,
        watch_item_id: str,
        draft: SearchDraft | None,
        tab_id: str,
        tab_url: str,
    ) -> None:
        """保存最近一次成功使用的 Chrome 分頁，作為下次操作的短期 hint。"""
        if draft is None:
            return
        try:
            await asyncio.to_thread(
                self._watch_item_repository.save_draft,
                watch_item_id,
                replace(
                    draft,
                    browser_tab_id=tab_id,
                    browser_page_url=tab_url,
                ),
            )
        except Exception as exc:
            print(
                "Chrome 分頁 hint 回寫失敗："
                f"watch_id={watch_item_id}；"
                f"tab_id={_compact_log_value(tab_id)}；"
                f"tab_url={_compact_log_value(tab_url)}；"
                f"error={_compact_log_value(f'{exc.__class__.__name__}: {exc}')}"
            )

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


def _map_runtime_exception_to_error_code_typed(exc: Exception) -> CheckErrorCode:
    """將 runtime 例外映射為監看錯誤代碼。"""
    if isinstance(exc, BrowserBlockedPageError):
        return _map_browser_blocking_outcome_to_error_code(exc.outcome)
    if isinstance(exc, (TimeoutError, PlaywrightTimeoutError)):
        return CheckErrorCode.NETWORK_TIMEOUT
    if isinstance(exc, PlaywrightError):
        return CheckErrorCode.NETWORK_ERROR
    return CheckErrorCode.NETWORK_ERROR


def _map_browser_blocking_outcome_to_error_code(
    outcome: BrowserBlockingOutcome,
) -> CheckErrorCode:
    """把站點阻擋 outcome 映射成目前 monitor policy 可理解的錯誤代碼。"""
    if outcome.kind == "rate_limited":
        return CheckErrorCode.RATE_LIMITED_429
    return CheckErrorCode.FORBIDDEN_403


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


def _format_browser_blocking_detail(
    outcome: BrowserBlockingOutcome | None,
) -> str | None:
    """把 browser blocking outcome 整理成 runtime event 的簡短細節。"""
    if outcome is None:
        return None
    return f"kind={outcome.kind}; reason={outcome.reason}; message={outcome.message}"


def _resolve_watch_preferred_tab_id(draft: SearchDraft | None) -> str | None:
    """讀取最近一次成功使用的分頁 hint；空值不參與 matching。"""
    if draft is None or draft.browser_tab_id is None:
        return None
    tab_id = draft.browser_tab_id.strip()
    return tab_id or None


def _format_startup_restore_attempt(
    *,
    watch_item: WatchItem,
    fallback_url: str,
    preferred_tab_id: str | None,
) -> str:
    """整理啟動恢復單一 watch 分頁前的終端機診斷訊息。"""
    return (
        "啟動恢復監視分頁："
        f"watch_id={watch_item.id}；"
        f"hotel={_compact_log_value(watch_item.hotel_name)}；"
        f"preferred_tab_id={_compact_log_value(preferred_tab_id)}；"
        f"fallback_url={_compact_log_value(fallback_url)}"
    )


def _format_startup_restore_success(
    *,
    watch_item: WatchItem,
    tab_id: str,
    tab_url: str,
) -> str:
    """整理啟動恢復單一 watch 分頁成功後的終端機診斷訊息。"""
    return (
        "啟動恢復監視分頁成功："
        f"watch_id={watch_item.id}；"
        f"hotel={_compact_log_value(watch_item.hotel_name)}；"
        f"tab_id={_compact_log_value(tab_id)}；"
        f"tab_url={_compact_log_value(tab_url)}"
    )


def _format_startup_restore_failure(
    *,
    watch_item: WatchItem,
    fallback_url: str,
    preferred_tab_id: str | None,
    exc: Exception,
) -> str:
    """整理啟動恢復單一 watch 分頁失敗時的終端機診斷訊息。"""
    error_text = f"{exc.__class__.__name__}: {exc}"
    return (
        "啟動恢復監視分頁失敗："
        f"watch_id={watch_item.id}；"
        f"hotel={_compact_log_value(watch_item.hotel_name)}；"
        f"preferred_tab_id={_compact_log_value(preferred_tab_id)}；"
        f"fallback_url={_compact_log_value(fallback_url)}；"
        f"error={_compact_log_value(error_text)}"
    )


def _compact_log_value(value: str | None, *, max_length: int = 320) -> str:
    """壓縮終端機診斷值，避免換行或過長 URL 讓啟動輸出難讀。"""
    if value is None or not value.strip():
        return "-"
    compacted = " ".join(value.strip().split())
    if len(compacted) <= max_length:
        return compacted
    return f"{compacted[: max_length - 3]}..."
