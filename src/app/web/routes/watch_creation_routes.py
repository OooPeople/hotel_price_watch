"""watch 建立與專用 Chrome 分頁 preview 相關的本機 GUI routes。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.application.preview_guard import PreviewCooldownError
from app.bootstrap.container import AppContainer
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic
from app.web import request_helpers
from app.web.views import (
    render_chrome_tab_selection_page,
    render_new_watch_page,
)
from app.web.watch_creation_page_service import WatchCreationPageService
from app.web.watch_creation_workflow import WatchCreationWorkflow

CHROME_TAB_LIST_TIMEOUT_SECONDS = 8.0
CHROME_TAB_PREVIEW_TIMEOUT_SECONDS = 45.0


def build_watch_creation_router(container: AppContainer) -> APIRouter:
    """建立 watch creation 與 Chrome tab preview routes。"""
    router = APIRouter(tags=["web"])
    page_service = WatchCreationPageService(container)
    workflow = WatchCreationWorkflow(
        container,
        page_service=page_service,
        tab_list_timeout_seconds=CHROME_TAB_LIST_TIMEOUT_SECONDS,
        tab_preview_timeout_seconds=CHROME_TAB_PREVIEW_TIMEOUT_SECONDS,
    )

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
            tabs = await workflow.list_chrome_tabs()
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
        try:
            preview = await workflow.preview_from_seed_url(seed_url)
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
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=request_helpers.to_user_facing_error_message(exc),
                    diagnostics=diagnostics,
                    site_descriptors=container.site_registry.descriptors(),
                ),
                status_code=400,
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
        tabs = await workflow.safe_list_chrome_tabs()
        if not selected_tab_id:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message="請先選擇要抓取的 Chrome 分頁。",
                selected_tab_id=selected_tab_id or None,
                status_code=400,
            )
        try:
            tab_preview_result = await workflow.preview_from_chrome_tab(
                selected_tab_id=selected_tab_id,
                tabs=tabs,
            )
        except PreviewCooldownError as exc:
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message=str(exc),
                diagnostics=exc.diagnostics,
                selected_tab_id=selected_tab_id,
                status_code=429,
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
            return _chrome_tab_selection_response(
                page_service=page_service,
                tabs=tabs,
                error_message=request_helpers.to_user_facing_error_message(exc),
                diagnostics=diagnostics,
                selected_tab_id=selected_tab_id,
                status_code=400,
        )
        return HTMLResponse(
            render_new_watch_page(
                seed_url=tab_preview_result.preview.draft.seed_url,
                preview=tab_preview_result.preview,
                preview_cache_key=tab_preview_result.preview_cache_key,
                site_descriptors=container.site_registry.descriptors(),
            )
        )

    @router.post("/watches", response_class=HTMLResponse)
    async def create_watch(request: Request) -> Response:
        """建立新的 watch item，成功後導回列表頁。"""
        request_helpers.ensure_local_request_origin(request)
        form = await request_helpers.read_form_data(request)
        seed_url = form.get("seed_url", "")
        preview = None
        try:
            result = await workflow.create_watch_from_form(form)
            preview = result.preview
            watch_item = result.watch_item
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
                    or await workflow.safe_preview(seed_url),
                    site_descriptors=container.site_registry.descriptors(),
                ),
                status_code=400,
            )

        return RedirectResponse(
            url=f"/?message=已建立%20{watch_item.hotel_name}%20的監視",
            status_code=303,
        )

    return router


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

