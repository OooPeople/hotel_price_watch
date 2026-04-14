"""FastAPI app entrypoint for the local management UI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.application.debug_captures import (
    clear_debug_captures,
    list_debug_captures,
    load_debug_capture,
    load_latest_debug_capture,
)
from app.application.preview_guard import PreviewCooldownError
from app.application.watch_editor import WatchCreationPreview
from app.bootstrap.container import AppContainer, build_app_container
from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind
from app.domain.value_objects import SearchDraft
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.views import (
    render_chrome_tab_selection_page,
    render_debug_capture_detail_page,
    render_debug_capture_list_page,
    render_new_watch_page,
    render_notification_channel_settings_page,
    render_notification_settings_page,
    render_runtime_status_fragment,
    render_watch_detail_page,
    render_watch_detail_sections,
    render_watch_list_page,
    render_watch_list_rows_fragment,
)


def create_app(container: AppContainer | None = None) -> FastAPI:
    """Create the local web app and wire the current GUI dependencies."""
    container = container or build_app_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """在 app 啟停時接上目前已實作的 background monitor runtime。"""
        if container.monitor_runtime is not None:
            await container.monitor_runtime.start()
        try:
            yield
        finally:
            if container.monitor_runtime is not None:
                await container.monitor_runtime.stop()

    app = FastAPI(title="hotel_price_watch", version="0.1.0", lifespan=lifespan)
    app.state.container = container

    @app.get("/health", tags=["system"])
    def health() -> dict[str, object]:
        runtime_status = _get_runtime_status(container)
        overall_status = (
            "ok"
            if runtime_status is None
            or (runtime_status.is_running and runtime_status.chrome_debuggable)
            else "degraded"
        )
        return {
            "status": overall_status,
            "instance_id": container.instance_id,
            "runtime": _serialize_runtime_status(runtime_status),
        }

    @app.get("/", response_class=HTMLResponse, tags=["web"])
    def watch_list(request: Request) -> HTMLResponse:
        """顯示 watch item 列表頁。"""
        flash_message = request.query_params.get("message")
        html = render_watch_list_page(
            watch_items=container.watch_item_repository.list_all(),
            flash_message=flash_message,
            runtime_status=_get_runtime_status(container),
        )
        return HTMLResponse(html)

    @app.get("/fragments/watch-list", tags=["web"])
    def watch_list_fragments() -> dict[str, str]:
        """回傳首頁局部更新所需的 runtime 與 watch 列表片段。"""
        return _build_watch_list_fragments(container)

    @app.get("/settings/notifications", response_class=HTMLResponse, tags=["web"])
    def notification_channel_settings_page(request: Request) -> HTMLResponse:
        """顯示全域通知通道設定頁。"""
        html = render_notification_channel_settings_page(
            settings=container.app_settings_service.get_notification_channel_settings(),
            test_result_message=request.query_params.get("test_message"),
            flash_message=request.query_params.get("message"),
        )
        return HTMLResponse(html)

    @app.get("/watches/new", response_class=HTMLResponse, tags=["web"])
    def new_watch_page(seed_url: str = "", error: str | None = None) -> HTMLResponse:
        """顯示新增 watch item 的第一段 editor。"""
        return HTMLResponse(
            render_new_watch_page(
                seed_url=seed_url,
                error_message=error,
            )
        )

    @app.get("/watches/chrome-tabs", response_class=HTMLResponse, tags=["web"])
    async def chrome_tab_list_page() -> HTMLResponse:
        """顯示目前可用的專用 Chrome `ikyu` 分頁清單。"""
        try:
            tabs = await run_in_threadpool(
                container.chrome_tab_preview_service.list_tabs,
            )
        except Exception as exc:
            return HTMLResponse(
                render_chrome_tab_selection_page(
                    tabs=(),
                    error_message=_to_user_facing_error_message(exc),
                    diagnostics=getattr(exc, "diagnostics", ()),
                ),
                status_code=400,
            )
        return HTMLResponse(
            render_chrome_tab_selection_page(
                tabs=tabs,
                existing_watch_ids_by_tab_id=_existing_watch_ids_by_tab_id(
                    container,
                    chrome_tabs=tabs,
                ),
            )
        )

    @app.get("/watches/{watch_item_id}", response_class=HTMLResponse, tags=["web"])
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
            flash_message=request.query_params.get("message"),
        )
        return HTMLResponse(html)

    @app.get("/watches/{watch_item_id}/fragments", tags=["web"])
    def watch_detail_fragments(watch_item_id: str) -> dict[str, str]:
        """回傳 watch 詳細頁局部更新所需的摘要、歷史與 debug 片段。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise HTTPException(status_code=404, detail="watch item not found")
        return _build_watch_detail_fragments(container=container, watch_item=watch_item)

    @app.get("/debug/captures", response_class=HTMLResponse, tags=["web"])
    def debug_capture_list_page(request: Request) -> HTMLResponse:
        """顯示目前已保存的 preview debug captures。"""
        captures = list_debug_captures()
        return HTMLResponse(
            render_debug_capture_list_page(
                captures=captures,
                flash_message=request.query_params.get("message"),
            )
        )

    @app.get("/debug/captures/latest", response_class=HTMLResponse, tags=["web"])
    def debug_capture_latest_page() -> HTMLResponse:
        """顯示最新一筆 preview debug capture。"""
        capture = load_latest_debug_capture()
        if capture is None:
            return HTMLResponse(
                render_debug_capture_list_page(captures=()),
                status_code=404,
            )
        return HTMLResponse(render_debug_capture_detail_page(capture=capture))

    @app.get("/debug/captures/{capture_id}", response_class=HTMLResponse, tags=["web"])
    def debug_capture_detail_page(capture_id: str) -> HTMLResponse:
        """顯示指定 preview debug capture 的詳細內容。"""
        capture = load_debug_capture(capture_id)
        if capture is None:
            return HTMLResponse(
                render_debug_capture_list_page(captures=list_debug_captures()),
                status_code=404,
            )
        return HTMLResponse(render_debug_capture_detail_page(capture=capture))

    @app.get(
        "/debug/captures/{capture_id}/html",
        response_class=PlainTextResponse,
        tags=["web"],
    )
    def debug_capture_html_page(capture_id: str) -> PlainTextResponse:
        """輸出指定 preview debug capture 的完整 HTML 原文。"""
        capture = load_debug_capture(capture_id)
        if capture is None:
            return PlainTextResponse("capture not found", status_code=404)
        return PlainTextResponse(capture.html_content)

    @app.post("/debug/captures/clear", response_class=HTMLResponse, tags=["web"])
    async def clear_debug_capture_list(request: Request) -> Response:
        """清空目前保存的所有 preview debug captures。"""
        _ensure_local_request_origin(request)
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

    @app.post("/watches/preview", response_class=HTMLResponse, tags=["web"])
    async def preview_watch_page(request: Request) -> HTMLResponse:
        """依 seed URL 解析草稿並顯示候選方案。"""
        _ensure_local_request_origin(request)
        form = await _read_form_data(request)
        seed_url = form.get("seed_url", "")
        try:
            container.preview_attempt_guard.ensure_allowed()
        except PreviewCooldownError as exc:
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=str(exc),
                    diagnostics=exc.diagnostics,
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
            container.preview_attempt_guard.register_result(diagnostics=diagnostics)
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=_to_user_facing_error_message(exc),
                    diagnostics=diagnostics,
                ),
                status_code=400,
            )
        preview = container.watch_editor_service.mark_existing_watch_for_preview(preview)
        container.preview_attempt_guard.register_result(diagnostics=preview.diagnostics)
        return HTMLResponse(render_new_watch_page(seed_url=seed_url, preview=preview))

    @app.post("/watches/chrome-tabs/preview", response_class=HTMLResponse, tags=["web"])
    async def preview_watch_from_chrome_tab(request: Request) -> HTMLResponse:
        """從使用者指定的專用 Chrome 分頁直接建立 preview。"""
        _ensure_local_request_origin(request)
        form = await _read_form_data(request)
        selected_tab_id = form.get("tab_id", "").strip()
        tabs = await _safe_list_chrome_tabs(container=container)
        if not selected_tab_id:
            return HTMLResponse(
                render_chrome_tab_selection_page(
                    tabs=tabs,
                    error_message="請先選擇要抓取的 Chrome 分頁。",
                    selected_tab_id=selected_tab_id or None,
                    existing_watch_ids_by_tab_id=_existing_watch_ids_by_tab_id(
                        container,
                        chrome_tabs=tabs,
                    ),
                ),
                status_code=400,
            )
        try:
            container.preview_attempt_guard.ensure_allowed()
        except PreviewCooldownError as exc:
            return HTMLResponse(
                render_chrome_tab_selection_page(
                    tabs=tabs,
                    error_message=str(exc),
                    diagnostics=exc.diagnostics,
                    selected_tab_id=selected_tab_id,
                    existing_watch_ids_by_tab_id=_existing_watch_ids_by_tab_id(
                        container,
                        chrome_tabs=tabs,
                    ),
                ),
                status_code=429,
            )
        try:
            preview = await run_in_threadpool(
                container.chrome_tab_preview_service.preview_from_tab_id,
                selected_tab_id,
            )
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            container.preview_attempt_guard.register_result(diagnostics=diagnostics)
            return HTMLResponse(
                render_chrome_tab_selection_page(
                    tabs=tabs,
                    error_message=_to_user_facing_error_message(exc),
                    diagnostics=diagnostics,
                    selected_tab_id=selected_tab_id,
                    existing_watch_ids_by_tab_id=_existing_watch_ids_by_tab_id(
                        container,
                        chrome_tabs=tabs,
                    ),
                ),
                status_code=400,
            )
        preview = container.watch_editor_service.mark_existing_watch_for_preview(preview)
        container.preview_attempt_guard.register_result(diagnostics=preview.diagnostics)
        return HTMLResponse(
            render_new_watch_page(
                seed_url=preview.draft.seed_url,
                preview=preview,
            )
        )

    @app.post("/watches", response_class=HTMLResponse, tags=["web"])
    async def create_watch(request: Request) -> Response:
        """建立新的 watch item，成功後導回列表頁。"""
        _ensure_local_request_origin(request)
        form = await _read_form_data(request)
        seed_url = form.get("seed_url", "")
        browser_tab_id = form.get("browser_tab_id", "").strip() or None
        preview = None
        try:
            room_id, plan_id = _parse_candidate_key(form.get("candidate_key", ""))
            target_price = _parse_optional_decimal(form.get("target_price", ""))
            preview = await _resolve_watch_creation_preview(
                container=container,
                seed_url=seed_url,
                browser_tab_id=browser_tab_id,
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
                        NotificationLeafKind.BELOW_TARGET_PRICE.value,
                    )
                ),
                target_price=target_price,
            )
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            return HTMLResponse(
                render_new_watch_page(
                    seed_url=seed_url,
                    error_message=_to_user_facing_error_message(exc),
                    diagnostics=diagnostics,
                    preview=preview
                    or await _safe_preview(container=container, seed_url=seed_url),
                ),
                status_code=400,
            )

        return RedirectResponse(
            url=f"/?message=已建立%20{watch_item.hotel_name}%20的監看項",
            status_code=303,
        )

    @app.get(
        "/watches/{watch_item_id}/notification-settings",
        response_class=HTMLResponse,
        tags=["web"],
    )
    def notification_settings_page(
        watch_item_id: str,
        request: Request,
    ) -> HTMLResponse:
        """顯示單一 watch item 的通知設定頁。"""
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            return HTMLResponse("watch item not found", status_code=404)
        return HTMLResponse(
            render_notification_settings_page(
                watch_item=watch_item,
                flash_message=request.query_params.get("message"),
            )
        )

    @app.post(
        "/watches/{watch_item_id}/notification-settings",
        response_class=HTMLResponse,
        tags=["web"],
    )
    async def update_notification_settings(
        watch_item_id: str,
        request: Request,
    ) -> Response:
        """更新單一 watch item 的通知條件設定。"""
        _ensure_local_request_origin(request)
        form = await _read_form_data(request)
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            return HTMLResponse("watch item not found", status_code=404)
        try:
            notification_rule_kind = NotificationLeafKind(
                form.get("notification_rule_kind", NotificationLeafKind.ANY_DROP.value)
            )
            target_price = (
                _parse_optional_decimal(form.get("target_price", ""))
                if notification_rule_kind is NotificationLeafKind.BELOW_TARGET_PRICE
                else None
            )
            updated_watch_item = await run_in_threadpool(
                container.watch_editor_service.update_notification_rule,
                watch_item_id=watch_item_id,
                notification_rule_kind=notification_rule_kind,
                target_price=target_price,
            )
        except Exception as exc:
            return HTMLResponse(
                render_notification_settings_page(
                    watch_item=watch_item,
                    error_message=_to_user_facing_error_message(exc),
                    form_values={
                        "notification_rule_kind": form.get(
                            "notification_rule_kind",
                            NotificationLeafKind.ANY_DROP.value,
                        ),
                        "target_price": form.get("target_price", ""),
                    },
                ),
                status_code=400,
            )
        return RedirectResponse(
            url=(
                f"/watches/{updated_watch_item.id}/notification-settings"
                "?message=已更新%20通知設定"
            ),
            status_code=303,
        )

    @app.post("/settings/notifications", response_class=HTMLResponse, tags=["web"])
    async def update_notification_channel_settings(request: Request) -> Response:
        """更新全域通知通道設定。"""
        _ensure_local_request_origin(request)
        form = await _read_form_data(request)
        try:
            await run_in_threadpool(
                container.app_settings_service.update_notification_channel_settings,
                desktop_enabled=_parse_checkbox(form.get("desktop_enabled")),
                ntfy_enabled=_parse_checkbox(form.get("ntfy_enabled")),
                ntfy_server_url=form.get("ntfy_server_url", "https://ntfy.sh"),
                ntfy_topic=form.get("ntfy_topic"),
                discord_enabled=_parse_checkbox(form.get("discord_enabled")),
                discord_webhook_url=form.get("discord_webhook_url"),
            )
        except Exception as exc:
            return HTMLResponse(
                render_notification_channel_settings_page(
                    settings=container.app_settings_service.get_notification_channel_settings(),
                    error_message=_to_user_facing_error_message(exc),
                    form_values={
                        "desktop_enabled": form.get("desktop_enabled", ""),
                        "ntfy_enabled": form.get("ntfy_enabled", ""),
                        "ntfy_server_url": form.get("ntfy_server_url", "https://ntfy.sh"),
                        "ntfy_topic": form.get("ntfy_topic", ""),
                        "discord_enabled": form.get("discord_enabled", ""),
                        "discord_webhook_url": form.get("discord_webhook_url", ""),
                    },
                ),
                status_code=400,
            )
        return RedirectResponse(
            url=(
                "/settings/notifications?"
                "message=已更新%20通知通道設定"
            ),
            status_code=303,
        )

    @app.post("/settings/notifications/test", response_class=HTMLResponse, tags=["web"])
    async def send_test_notification(request: Request) -> Response:
        """用目前已保存的全域設定送出測試通知。"""
        _ensure_local_request_origin(request)
        try:
            dispatch_result = await run_in_threadpool(
                container.notification_channel_test_service.send_test_notification,
            )
        except Exception as exc:
            return HTMLResponse(
                render_notification_channel_settings_page(
                    settings=container.app_settings_service.get_notification_channel_settings(),
                    error_message=_to_user_facing_error_message(exc),
                ),
                status_code=400,
            )

        sent_channels = ", ".join(dispatch_result.sent_channels) or "none"
        throttled_channels = ", ".join(dispatch_result.throttled_channels) or "none"
        failed_channels = ", ".join(dispatch_result.failed_channels) or "none"
        failure_details = (
            " | ".join(
                f"{channel}: {detail}"
                for channel, detail in (dispatch_result.failure_details or {}).items()
            )
            or "none"
        )
        return RedirectResponse(
            url=(
                "/settings/notifications?"
                f"test_message=測試通知結果：sent={sent_channels}；"
                f"throttled={throttled_channels}；failed={failed_channels}；"
                f"details={failure_details}"
            ),
            status_code=303,
        )

    @app.post("/watches/{watch_item_id}/delete", response_class=HTMLResponse, tags=["web"])
    async def delete_watch(watch_item_id: str, request: Request) -> Response:
        """刪除指定 watch item，並回到列表頁。"""
        _ensure_local_request_origin(request)
        await run_in_threadpool(
            container.watch_editor_service.delete_watch_item,
            watch_item_id,
        )
        return RedirectResponse(
            url="/?message=已刪除%20watch%20item",
            status_code=303,
        )

    @app.post("/watches/{watch_item_id}/enable", response_class=HTMLResponse, tags=["web"])
    async def enable_watch(watch_item_id: str, request: Request) -> Response:
        """啟用指定 watch item。"""
        _ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_editor_service.enable_watch_item,
            watch_item_id,
        )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已啟用%20watch",
            status_code=303,
        )

    @app.post("/watches/{watch_item_id}/disable", response_class=HTMLResponse, tags=["web"])
    async def disable_watch(watch_item_id: str, request: Request) -> Response:
        """停用指定 watch item。"""
        _ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_editor_service.disable_watch_item,
            watch_item_id,
        )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已停用%20watch",
            status_code=303,
        )

    @app.post("/watches/{watch_item_id}/pause", response_class=HTMLResponse, tags=["web"])
    async def pause_watch(watch_item_id: str, request: Request) -> Response:
        """暫停指定 watch item。"""
        _ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_editor_service.pause_watch_item,
            watch_item_id,
        )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已暫停%20watch",
            status_code=303,
        )

    @app.post("/watches/{watch_item_id}/resume", response_class=HTMLResponse, tags=["web"])
    async def resume_watch(watch_item_id: str, request: Request) -> Response:
        """恢復指定 watch item。"""
        _ensure_local_request_origin(request)
        watch_item = await run_in_threadpool(
            container.watch_editor_service.resume_watch_item,
            watch_item_id,
        )
        return RedirectResponse(
            url=f"/watches/{watch_item.id}?message=已恢復%20watch",
            status_code=303,
        )

    @app.post("/watches/{watch_item_id}/check-now", response_class=HTMLResponse, tags=["web"])
    async def check_watch_now(watch_item_id: str, request: Request) -> Response:
        """立即執行單一 watch item 的檢查。"""
        _ensure_local_request_origin(request)
        runtime = container.monitor_runtime
        if runtime is None:
            return HTMLResponse("background monitor runtime is not available", status_code=503)
        await runtime.request_check_now(watch_item_id)
        return RedirectResponse(
            url=f"/watches/{watch_item_id}?message=已觸發%20立即檢查",
            status_code=303,
        )

    return app


