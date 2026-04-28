"""watch creation routes 使用的流程協調 helper。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from starlette.concurrency import run_in_threadpool

from app.application.watch_editor import WatchCreationPreview
from app.bootstrap.container import AppContainer
from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind
from app.infrastructure.browser import ChromeTabSummary
from app.web import request_helpers
from app.web.watch_creation_page_service import WatchCreationPageService


@dataclass(frozen=True, slots=True)
class ChromeTabPreviewResult:
    """Chrome 分頁 preview 成功後 route 需要的結果資料。"""

    preview: WatchCreationPreview
    preview_cache_key: str


@dataclass(frozen=True, slots=True)
class CreatedWatchResult:
    """建立 watch 成功後 route 需要的結果資料。"""

    watch_item: WatchItem
    preview: WatchCreationPreview


class WatchCreationWorkflow:
    """集中 watch creation route 的 preview、cache 與建立流程。"""

    def __init__(
        self,
        container: AppContainer,
        *,
        page_service: WatchCreationPageService,
        tab_list_timeout_seconds: float,
        tab_preview_timeout_seconds: float,
    ) -> None:
        """保存建立流程所需服務與 timeout 設定。"""
        self._container = container
        self._page_service = page_service
        self._tab_list_timeout_seconds = tab_list_timeout_seconds
        self._tab_preview_timeout_seconds = tab_preview_timeout_seconds

    async def list_chrome_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """列出可供 preview 的 Chrome 分頁，逾時由呼叫端轉成 HTTP response。"""
        return await asyncio.wait_for(
            run_in_threadpool(
                self._container.chrome_tab_preview_service.list_tabs,
            ),
            timeout=self._tab_list_timeout_seconds,
        )

    async def safe_list_chrome_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """嘗試列出 Chrome 分頁；失敗時回傳空清單供錯誤頁使用。"""
        try:
            return await run_in_threadpool(
                self._container.chrome_tab_preview_service.list_tabs,
            )
        except Exception:
            return ()

    async def preview_from_seed_url(self, seed_url: str) -> WatchCreationPreview:
        """依 seed URL 建立 preview，並同步 preview guard 結果。"""
        site_name = self._page_service.site_name_for_seed_url(seed_url)
        self._container.preview_attempt_guard.ensure_allowed(site_name=site_name)
        try:
            preview = await run_in_threadpool(
                self._container.watch_editor_service.preview_from_seed_url,
                seed_url=seed_url,
            )
        except Exception as exc:
            self._container.preview_attempt_guard.register_result(
                diagnostics=getattr(exc, "diagnostics", ()),
                site_name=site_name,
            )
            raise

        preview = self._container.watch_editor_service.mark_existing_watch_for_preview(
            preview
        )
        self._container.preview_attempt_guard.register_result(
            diagnostics=preview.diagnostics,
            site_name=self._page_service.site_name_for_preview(preview),
        )
        return preview

    async def preview_from_chrome_tab(
        self,
        *,
        selected_tab_id: str,
        tabs: tuple[ChromeTabSummary, ...],
    ) -> ChromeTabPreviewResult:
        """依 Chrome tab id 建立 preview，並保存短期 cache 供建立 watch 使用。"""
        site_name = self._page_service.site_name_for_selected_tab(
            chrome_tabs=tabs,
            selected_tab_id=selected_tab_id,
        )
        self._container.preview_attempt_guard.ensure_allowed(site_name=site_name)
        try:
            preview = await asyncio.wait_for(
                run_in_threadpool(
                    self._container.chrome_tab_preview_service.preview_from_tab_id,
                    selected_tab_id,
                ),
                timeout=self._tab_preview_timeout_seconds,
            )
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                raise
            self._container.preview_attempt_guard.register_result(
                diagnostics=getattr(exc, "diagnostics", ()),
                site_name=site_name,
            )
            raise

        preview = self._container.watch_editor_service.mark_existing_watch_for_preview(
            preview
        )
        preview_cache_key = self._container.watch_creation_preview_cache.store(preview)
        self._container.preview_attempt_guard.register_result(
            diagnostics=preview.diagnostics,
            site_name=self._page_service.site_name_for_preview(preview),
        )
        return ChromeTabPreviewResult(
            preview=preview,
            preview_cache_key=preview_cache_key,
        )

    async def create_watch_from_form(self, form: dict[str, str]) -> CreatedWatchResult:
        """依建立表單建立 watch，並持久化 preview 初始價格。"""
        seed_url = form.get("seed_url", "")
        browser_tab_id = form.get("browser_tab_id", "").strip() or None
        preview_cache_key = form.get("preview_cache_key", "").strip() or None
        room_id, plan_id = request_helpers.parse_candidate_key(
            form.get("candidate_key", "")
        )
        target_price = request_helpers.parse_optional_decimal(
            form.get("target_price", "")
        )
        preview = await self.resolve_creation_preview(
            seed_url=seed_url,
            browser_tab_id=browser_tab_id,
            preview_cache_key=preview_cache_key,
        )
        preview = self._container.watch_editor_service.mark_existing_watch_for_preview(
            preview
        )
        watch_item = await self._create_watch_item(
            preview=preview,
            room_id=room_id,
            plan_id=plan_id,
            scheduler_interval_seconds=int(form.get("scheduler_interval_seconds", "600")),
            notification_rule_kind=NotificationLeafKind(
                form.get(
                    "notification_rule_kind",
                    NotificationLeafKind.ANY_DROP.value,
                )
            ),
            target_price=target_price,
        )
        self._container.watch_creation_snapshot_service.persist_initial_snapshot_from_preview(
            preview=preview,
            watch_item_id=watch_item.id,
            room_id=room_id,
            plan_id=plan_id,
        )
        self._container.watch_creation_preview_cache.discard(preview_cache_key)
        return CreatedWatchResult(watch_item=watch_item, preview=preview)

    async def resolve_creation_preview(
        self,
        *,
        seed_url: str,
        browser_tab_id: str | None,
        preview_cache_key: str | None,
    ) -> WatchCreationPreview:
        """依目前主線決定建立 watch 時應使用 cache、Chrome tab 或 seed preview。"""
        cached_preview = self._container.watch_creation_preview_cache.get(
            preview_cache_key
        )
        if cached_preview is not None:
            return cached_preview
        if browser_tab_id is not None:
            return await asyncio.wait_for(
                run_in_threadpool(
                    self._container.chrome_tab_preview_service.preview_from_tab_id,
                    browser_tab_id,
                ),
                timeout=self._tab_preview_timeout_seconds,
            )
        return await run_in_threadpool(
            self._container.watch_editor_service.preview_from_seed_url,
            seed_url,
        )

    async def safe_preview(self, seed_url: str) -> WatchCreationPreview | None:
        """在表單提交失敗時盡量重建 preview，失敗則回傳 `None`。"""
        try:
            return await run_in_threadpool(
                self._container.watch_editor_service.preview_from_seed_url,
                seed_url,
            )
        except Exception:
            return None

    async def _create_watch_item(
        self,
        *,
        preview: WatchCreationPreview,
        room_id: str,
        plan_id: str,
        scheduler_interval_seconds: int,
        notification_rule_kind: NotificationLeafKind,
        target_price: Decimal | None,
    ) -> WatchItem:
        """在線程池中執行同步 watch editor 建立動作。"""
        return await run_in_threadpool(
            self._container.watch_editor_service.create_watch_item_from_preview,
            preview=preview,
            room_id=room_id,
            plan_id=plan_id,
            scheduler_interval_seconds=scheduler_interval_seconds,
            notification_rule_kind=notification_rule_kind,
            target_price=target_price,
        )
