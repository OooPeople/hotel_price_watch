"""watch 列表、詳細頁與控制操作相關的本機 GUI routes。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.application.watch_lifecycle import WatchLifecycleError
from app.bootstrap.container import AppContainer
from app.config.models import DisplaySettings
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    PriceHistoryEntry,
    RuntimeStateEvent,
    WatchItem,
)
from app.monitor.runtime import MonitorRuntimeStatus
from app.web import request_helpers
from app.web.ui_components import flash_message as render_flash_message
from app.web.views import (
    render_dashboard_summary_fragment,
    render_runtime_status_fragment,
    render_watch_detail_page,
    render_watch_detail_sections,
    render_watch_list_page,
    render_watch_list_rows_fragment,
)
from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_PAYLOAD_KEYS,
    WATCH_LIST_PAYLOAD_KEYS,
    WatchDetailFragmentPayload,
    WatchListFragmentPayload,
)


@dataclass(frozen=True)
class WatchListPageContext:
    """首頁 watch 列表 renderer 所需的資料集合。"""

    watch_items: tuple[WatchItem, ...]
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None]
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]]
    today_notification_count: int
    runtime_status: MonitorRuntimeStatus | None
    display_settings: DisplaySettings


@dataclass(frozen=True)
class WatchDetailPageContext:
    """watch 詳細頁與 fragment renderer 共用的資料集合。"""

    watch_item: WatchItem
    latest_snapshot: LatestCheckSnapshot | None
    check_events: tuple[CheckEvent, ...]
    notification_state: NotificationState | None
    debug_artifacts: tuple[DebugArtifact, ...]
    runtime_state_events: tuple[RuntimeStateEvent, ...]
    display_settings: DisplaySettings


def build_watch_router(container: AppContainer) -> APIRouter:
    """建立 watch list / detail / control routes。"""
    router = APIRouter(tags=["web"])

    @router.get("/", response_class=HTMLResponse)
    def watch_list(request: Request) -> HTMLResponse:
        """顯示 watch item 列表頁。"""
        flash_message = request.query_params.get("message")
        context = _build_watch_list_context(container)
        html = render_watch_list_page(
            watch_items=context.watch_items,
            latest_snapshots_by_watch_id=context.latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=context.recent_price_history_by_watch_id,
            today_notification_count=context.today_notification_count,
            flash_message=flash_message,
            runtime_status=context.runtime_status,
            use_24_hour_time=context.display_settings.use_24_hour_time,
            initial_fragment_version=_build_watch_list_revision(container),
        )
        return HTMLResponse(html)

    @router.get("/fragments/watch-list")
    def watch_list_fragments() -> dict[str, str]:
        """回傳首頁局部更新所需的 runtime 與 watch 列表片段。"""
        return _build_watch_list_fragment_payload(container).to_dict()

    @router.get("/fragments/watch-list/version")
    def watch_list_fragment_version() -> dict[str, str]:
        """回傳首頁局部更新使用的資料版本。"""
        return {WATCH_LIST_PAYLOAD_KEYS.version: _build_watch_list_revision(container)}

    @router.get("/watches/{watch_item_id}", response_class=HTMLResponse)
    def watch_detail_page(watch_item_id: str, request: Request) -> HTMLResponse:
        """顯示單一 watch item 的歷史與錯誤摘要。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            return HTMLResponse("watch item not found", status_code=404)
        context = _build_watch_detail_context(container=container, watch_item=watch_item)
        html = render_watch_detail_page(
            watch_item=context.watch_item,
            latest_snapshot=context.latest_snapshot,
            check_events=context.check_events,
            notification_state=context.notification_state,
            debug_artifacts=context.debug_artifacts,
            runtime_state_events=context.runtime_state_events,
            flash_message=request.query_params.get("message"),
            use_24_hour_time=context.display_settings.use_24_hour_time,
            initial_fragment_version=_build_watch_detail_revision(
                container=container,
                watch_item=watch_item,
            ),
        )
        return HTMLResponse(html)

    @router.get("/watches/{watch_item_id}/fragments")
    def watch_detail_fragments(watch_item_id: str) -> dict[str, str]:
        """回傳 watch 詳細頁局部更新所需的摘要、歷史與 debug 片段。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise HTTPException(status_code=404, detail="watch item not found")
        return _build_watch_detail_fragment_payload(
            container=container,
            watch_item=watch_item,
        ).to_dict()

    @router.get("/watches/{watch_item_id}/fragments/version")
    def watch_detail_fragment_version(watch_item_id: str) -> dict[str, str]:
        """回傳 watch 詳細頁局部更新使用的資料版本。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise HTTPException(status_code=404, detail="watch item not found")
        return {
            WATCH_DETAIL_PAYLOAD_KEYS.version: _build_watch_detail_revision(
                container=container,
                watch_item=watch_item,
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
                container=container,
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
                container=container,
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
                container=container,
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
                container=container,
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
                container=container,
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


def _get_runtime_status(container: AppContainer) -> MonitorRuntimeStatus | None:
    """讀取目前 background monitor runtime 的狀態摘要。"""
    if container.monitor_runtime is None:
        return None
    return container.monitor_runtime.get_status()


def _latest_snapshots_by_watch_id(
    *,
    container: AppContainer,
    watch_items: tuple[WatchItem, ...],
) -> dict[str, LatestCheckSnapshot | None]:
    """建立首頁與局部更新使用的最新摘要索引。"""
    return {
        watch_item.id: container.runtime_repository.get_latest_check_snapshot(watch_item.id)
        for watch_item in watch_items
    }


def _build_watch_list_context(container: AppContainer) -> WatchListPageContext:
    """集中讀取首頁與首頁 fragment 需要的 watch 列表 context。"""
    watch_items = tuple(container.watch_item_repository.list_all())
    now = datetime.now(UTC)
    return WatchListPageContext(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=_latest_snapshots_by_watch_id(
            container=container,
            watch_items=watch_items,
        ),
        recent_price_history_by_watch_id=container.runtime_repository.list_price_history_since(
            watch_item_ids=tuple(watch_item.id for watch_item in watch_items),
            since=now - timedelta(hours=24),
        ),
        today_notification_count=container.runtime_repository.count_notifications_since(
            _local_day_start_as_utc()
        ),
        runtime_status=_get_runtime_status(container),
        display_settings=container.app_settings_service.get_display_settings(),
    )


def _build_watch_list_fragment_payload(
    container: AppContainer,
    *,
    flash_message: str | None = None,
) -> WatchListFragmentPayload:
    """建立首頁局部更新所需的 runtime 與 watch 列表 HTML 片段。"""
    context = _build_watch_list_context(container)
    return WatchListFragmentPayload(
        version=_build_watch_list_revision(container),
        flash_html=render_flash_message(flash_message),
        summary_html=render_dashboard_summary_fragment(
            context.watch_items,
            latest_snapshots_by_watch_id=context.latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=context.recent_price_history_by_watch_id,
            today_notification_count=context.today_notification_count,
            runtime_status=context.runtime_status,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
        runtime_html=render_runtime_status_fragment(
            context.runtime_status,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
        table_body_html=render_watch_list_rows_fragment(
            context.watch_items,
            latest_snapshots_by_watch_id=context.latest_snapshots_by_watch_id,
            recent_price_history_by_watch_id=context.recent_price_history_by_watch_id,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
    )


def _is_watch_list_fragment_request(request: Request) -> bool:
    """判斷本次 control action 是否由首頁列表 quick action 以 fetch 送出。"""
    return request.headers.get("x-requested-with") == "fetch"


def _watch_list_control_response(
    *,
    container: AppContainer,
    flash_message: str,
) -> JSONResponse:
    """回傳首頁 control action 完成後需要原地替換的 HTML fragments。"""
    return JSONResponse(
        _build_watch_list_fragment_payload(
            container,
            flash_message=flash_message,
        ).to_dict()
    )


def _build_watch_list_revision(container: AppContainer) -> str:
    """建立首頁可見資料的版本 hash，供前端判斷是否要抓 fragment。"""
    now = datetime.now(UTC)
    runtime_status = _get_runtime_status(container)
    return _hash_revision_parts(
        (
            container.watch_item_repository.get_collection_revision_token(),
            container.runtime_repository.get_watch_list_revision_token(
                price_history_since=now - timedelta(hours=24),
                notification_since=_local_day_start_as_utc(),
            ),
            container.app_settings_repository.get_display_settings_revision_token(),
            _runtime_status_revision_token(runtime_status),
        )
    )


def _build_watch_detail_revision(
    *,
    container: AppContainer,
    watch_item: WatchItem,
) -> str:
    """建立詳細頁可見資料的版本 hash，供前端判斷是否要抓 fragment。"""
    return _hash_revision_parts(
        (
            container.watch_item_repository.get_revision_token(watch_item.id),
            container.runtime_repository.get_watch_detail_revision_token(watch_item.id),
            container.app_settings_repository.get_display_settings_revision_token(),
        )
    )


def _runtime_status_revision_token(runtime_status: MonitorRuntimeStatus | None) -> str:
    """把 runtime status 中會影響首頁可見內容的欄位轉成版本 token。"""
    if runtime_status is None:
        return "runtime:none"
    parts = (
        str(runtime_status.is_running),
        str(runtime_status.enabled_watch_count),
        str(runtime_status.registered_watch_count),
        str(runtime_status.inflight_watch_count),
        str(runtime_status.chrome_debuggable),
        runtime_status.last_watch_sync_at.isoformat()
        if runtime_status.last_watch_sync_at is not None
        else "",
    )
    return "|".join(parts)


def _hash_revision_parts(parts: tuple[str, ...]) -> str:
    """把多個資料來源版本合成單一前端可比對版本。"""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def _local_day_start_as_utc() -> datetime:
    """回傳使用者本地日期今天 00:00 對應的 UTC 時間。"""
    local_now = datetime.now().astimezone()
    local_start = datetime.combine(
        local_now.date(),
        time.min,
        tzinfo=local_now.tzinfo,
    )
    return local_start.astimezone(UTC)


def _build_watch_detail_context(
    *,
    container: AppContainer,
    watch_item: WatchItem,
) -> WatchDetailPageContext:
    """集中讀取 watch 詳細頁與 fragment 需要的 runtime context。"""
    return WatchDetailPageContext(
        watch_item=watch_item,
        latest_snapshot=container.runtime_repository.get_latest_check_snapshot(watch_item.id),
        check_events=tuple(container.runtime_repository.list_check_events(watch_item.id)),
        notification_state=container.runtime_repository.get_notification_state(watch_item.id),
        debug_artifacts=tuple(container.runtime_repository.list_debug_artifacts(watch_item.id)),
        runtime_state_events=tuple(
            container.runtime_repository.list_runtime_state_events(watch_item.id)
        ),
        display_settings=container.app_settings_service.get_display_settings(),
    )


def _build_watch_detail_fragments(
    *,
    container: AppContainer,
    watch_item: WatchItem,
) -> dict[str, str]:
    """建立 watch 詳細頁局部更新所需的主要 HTML 片段。"""
    return _build_watch_detail_fragment_payload(
        container=container,
        watch_item=watch_item,
    ).sections


def _build_watch_detail_fragment_payload(
    *,
    container: AppContainer,
    watch_item: WatchItem,
) -> WatchDetailFragmentPayload:
    """建立 watch 詳細頁局部更新所需的 HTML 片段與版本。"""
    context = _build_watch_detail_context(container=container, watch_item=watch_item)
    return WatchDetailFragmentPayload(
        version=_build_watch_detail_revision(
            container=container,
            watch_item=watch_item,
        ),
        sections=render_watch_detail_sections(
            watch_item=context.watch_item,
            latest_snapshot=context.latest_snapshot,
            check_events=context.check_events,
            notification_state=context.notification_state,
            debug_artifacts=context.debug_artifacts,
            runtime_state_events=context.runtime_state_events,
            use_24_hour_time=context.display_settings.use_24_hour_time,
        ),
    )