async def _read_form_data(request: Request) -> dict[str, str]:
    """手動解析表單內容，避免額外依賴 multipart 套件。"""
    body = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _ensure_local_request_origin(request: Request) -> None:
    """驗證 state-changing POST 是否來自允許的本機管理介面來源。"""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if not origin and not referer:
        raise HTTPException(status_code=403, detail="missing request origin")

    expected_scheme = request.url.scheme
    expected_port = request.url.port or (443 if expected_scheme == "https" else 80)
    local_hosts = {"127.0.0.1", "localhost"}

    if origin is not None and _is_allowed_local_url(
        origin,
        expected_scheme=expected_scheme,
        expected_port=expected_port,
        local_hosts=local_hosts,
    ):
        return

    if referer is not None and _is_allowed_local_url(
        referer,
        expected_scheme=expected_scheme,
        expected_port=expected_port,
        local_hosts=local_hosts,
    ):
        return

    raise HTTPException(status_code=403, detail="invalid request origin")


def _is_allowed_local_url(
    raw_url: str,
    *,
    expected_scheme: str,
    expected_port: int,
    local_hosts: set[str],
) -> bool:
    """判斷來源 URL 是否屬於允許的本機管理介面位址。"""
    parsed = urlparse(raw_url)
    hostname = parsed.hostname
    if hostname not in local_hosts:
        return False
    if parsed.scheme != expected_scheme:
        return False
    actual_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return actual_port == expected_port


