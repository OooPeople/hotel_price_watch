"""啟動時恢復監視分頁的協調流程。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from typing import Protocol

from app.domain.entities import WatchItem
from app.domain.value_objects import SearchDraft
from app.monitor.runtime_logging import compact_log_value
from app.monitor.runtime_outcomes import WatchCheckOutcome
from app.sites.registry import SiteRegistry


class StartupRestoreCheckRunner(Protocol):
    """描述啟動恢復流程需要呼叫的單次檢查介面。"""

    def __call__(
        self,
        watch_item_id: str,
        *,
        reload_page: bool,
        excluded_tab_ids: tuple[str, ...],
    ) -> Awaitable[WatchCheckOutcome]:
        """執行單一 watch check 並回傳 tab assignment 結果。"""
        ...


class StartupRestoreDraftReader(Protocol):
    """描述啟動恢復流程需要的 draft 讀取介面。"""

    def get_draft(self, watch_item_id: str) -> SearchDraft | None:
        """讀取 watch 建立時保存的搜尋草稿。"""
        ...


class StartupRestoreScheduler(Protocol):
    """描述啟動恢復流程需要回寫 scheduler 的介面。"""

    def mark_check_completed(
        self,
        *,
        watch_item_id: str,
        completed_at: datetime,
        backoff_until: datetime | None = None,
    ) -> None:
        """標記啟動恢復中的檢查已完成。"""
        ...


class StartupRestoreStopSignal(Protocol):
    """描述啟動恢復流程用來判斷是否停止的最小介面。"""

    def is_set(self) -> bool:
        """回傳 runtime 是否已要求停止。"""
        ...


class BrowserAssignmentRestorer:
    """在 runtime 啟動時依序恢復 enabled watch 對應的 Chrome 分頁。"""

    def __init__(
        self,
        *,
        draft_reader: StartupRestoreDraftReader,
        site_registry: SiteRegistry,
        scheduler: StartupRestoreScheduler,
        check_runner: StartupRestoreCheckRunner,
        stop_event: StartupRestoreStopSignal,
        restore_delay_seconds: float,
        now: Callable[[], datetime],
    ) -> None:
        """建立啟動恢復流程所需的協作者。"""
        self._draft_reader = draft_reader
        self._site_registry = site_registry
        self._scheduler = scheduler
        self._check_runner = check_runner
        self._stop_event = stop_event
        self._restore_delay_seconds = restore_delay_seconds
        self._now = now

    async def restore_active_watch_tabs(
        self,
        active_watch_items: dict[str, WatchItem],
    ) -> None:
        """依序恢復目前啟用且未暫停的 watch Chrome 分頁。"""
        if not active_watch_items:
            print("啟動恢復監視分頁：沒有啟用且未暫停的監視。")
            return

        print(f"啟動恢復監視分頁：準備恢復 {len(active_watch_items)} 筆監視。")
        claimed_tab_ids: set[str] = set()
        for watch_item in active_watch_items.values():
            if self._stop_event.is_set():
                break
            await self._restore_single_watch_tab(
                watch_item=watch_item,
                claimed_tab_ids=claimed_tab_ids,
            )
            if self._restore_delay_seconds > 0 and not self._stop_event.is_set():
                await asyncio.sleep(self._restore_delay_seconds)

    async def _restore_single_watch_tab(
        self,
        *,
        watch_item: WatchItem,
        claimed_tab_ids: set[str],
    ) -> None:
        """恢復單一 watch 分頁並回寫本次成功使用的 tab id。"""
        fallback_url = watch_item.canonical_url
        preferred_tab_id = None
        try:
            draft = await asyncio.to_thread(
                self._draft_reader.get_draft,
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
            preferred_tab_id = resolve_watch_preferred_tab_id(draft)
            print(
                _format_startup_restore_attempt(
                    watch_item=watch_item,
                    fallback_url=fallback_url,
                    preferred_tab_id=preferred_tab_id,
                )
            )
            outcome = await self._check_runner(
                watch_item.id,
                reload_page=False,
                excluded_tab_ids=tuple(claimed_tab_ids),
            )
            if outcome.persisted and not outcome.removed_from_scheduler:
                with suppress(LookupError):
                    self._scheduler.mark_check_completed(
                        watch_item_id=watch_item.id,
                        completed_at=self._now(),
                        backoff_until=outcome.backoff_until,
                    )
            if outcome.tab_id is None or outcome.tab_url is None:
                raise RuntimeError(
                    outcome.failure_detail or "startup capture did not return a Chrome tab"
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


def resolve_watch_preferred_tab_id(draft: SearchDraft | None) -> str | None:
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
        f"hotel={compact_log_value(watch_item.hotel_name)}；"
        f"preferred_tab_id={compact_log_value(preferred_tab_id)}；"
        f"fallback_url={compact_log_value(fallback_url)}"
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
        f"hotel={compact_log_value(watch_item.hotel_name)}；"
        f"tab_id={compact_log_value(tab_id)}；"
        f"tab_url={compact_log_value(tab_url)}"
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
        f"hotel={compact_log_value(watch_item.hotel_name)}；"
        f"preferred_tab_id={compact_log_value(preferred_tab_id)}；"
        f"fallback_url={compact_log_value(fallback_url)}；"
        f"error={compact_log_value(error_text)}"
    )
