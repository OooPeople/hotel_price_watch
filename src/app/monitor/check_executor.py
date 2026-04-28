"""單一 watch 檢查流程的執行器。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.domain.entities import (
    DebugArtifact,
    NotificationState,
    PriceSnapshot,
)
from app.domain.enums import Availability, CheckErrorCode, SourceKind
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
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
    SqliteWatchItemRepository,
)
from app.monitor.notification_dispatch import NotificationDispatchCoordinator
from app.monitor.policies import (
    TaskLifecycleCheckpoint,
    TaskLifecycleDisposition,
    build_monitor_check_artifacts,
    build_runtime_control_recommendation,
    decide_error_handling,
    evaluate_task_lifecycle_disposition,
    reset_notification_state_after_success,
)
from app.monitor.runtime_logging import compact_log_value
from app.monitor.runtime_outcomes import WatchCheckOutcome
from app.monitor.startup_restore import resolve_watch_preferred_tab_id
from app.sites.registry import SiteRegistry


class WatchCheckExecutor:
    """執行單一 watch 的 capture、compare、notification 與 persistence 流程。"""

    def __init__(
        self,
        *,
        watch_item_repository: SqliteWatchItemRepository,
        site_registry: SiteRegistry,
        chrome_fetcher: ChromeCdpHtmlFetcher,
        runtime_write_repository: SqliteRuntimeWriteRepository,
        runtime_history_repository: SqliteRuntimeHistoryQueryRepository,
        notification_dispatch_coordinator: NotificationDispatchCoordinator,
        remove_from_schedule: Callable[[str], None],
        debug_retention_limit: int,
        now: Callable[[], datetime],
    ) -> None:
        """建立單次檢查流程所需的資料、瀏覽器與通知依賴。"""
        self._watch_item_repository = watch_item_repository
        self._site_registry = site_registry
        self._chrome_fetcher = chrome_fetcher
        self._runtime_write_repository = runtime_write_repository
        self._runtime_history_repository = runtime_history_repository
        self._notification_dispatch_coordinator = notification_dispatch_coordinator
        self._remove_from_schedule = remove_from_schedule
        self._debug_retention_limit = debug_retention_limit
        self._now = now

    async def run_watch_check_once(
        self,
        watch_item_id: str,
        *,
        reload_page: bool,
        excluded_tab_ids: tuple[str, ...],
    ) -> WatchCheckOutcome:
        """執行單一 watch item 檢查，並可選擇是否先重新整理頁面。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None or not watch_item.enabled or watch_item.paused_reason is not None:
            return WatchCheckOutcome(persisted=False)

        draft = self._watch_item_repository.get_draft(watch_item_id)
        adapter = self._site_registry.for_url(
            draft.seed_url if draft else watch_item.canonical_url
        )
        operation_url = adapter.build_browser_operation_url(
            watch_item=watch_item,
            draft=draft,
        )

        latest_snapshot = self._runtime_history_repository.get_latest_check_snapshot(
            watch_item_id
        )
        previous_snapshot = _previous_snapshot_from_latest(latest_snapshot)
        previous_effective_availability = (
            self._runtime_history_repository.get_last_effective_availability(watch_item_id)
        )
        notification_state = (
            self._runtime_history_repository.get_notification_state(watch_item_id)
            or NotificationState(watch_item_id=watch_item_id)
        )
        checked_at = self._now()
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
                preferred_tab_id=resolve_watch_preferred_tab_id(draft),
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
            return WatchCheckOutcome(
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
                return WatchCheckOutcome(
                    persisted=False,
                    tab_id=capture.tab.tab_id if capture is not None else None,
                    tab_url=capture.tab.url if capture is not None else None,
                )
            dispatch_result = await asyncio.to_thread(
                self._notification_dispatch_coordinator.dispatch_notification,
                watch_item=watch_item,
                check_result=check_result,
                notification_decision=replace(
                    notification_decision,
                    next_state=next_notification_state,
                ),
                attempted_at=checked_at,
            )

        if (
            await self._evaluate_task_disposition(
                watch_item_id,
                TaskLifecycleCheckpoint.BEFORE_PERSIST_RESULT,
            )
        ).should_discard:
            return WatchCheckOutcome(
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
            self._runtime_write_repository.persist_check_outcome,
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
            self._remove_from_schedule(watch_item_id)
        return WatchCheckOutcome(
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
                f"tab_id={compact_log_value(tab_id)}；"
                f"tab_url={compact_log_value(tab_url)}；"
                f"error={compact_log_value(f'{exc.__class__.__name__}: {exc}')}"
            )


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


def _format_browser_blocking_detail(
    outcome: BrowserBlockingOutcome | None,
) -> str | None:
    """把 browser blocking outcome 整理成 runtime event 的簡短細節。"""
    if outcome is None:
        return None
    return f"kind={outcome.kind}; reason={outcome.reason}; message={outcome.message}"