def _parse_candidate_key(raw_value: str) -> tuple[str, str]:
    """把 radio button 的候選 key 還原成 room_id / plan_id。"""
    room_id, separator, plan_id = raw_value.partition("::")
    if not separator or not room_id or not plan_id:
        raise ValueError("請先選擇有效的房型方案")
    return room_id, plan_id


def _parse_optional_decimal(raw_value: str) -> Decimal | None:
    """把表單中的目標價字串轉成可選的 Decimal。"""
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("目標價格式不正確") from exc


def _parse_checkbox(raw_value: str | None) -> bool:
    """把 HTML checkbox 欄位轉成布林值。"""
    return raw_value == "on"


def _to_user_facing_error_message(exc: Exception) -> str:
    """把內部錯誤訊息轉成較適合 GUI 顯示的說法。"""
    raw_message = str(exc)
    if raw_message == "search draft is incomplete for candidate lookup":
        return (
            "目前網址尚未帶齊查候選所需條件；"
            "請改用已帶日期與人數的精確 URL，"
            "或改由專用 Chrome 分頁抓取。"
        )
    return raw_message


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


def _existing_watch_ids_by_tab_id(
    container: AppContainer,
    *,
    chrome_tabs: tuple | None = None,
) -> dict[str, str]:
    """依既有 watch target 與已保存頁面資訊，標記哪些分頁已對應 watch。"""
    linked: dict[str, str] = {}
    chrome_tabs = chrome_tabs or container.chrome_tab_preview_service.list_tabs()
    watch_items = tuple(container.watch_item_repository.list_all())
    drafts_by_watch_id = {
        watch_item.id: container.watch_item_repository.get_draft(watch_item.id)
        for watch_item in watch_items
    }

    for tab in chrome_tabs:
        matched_watch = _find_existing_watch_for_tab(
            tab_url=tab.url,
            watch_items=watch_items,
            drafts_by_watch_id=drafts_by_watch_id,
        )
        if matched_watch is not None:
            linked[tab.tab_id] = matched_watch.id
    return linked


