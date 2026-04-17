"""debug capture 相關的本機 GUI routes。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.application.debug_captures import (
    clear_debug_captures,
    list_debug_captures,
    load_debug_capture,
    load_latest_debug_capture,
)
from app.web import request_helpers
from app.web.views import (
    render_debug_capture_detail_page,
    render_debug_capture_list_page,
)


def build_debug_router() -> APIRouter:
    """建立 debug capture 頁面與操作使用的 router。"""
    router = APIRouter(tags=["web"])

    @router.get("/debug/captures", response_class=HTMLResponse)
    def debug_capture_list_page(request: Request) -> HTMLResponse:
        """顯示目前已保存的 preview debug captures。"""
        captures = list_debug_captures()
        return HTMLResponse(
            render_debug_capture_list_page(
                captures=captures,
                flash_message=request.query_params.get("message"),
            )
        )

    @router.get("/debug/captures/latest", response_class=HTMLResponse)
    def debug_capture_latest_page() -> HTMLResponse:
        """顯示最新一筆 preview debug capture。"""
        capture = load_latest_debug_capture()
        if capture is None:
            return HTMLResponse(
                render_debug_capture_list_page(captures=()),
                status_code=404,
            )
        return HTMLResponse(render_debug_capture_detail_page(capture=capture))

    @router.get("/debug/captures/{capture_id}", response_class=HTMLResponse)
    def debug_capture_detail_page(capture_id: str) -> HTMLResponse:
        """顯示指定 preview debug capture 的詳細內容。"""
        capture = load_debug_capture(capture_id)
        if capture is None:
            return HTMLResponse(
                render_debug_capture_list_page(captures=list_debug_captures()),
                status_code=404,
            )
        return HTMLResponse(render_debug_capture_detail_page(capture=capture))

    @router.get(
        "/debug/captures/{capture_id}/html",
        response_class=PlainTextResponse,
    )
    def debug_capture_html_page(capture_id: str) -> PlainTextResponse:
        """輸出指定 preview debug capture 的完整 HTML 原文。"""
        capture = load_debug_capture(capture_id)
        if capture is None:
            return PlainTextResponse("capture not found", status_code=404)
        return PlainTextResponse(capture.html_content)

    @router.post("/debug/captures/clear", response_class=HTMLResponse)
    async def clear_debug_capture_list(request: Request) -> Response:
        """清空目前保存的所有 preview debug captures。"""
        request_helpers.ensure_local_request_origin(request)
        clear_result = await run_in_threadpool(clear_debug_captures)
        if clear_result.failed_paths:
            failed_count = len(clear_result.failed_paths)
            return RedirectResponse(
                url=(
                    "/debug/captures?"
                    f"message=已刪除%20{clear_result.removed_count}%20個%20debug%20檔案，"
                    f"另有%20{failed_count}%20個刪除失敗"
                ),
                status_code=303,
            )
        return RedirectResponse(
            url=(
                f"/debug/captures?message=已清空%20"
                f"{clear_result.removed_count}%20筆%20debug%20檔案"
            ),
            status_code=303,
        )

    return router
