"""watch 列表、詳細頁與控制操作相關的本機 GUI routes。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.application.watch_lifecycle import WatchLifecycleError
from app.bootstrap.container import AppContainer
from app.web import request_helpers
from app.web.views import (
    render_watch_detail_page,
    render_watch_list_page,
)
from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_PAYLOAD_KEYS,
    WATCH_LIST_PAYLOAD_KEYS,
)
from app.web.watch_fragment_payloads import (
    build_watch_detail_fragment_payload,
    build_watch_list_fragment_payload,
)
from app.web.watch_page_service import WatchPageService


def build_watch_router(container: AppContainer) -> APIRouter:
    """建立 watch list / detail / control routes。"""
    router = APIRouter(tags=["web"])
    page_service = WatchPageService(container)

    @router.get("/", response_class=HTMLResponse)
    def watch_list(request: Request) -> HTMLResponse:
        """顯示 watch item 列表頁。"""
        flash_message = request.query_params.get("message")
        context = page_service.build_watch_list_context()
        html = render_watch_list_page(
            watch_items=context.watch_items,
            latest_snapshots_by_watch_id=context.latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=context.recent_price_history_by_watch_id,
            today_notification_count=context.today_notification_count,
            flash_message=flash_message,
            runtime_status=context.runtime_status,
            use_24_hour_time=context.display_settings.use_24_hour_time,
            initial_fragment_version=page_service.build_watch_list_revision(),
        )
        return HTMLResponse(html)

    @router.get("/fragments/watch-list")
    def watch_list_fragments() -> dict[str, str]:
        """回傳首頁局部更新所需的 runtime 與 watch 列表片段。"""
        context = page_service.build_watch_list_context()
        return build_watch_list_fragment_payload(
            context=context,
            version=page_service.build_watch_list_revision(),
        ).to_dict()

    @router.get("/fragments/watch-list/version")
    def watch_list_fragment_version() -> dict[str, str]:
        """回傳首頁局部更新使用的資料版本。"""
        return {WATCH_LIST_PAYLOAD_KEYS.version: page_service.build_watch_list_revision()}

    @router.get("/watches/{watch_item_id}", response_class=HTMLResponse)
    def watch_detail_page(watch_item_id: str, request: Request) -> HTMLResponse:
        """顯示單一 watch item 的歷史與錯誤摘要。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            return HTMLResponse("watch item not found", status_code=404)
        context = page_service.build_watch_detail_context(watch_item)
        html = render_watch_detail_page(
            watch_item=context.watch_item,
            latest_snapshot=context.latest_snapshot,
            check_events=context.check_events,
            notification_state=context.notification_state,
            debug_artifacts=context.debug_artifacts,
            runtime_state_events=context.runtime_state_events,
            flash_message=request.query_params.get("message"),
            use_24_hour_time=context.display_settings.use_24_hour_time,
            initial_fragment_version=page_service.build_watch_detail_revision(
                watch_item
            ),
        )
        return HTMLResponse(html)

    @router.get("/watches/{watch_item_id}/fragments")
    def watch_detail_fragments(watch_item_id: str) -> dict[str, str]:
        """回傳 watch 詳細頁局部更新所需的摘要、歷史與 debug 片段。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise HTTPException(status_code=404, detail="watch item not found")
        context = page_service.build_watch_detail_context(watch_item)
        return build_watch_detail_fragment_payload(
            context=context,
            version=page_service.build_watch_detail_revision(watch_item),
        ).to_dict()

    @router.get("/watches/{watch_item_id}/fragments/version")
    def watch_detail_fragment_version(watch_item_id: str) -> dict[str, str]:
        """回傳 watch 詳細頁局部更新使用的資料版本。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise HTTPException(status_code=404, detail="watch item not found")
        return {
            WATCH_DETAIL_PAYLOAD_KEYS.version: page_service.build_watch_detail_revision(
                watch_item
            )
        }

    @router.post("/watches/{watch_item_id}/delete", response_class=HTMLResponse)
    async def delete_watch(watch_item_id: str, request: Request) -> Response:
        """刪除指定 watch item，並回到列表頁。"""
        request_helpers.ensure_local_request_origin(request)
        await run_in_threadpool(
            container.watch_editor_service.delete_watch_item,
            watch_item_id,
        )
        if _is_watch_list_fragment_request(request):
            return _watch_list_control_response(
                page_service=page_service,
                flash_message="已刪除監視",
            )
        return RedirectResponse(
            url="/?message=已刪除%20監視",
            status_code=303,
        )

    @router.post("/watches/{watch_item_id}/enable", response_class=HTMLResponse)
    async def enable_watch(watch_item_id: str, request: Request) -> Response:
        """啟用指定 watch item。"""
        request_helpers.ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_lifecycle_coordinator.enable_watch,
            watch_item_id,
        )
        if _is_watch_list_fragment_request(request):
            return _watch_list_control_response(
                page_service=page_service,
                flash_message="已啟用監視",
            )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已啟用%20監視",
            status_code=303,
        )

    @router.post("/watches/{watch_item_id}/disable", response_class=HTMLResponse)
    async def disable_watch(watch_item_id: str, request: Request) -> Response:
        """停用指定 watch item。"""
        request_helpers.ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_lifecycle_coordinator.disable_watch,
            watch_item_id,
        )
        if _is_watch_list_fragment_request(request):
            return _watch_list_control_response(
                page_service=page_service,
                flash_message="已停用監視",
            )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已停用%20監視",
            status_code=303,
        )

    @router.post("/watches/{watch_item_id}/pause", response_class=HTMLResponse)
    async def pause_watch(watch_item_id: str, request: Request) -> Response:
        """暫停指定 watch item。"""
        request_helpers.ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_lifecycle_coordinator.pause_watch,
            watch_item_id,
        )
        if _is_watch_list_fragment_request(request):
            return _watch_list_control_response(
                page_service=page_service,
                flash_message="已暫停監視",
            )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已暫停%20監視",
            status_code=303,
        )

    @router.post("/watches/{watch_item_id}/resume", response_class=HTMLResponse)
    async def resume_watch(watch_item_id: str, request: Request) -> Response:
        """恢復指定 watch item。"""
        request_helpers.ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_lifecycle_coordinator.resume_watch,
            watch_item_id,
        )
        if _is_watch_list_fragment_request(request):
            return _watch_list_control_response(
                page_service=page_service,
                flash_message="已恢復監視",
            )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已恢復%20監視",
            status_code=303,
        )

    @router.post("/watches/{watch_item_id}/check-now", response_class=HTMLResponse)
    async def check_watch_now(watch_item_id: str, request: Request) -> Response:
        """立即執行單一 watch item 的檢查。"""
        request_helpers.ensure_local_request_origin(request)
        try:
            await container.watch_lifecycle_coordinator.request_check_now(watch_item_id)
        except WatchLifecycleError as exc:
            return HTMLResponse(str(exc), status_code=409)
        return RedirectResponse(
            url=f"/watches/{watch_item_id}?message=已觸發%20立即檢查",
            status_code=303,
        )

    return router


def _is_watch_list_fragment_request(request: Request) -> bool:
    """判斷本次 control action 是否由首頁列表 quick action 以 fetch 送出。"""
    return request.headers.get("x-requested-with") == "fetch"


def _watch_list_control_response(
    *,
    page_service: WatchPageService,
    flash_message: str,
) -> JSONResponse:
    """回傳首頁 control action 完成後需要原地替換的 HTML fragments。"""
    return JSONResponse(
        build_watch_list_fragment_payload(
            context=page_service.build_watch_list_context(),
            version=page_service.build_watch_list_revision(),
            flash_message=flash_message,
        ).to_dict()
    )