def _find_existing_watch_for_tab(
    *,
    tab_url: str,
    watch_items: tuple[WatchItem, ...],
    drafts_by_watch_id: dict[str, SearchDraft | None],
) -> WatchItem | None:
    """依頁面 URL 與 watch target identity 判斷某個分頁是否已對應既有 watch。"""
    tab_signature = _extract_watch_match_signature(tab_url)
    for watch_item in watch_items:
        draft = drafts_by_watch_id.get(watch_item.id)
        if draft is not None and draft.browser_page_url is not None and (
            draft.browser_page_url == tab_url
            or _signatures_match_confidently(
                left=_extract_watch_match_signature(draft.browser_page_url),
                right=tab_signature,
            )
        ):
            return watch_item
        if _signatures_match_confidently(
            left=_extract_watch_match_signature(watch_item.canonical_url),
            right=tab_signature,
        ):
            return watch_item
        if _watch_target_matches_signature(watch_item=watch_item, signature=tab_signature):
            return watch_item
    return None


def _watch_target_matches_signature(
    *,
    watch_item: WatchItem,
    signature: tuple[str | None, ...],
) -> bool:
    """以 target identity 判斷目前分頁 URL 是否已對應到指定 watch。"""
    (
        hotel_id,
        room_id,
        plan_id,
        check_in,
        people_count,
        room_count,
    ) = signature
    expected_check_in = watch_item.target.check_in_date.isoformat().replace("-", "")
    expected_people_count = str(watch_item.target.people_count)
    expected_room_count = str(watch_item.target.room_count)
    return (
        hotel_id == watch_item.target.hotel_id
        and room_id == watch_item.target.room_id
        and plan_id == watch_item.target.plan_id
        and (check_in is None or check_in == expected_check_in)
        and (people_count is None or people_count == expected_people_count)
        and (room_count is None or room_count == expected_room_count)
    )


