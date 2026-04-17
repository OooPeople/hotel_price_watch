"""watch 列表、詳細頁與控制操作相關的本機 GUI routes。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.application.watch_lifecycle import WatchLifecycleError
from app.bootstrap.container import AppContainer
from app.domain.entities import LatestCheckSnapshot, WatchItem
from app.monitor.runtime import MonitorRuntimeStatus
from app.web import request_helpers
from app.web.views import (
    render_runtime_status_fragment,
    render_watch_detail_page,
    render_watch_detail_sections,
    render_watch_list_page,
    render_watch_list_rows_fragment,
)


def build_watch_router(container: AppContainer) -> APIRouter:
    """建立 watch list / detail / control routes。"""
    router = APIRouter(tags=["web"])

    @router.get("/", response_class=HTMLResponse)
    def watch_list(request: Request) -> HTMLResponse:
        """顯示 watch item 列表頁。"""
        flash_message = request.query_params.get("message")
        html = render_watch_list_page(
            watch_items=container.watch_item_repository.list_all(),
            latest_snapshots_by_watch_id=_latest_snapshots_by_watch_id(container),
            flash_message=flash_message,
            runtime_status=_get_runtime_status(container),
        )
        return HTMLResponse(html)

    @router.get("/fragments/watch-list")
    def watch_list_fragments() -> dict[str, str]:
        """回傳首頁局部更新所需的 runtime 與 watch 列表片段。"""
        return _build_watch_list_fragments(container)

    @router.get("/watches/{watch_item_id}", response_class=HTMLResponse)
    def watch_detail_page(watch_item_id: str, request: Request) -> HTMLResponse:
        """顯示單一 watch item 的歷史與錯誤摘要。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            return HTMLResponse("watch item not found", status_code=404)
        html = render_watch_detail_page(
            watch_item=watch_item,
            latest_snapshot=container.runtime_repository.get_latest_check_snapshot(watch_item_id),
            check_events=tuple(container.runtime_repository.list_check_events(watch_item_id)),
            notification_state=container.runtime_repository.get_notification_state(watch_item_id),
            debug_artifacts=tuple(container.runtime_repository.list_debug_artifacts(watch_item_id)),
            runtime_state_events=tuple(
                container.runtime_repository.list_runtime_state_events(watch_item_id)
            ),
            flash_message=request.query_params.get("message"),
        )
        return HTMLResponse(html)

    @router.get("/watches/{watch_item_id}/fragments")
    def watch_detail_fragments(watch_item_id: str) -> dict[str, str]:
        """回傳 watch 詳細頁局部更新所需的摘要、歷史與 debug 片段。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise HTTPException(status_code=404, detail="watch item not found")
        return _build_watch_detail_fragments(container=container, watch_item=watch_item)

    @router.post("/watches/{watch_item_id}/delete", response_class=HTMLResponse)
    async def delete_watch(watch_item_id: str, request: Request) -> Response:
        """刪除指定 watch item，並回到列表頁。"""
        request_helpers.ensure_local_request_origin(request)
        await run_in_threadpool(
            container.watch_editor_service.delete_watch_item,
            watch_item_id,
        )
        return RedirectResponse(
            url="/?message=已刪除%20watch%20item",
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
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已啟用%20watch",
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
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已停用%20watch",
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
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已暫停%20watch",
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
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已恢復%20watch",
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


def _get_runtime_status(container: AppContainer) -> MonitorRuntimeStatus | None:
    """讀取目前 background monitor runtime 的狀態摘要。"""
    if container.monitor_runtime is None:
        return None
    return container.monitor_runtime.get_status()


def _latest_snapshots_by_watch_id(
    container: AppContainer,
) -> dict[str, LatestCheckSnapshot | None]:
    """建立首頁與局部更新使用的最新摘要索引。"""
    watch_items = tuple(container.watch_item_repository.list_all())
    return {
        watch_item.id: container.runtime_repository.get_latest_check_snapshot(watch_item.id)
        for watch_item in watch_items
    }


def _build_watch_list_fragments(container: AppContainer) -> dict[str, str]:
    """建立首頁局部更新所需的 runtime 與 watch 列表 HTML 片段。"""
    return {
        "runtime_html": render_runtime_status_fragment(_get_runtime_status(container)),
        "table_body_html": render_watch_list_rows_fragment(
            container.watch_item_repository.list_all(),
            latest_snapshots_by_watch_id=_latest_snapshots_by_watch_id(container),
        ),
    }


def _build_watch_detail_fragments(
    *,
    container: AppContainer,
    watch_item: WatchItem,
) -> dict[str, str]:
    """建立 watch 詳細頁局部更新所需的主要 HTML 片段。"""
    return render_watch_detail_sections(
        watch_item=watch_item,
        latest_snapshot=container.runtime_repository.get_latest_check_snapshot(watch_item.id),
        check_events=tuple(container.runtime_repository.list_check_events(watch_item.id)),
        notification_state=container.runtime_repository.get_notification_state(watch_item.id),
        debug_artifacts=tuple(container.runtime_repository.list_debug_artifacts(watch_item.id)),
        runtime_state_events=tuple(
            container.runtime_repository.list_runtime_state_events(watch_item.id)
        ),
    )
