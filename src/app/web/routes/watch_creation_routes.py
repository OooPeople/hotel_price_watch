"""watch 建立與專用 Chrome 分頁 preview 相關的本機 GUI routes。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.application.preview_guard import PreviewCooldownError
from app.application.watch_editor import WatchCreationPreview
from app.bootstrap.container import AppContainer
from app.domain.enums import NotificationLeafKind
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic
from app.web import request_helpers
from app.web.views import (
    render_chrome_tab_selection_page,
    render_new_watch_page,
)
from app.web.watch_creation_page_service import WatchCreationPageService

CHROME_TAB_LIST_TIMEOUT_SECONDS = 8.0
CHROME_TAB_PREVIEW_TIMEOUT_SECONDS = 45.0


def build_watch_creation_router(container: AppContainer) -> APIRouter:
    """建立 watch creation 與 Chrome tab preview routes。"""
    router = APIRouter(tags=["web"])
    page_service = WatchCreationPageService(container)

    @router.get("/watches/new", response_class=HTMLResponse)
    def new_watch_page(seed_url: str = "", error: str | None = None) -> HTMLResponse:
        """顯示新增 watch item 的第一段 editor。"""
        return HTMLResponse(
            render_new_watch_page(
                seed_url=seed_url,
                error_message=error,
                site_descriptors=container.site_registry.descriptors(),
            )
        )

    @router.get("/watches/chrome-tabs", response_class=HTMLResponse)
    async def chrome_tab_list_page() -> HTMLResponse:
        """顯示目前可用的專用 Chrome `ikyu` 分頁清單。"""
        try:
            tabs = await asyncio.wait_for(
                run_in_threadpool(
                    container.chrome_tab_preview_service.list_tabs,
                ),
                timeout=CHROME_TAB_LIST_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=(),
                error_message="列出專用 Chrome 分頁逾時，請確認 Chrome 仍可附著後再重試。",
                diagnostics=getattr(exc, "diagnostics", ()),
                status_code=504,
            )
        except Exception as exc:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=(),
                error_message=request_helpers.to_user_facing_error_message(exc),
                diagnostics=getattr(exc, "diagnostics", ()),
                status_code=400,
            )
        return _chrome_tab_selection_response(
            page_service=page_service,
            tabs=tabs,
        )

    @router.post("/watches/preview", response_class=HTMLResponse)
    async def preview_watch_page(request: Request) -> HTMLResponse:
        """依 seed URL 解析草稿並顯示候選方案。"""
        request_helpers.ensure_local_request_origin(request)
        form = await request_helpers.read_form_data(request)
        seed_url = form.get("seed_url", "")
        site_name = page_service.site_name_for_seed_url(seed_url)
        try:
            container.preview_attempt_guard.ensure_allowed(site_name=site_name)
        except PreviewCooldownError as exc:
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=str(exc),
                    diagnostics=exc.diagnostics,
                    site_descriptors=container.site_registry.descriptors(),
                ),
                status_code=429,
            )
        try:
            preview = await run_in_threadpool(
                container.watch_editor_service.preview_from_seed_url,
                seed_url=seed_url,
            )
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            container.preview_attempt_guard.register_result(
                diagnostics=diagnostics,
                site_name=site_name,
            )
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=request_helpers.to_user_facing_error_message(exc),
                    diagnostics=diagnostics,
                    site_descriptors=container.site_registry.descriptors(),
                ),
                status_code=400,
            )
        preview = container.watch_editor_service.mark_existing_watch_for_preview(preview)
        site_name = page_service.site_name_for_preview(preview)
        container.preview_attempt_guard.register_result(
            diagnostics=preview.diagnostics,
            site_name=site_name,
        )
        return HTMLResponse(
            render_new_watch_page(
                seed_url=seed_url,
                preview=preview,
                site_descriptors=container.site_registry.descriptors(),
            )
        )

    @router.post("/watches/chrome-tabs/preview", response_class=HTMLResponse)
    async def preview_watch_from_chrome_tab(request: Request) -> HTMLResponse:
        """從使用者指定的專用 Chrome 分頁直接建立 preview。"""
        request_helpers.ensure_local_request_origin(request)
        form = await request_helpers.read_form_data(request)
        selected_tab_id = form.get("tab_id", "").strip()
        tabs = await _safe_list_chrome_tabs(container=container)
        if not selected_tab_id:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message="請先選擇要抓取的 Chrome 分頁。",
                selected_tab_id=selected_tab_id or None,
                status_code=400,
            )
        site_name = page_service.site_name_for_selected_tab(
            chrome_tabs=tabs,
            selected_tab_id=selected_tab_id,
        )
        try:
            container.preview_attempt_guard.ensure_allowed(site_name=site_name)
        except PreviewCooldownError as exc:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message=str(exc),
                diagnostics=exc.diagnostics,
                selected_tab_id=selected_tab_id,
                status_code=429,
            )
        try:
            preview = await asyncio.wait_for(
                run_in_threadpool(
                    container.chrome_tab_preview_service.preview_from_tab_id,
                    selected_tab_id,
                ),
                timeout=CHROME_TAB_PREVIEW_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message="抓取 Chrome 分頁逾時，請確認該分頁已完整載入後再重試。",
                selected_tab_id=selected_tab_id,
                status_code=504,
            )
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            container.preview_attempt_guard.register_result(
                diagnostics=diagnostics,
                site_name=site_name,
            )
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message=request_helpers.to_user_facing_error_message(exc),
                diagnostics=diagnostics,
                selected_tab_id=selected_tab_id,
                status_code=400,
        )
        preview = container.watch_editor_service.mark_existing_watch_for_preview(preview)
        preview_cache_key = container.watch_creation_preview_cache.store(preview)
        site_name = page_service.site_name_for_preview(preview)
        container.preview_attempt_guard.register_result(
            diagnostics=preview.diagnostics,
            site_name=site_name,
        )
        return HTMLResponse(
            render_new_watch_page(
                seed_url=preview.draft.seed_url,
                preview=preview,
                preview_cache_key=preview_cache_key,
                site_descriptors=container.site_registry.descriptors(),
            )
        )

    @router.post("/watches", response_class=HTMLResponse)
    async def create_watch(request: Request) -> Response:
        """建立新的 watch item，成功後導回列表頁。"""
        request_helpers.ensure_local_request_origin(request)
        form = await request_helpers.read_form_data(request)
        seed_url = form.get("seed_url", "")
        browser_tab_id = form.get("browser_tab_id", "").strip() or None
        preview_cache_key = form.get("preview_cache_key", "").strip() or None
        preview = None
        try:
            room_id, plan_id = request_helpers.parse_candidate_key(
                form.get("candidate_key", "")
            )
            target_price = request_helpers.parse_optional_decimal(
                form.get("target_price", "")
            )
            preview = await _resolve_watch_creation_preview(
                container=container,
                seed_url=seed_url,
                browser_tab_id=browser_tab_id,
                preview_cache_key=preview_cache_key,
            )
            preview = container.watch_editor_service.mark_existing_watch_for_preview(preview)
            watch_item = await run_in_threadpool(
                container.watch_editor_service.create_watch_item_from_preview,
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
            container.watch_creation_snapshot_service.persist_initial_snapshot_from_preview(
                preview=preview,
                watch_item_id=watch_item.id,
                room_id=room_id,
                plan_id=plan_id,
            )
            container.watch_creation_preview_cache.discard(preview_cache_key)
        except TimeoutError:
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message="抓取 Chrome 分頁逾時，請回到分頁選擇頁重新抓取。",
                    preview=preview,
                    site_descriptors=container.site_registry.descriptors(),
                ),
                status_code=504,
            )
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=request_helpers.to_user_facing_error_message(exc),
                    diagnostics=diagnostics,
                    preview=preview
                    or await _safe_preview(container=container, seed_url=seed_url),
                    site_descriptors=container.site_registry.descriptors(),
                ),
                status_code=400,
            )

        return RedirectResponse(
            url=f"/?message=已建立%20{watch_item.hotel_name}%20的監視",
            status_code=303,
        )

    return router


async def _safe_preview(
    *,
    container: AppContainer,
    seed_url: str,
) -> WatchCreationPreview | None:
    """在表單提交失敗時盡量重建 preview，失敗則回傳 `None`。"""
    try:
        return await run_in_threadpool(
            container.watch_editor_service.preview_from_seed_url,
            seed_url,
        )
    except Exception:
        return None


def _chrome_tab_selection_response(
    *,
    page_service: WatchCreationPageService,
    tabs: tuple[ChromeTabSummary, ...],
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    selected_tab_id: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """集中建立 Chrome 分頁選擇頁 response，避免 route 分支重複組 page context。"""
    context = page_service.chrome_tab_selection_context(
        tabs=tabs,
        error_message=error_message,
        diagnostics=diagnostics,
        selected_tab_id=selected_tab_id,
    )
    return HTMLResponse(
        render_chrome_tab_selection_page(
            tabs=context.tabs,
            error_message=context.error_message,
            diagnostics=context.diagnostics,
            selected_tab_id=context.selected_tab_id,
            existing_watch_ids_by_tab_id=context.existing_watch_ids_by_tab_id,
            site_descriptors=context.site_descriptors,
            site_labels_by_tab_id=context.site_labels_by_tab_id,
        ),
        status_code=status_code,
    )


async def _resolve_watch_creation_preview(
    *,
    container: AppContainer,
    seed_url: str,
    browser_tab_id: str | None,
    preview_cache_key: str | None,
) -> WatchCreationPreview:
    """依目前主線決定建立 watch 時應重建哪一份 preview。"""
    cached_preview = container.watch_creation_preview_cache.get(preview_cache_key)
    if cached_preview is not None:
        return cached_preview
    if browser_tab_id is not None:
        return await asyncio.wait_for(
            run_in_threadpool(
                container.chrome_tab_preview_service.preview_from_tab_id,
                browser_tab_id,
            ),
            timeout=CHROME_TAB_PREVIEW_TIMEOUT_SECONDS,
        )
    return await run_in_threadpool(
        container.watch_editor_service.preview_from_seed_url,
        seed_url,
    )


async def _safe_list_chrome_tabs(
    *,
    container: AppContainer,
) -> tuple[ChromeTabSummary, ...]:
    """嘗試列出 Chrome 分頁；若失敗則回傳空清單，供錯誤頁面沿用。"""
    try:
        return await run_in_threadpool(
            container.chrome_tab_preview_service.list_tabs,
        )
    except Exception:
        return ()