def _signatures_match_confidently(
    *,
    left: tuple[str | None, str | None, str | None, str | None, str | None, str | None],
    right: tuple[str | None, str | None, str | None, str | None, str | None, str | None],
) -> bool:
    """僅在精確 target 足夠一致時，才把兩個 URL 視為同一個 watch 目標。"""
    (
        left_hotel_id,
        left_room_id,
        left_plan_id,
        left_check_in,
        left_people_count,
        left_room_count,
    ) = left
    (
        right_hotel_id,
        right_room_id,
        right_plan_id,
        right_check_in,
        right_people_count,
        right_room_count,
    ) = right

    if not all(
        (
            left_hotel_id,
            left_room_id,
            left_plan_id,
            right_hotel_id,
            right_room_id,
            right_plan_id,
        )
    ):
        return False

    return (
        left_hotel_id == right_hotel_id
        and left_room_id == right_room_id
        and left_plan_id == right_plan_id
        and _optional_signature_field_matches(left_check_in, right_check_in)
        and _optional_signature_field_matches(left_people_count, right_people_count)
        and _optional_signature_field_matches(left_room_count, right_room_count)
    )


def _optional_signature_field_matches(left: str | None, right: str | None) -> bool:
    """兩邊都存在時需一致；任一方缺省時，視為可接受的非衝突狀態。"""
    if left is None or right is None:
        return True
    return left == right


