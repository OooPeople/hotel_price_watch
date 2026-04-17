"""通知設定相關的本機 GUI routes。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.bootstrap.container import AppContainer
from app.domain.enums import NotificationLeafKind
from app.web import request_helpers
from app.web.views import (
    render_notification_channel_settings_page,
    render_notification_settings_page,
)


def build_settings_router(container: AppContainer) -> APIRouter:
    """建立全域與單一 watch 通知設定使用的 router。"""
    router = APIRouter(tags=["web"])

    @router.get("/settings/notifications", response_class=HTMLResponse)
    def notification_channel_settings_page(request: Request) -> HTMLResponse:
        """顯示全域通知通道設定頁。"""
        html = render_notification_channel_settings_page(
            settings=container.app_settings_service.get_notification_channel_settings(),
            test_result_message=request.query_params.get("test_message"),
            flash_message=request.query_params.get("message"),
        )
        return HTMLResponse(html)

    @router.get(
        "/watches/{watch_item_id}/notification-settings",
        response_class=HTMLResponse,
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

    @router.post(
        "/watches/{watch_item_id}/notification-settings",
        response_class=HTMLResponse,
    )
    async def update_notification_settings(
        watch_item_id: str,
        request: Request,
    ) -> Response:
        """更新單一 watch item 的通知條件設定。"""
        request_helpers.ensure_local_request_origin(request)
        form = await request_helpers.read_form_data(request)
        watch_item = container.watch_item_repository.get(watch_item_id)
        if watch_item is None:
            return HTMLResponse("watch item not found", status_code=404)
        try:
            notification_rule_kind = NotificationLeafKind(
                form.get("notification_rule_kind", NotificationLeafKind.ANY_DROP.value)
            )
            target_price = (
                request_helpers.parse_optional_decimal(form.get("target_price", ""))
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
                    error_message=request_helpers.to_user_facing_error_message(exc),
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

    @router.post("/settings/notifications", response_class=HTMLResponse)
    async def update_notification_channel_settings(request: Request) -> Response:
        """更新全域通知通道設定。"""
        request_helpers.ensure_local_request_origin(request)
        form = await request_helpers.read_form_data(request)
        try:
            await run_in_threadpool(
                container.app_settings_service.update_notification_channel_settings,
                desktop_enabled=request_helpers.parse_checkbox(form.get("desktop_enabled")),
                ntfy_enabled=request_helpers.parse_checkbox(form.get("ntfy_enabled")),
                ntfy_server_url=form.get("ntfy_server_url", "https://ntfy.sh"),
                ntfy_topic=form.get("ntfy_topic"),
                discord_enabled=request_helpers.parse_checkbox(form.get("discord_enabled")),
                discord_webhook_url=form.get("discord_webhook_url"),
            )
        except Exception as exc:
            return HTMLResponse(
                render_notification_channel_settings_page(
                    settings=container.app_settings_service.get_notification_channel_settings(),
                    error_message=request_helpers.to_user_facing_error_message(exc),
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

    @router.post("/settings/notifications/test", response_class=HTMLResponse)
    async def send_test_notification(request: Request) -> Response:
        """用目前已保存的全域設定送出測試通知。"""
        request_helpers.ensure_local_request_origin(request)
        try:
            dispatch_result = await run_in_threadpool(
                container.notification_channel_test_service.send_test_notification,
            )
        except Exception as exc:
            return HTMLResponse(
                render_notification_channel_settings_page(
                    settings=container.app_settings_service.get_notification_channel_settings(),
                    error_message=request_helpers.to_user_facing_error_message(exc),
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

    return router
