"""FastAPI app entrypoint for the local management UI."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.container import AppContainer, build_app_container
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.routes.debug_routes import build_debug_router
from app.web.routes.settings_routes import build_settings_router
from app.web.routes.watch_creation_routes import build_watch_creation_router
from app.web.routes.watch_routes import build_watch_router


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
    app.include_router(build_debug_router())
    app.include_router(build_settings_router(container))
    app.include_router(build_watch_creation_router(container))
    app.include_router(build_watch_router(container))

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

    return app


def _get_runtime_status(container: AppContainer) -> MonitorRuntimeStatus | None:
    """讀取目前 background monitor runtime 的狀態摘要。"""
    if container.monitor_runtime is None:
        return None
    return container.monitor_runtime.get_status()


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