def _extract_watch_match_signature(
    url: str,
) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    """從 ikyu URL 萃取 watch target 對應所需的最小比對訊號。"""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    hotel_id = path_segments[-1] if path_segments else None
    if hotel_id is not None and not hotel_id.isdigit():
        hotel_id = None
    return (
        hotel_id,
        _first_query_value(query, "rm"),
        _first_query_value(query, "pln"),
        _first_query_value(query, "cid"),
        _first_query_value(query, "ppc"),
        _first_query_value(query, "rc"),
    )


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    """安全取出 query string 第一個值，避免空值與缺值混淆。"""
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


async def _resolve_watch_creation_preview(
    *,
    container: AppContainer,
    seed_url: str,
    browser_tab_id: str | None,
) -> WatchCreationPreview:
    """依目前主線決定建立 watch 時應重建哪一份 preview。"""
    if browser_tab_id is not None:
        return await run_in_threadpool(
            container.chrome_tab_preview_service.preview_from_tab_id,
            browser_tab_id,
        )
    return await run_in_threadpool(
        container.watch_editor_service.preview_from_seed_url,
        seed_url,
    )


async def _safe_list_chrome_tabs(
    *,
    container: AppContainer,
):
    """嘗試列出 Chrome 分頁；若失敗則回傳空清單，供錯誤頁面沿用。"""
    try:
        return await run_in_threadpool(
            container.chrome_tab_preview_service.list_tabs,
        )
    except Exception:
        return ()


def _get_runtime_status(container: AppContainer) -> MonitorRuntimeStatus | None:
    """讀取目前 background monitor runtime 的狀態摘要。"""
    if container.monitor_runtime is None:
        return None
    return container.monitor_runtime.get_status()


def _build_watch_list_fragments(container: AppContainer) -> dict[str, str]:
    """建立首頁局部更新所需的 runtime 與 watch 列表 HTML 片段。"""
    return {
        "runtime_html": render_runtime_status_fragment(_get_runtime_status(container)),
        "table_body_html": render_watch_list_rows_fragment(
            container.watch_item_repository.list_all()
        ),
    }


def _build_watch_detail_fragments(
    *,
    container: AppContainer,
    watch_item,
) -> dict[str, str]:
    """建立 watch 詳細頁局部更新所需的主要 HTML 片段。"""
    return render_watch_detail_sections(
        watch_item=watch_item,
        latest_snapshot=container.runtime_repository.get_latest_check_snapshot(watch_item.id),
        check_events=tuple(container.runtime_repository.list_check_events(watch_item.id)),
        notification_state=container.runtime_repository.get_notification_state(watch_item.id),
        debug_artifacts=tuple(container.runtime_repository.list_debug_artifacts(watch_item.id)),
    )


def _serialize_runtime_status(
    runtime_status: MonitorRuntimeStatus | None,
) -> dict[str, object] | None:
    """將 runtime 狀態摘要轉成 health endpoint 可直接輸出的資料。"""
    if runtime_status is None:
        return None
    return {
        "is_running": runtime_status.is_running,
        "enabled_watch_count": runtime_status.enabled_watch_count,
        "registered_watch_count": runtime_status.registered_watch_count,
        "inflight_watch_count": runtime_status.inflight_watch_count,
        "chrome_debuggable": runtime_status.chrome_debuggable,
        "last_tick_at": (
            runtime_status.last_tick_at.isoformat()
            if runtime_status.last_tick_at is not None
            else None
        ),
        "last_watch_sync_at": (
            runtime_status.last_watch_sync_at.isoformat()
            if runtime_status.last_watch_sync_at is not None
            else None
        ),
    }


app = create_app()
