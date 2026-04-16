"""watch lifecycle 控制面的 application service。"""

from __future__ import annotations

from app.application.watch_editor import WatchEditorService
from app.domain.watch_runtime_state import derive_watch_runtime_state
from app.infrastructure.db.repositories import SqliteRuntimeRepository, SqliteWatchItemRepository
from app.monitor.runtime import ChromeDrivenMonitorRuntime


class WatchLifecycleError(RuntimeError):
    """表示 watch lifecycle 命令目前不可執行。"""


class WatchLifecycleCoordinator:
    """統一協調 watch 手動控制命令與 runtime 執行入口。"""

    def __init__(
        self,
        *,
        watch_editor_service: WatchEditorService,
        watch_item_repository: SqliteWatchItemRepository,
        runtime_repository: SqliteRuntimeRepository,
        monitor_runtime: ChromeDrivenMonitorRuntime | None,
    ) -> None:
        self._watch_editor_service = watch_editor_service
        self._watch_item_repository = watch_item_repository
        self._runtime_repository = runtime_repository
        self._monitor_runtime = monitor_runtime

    def enable_watch(self, watch_item_id: str):
        """啟用 watch，並由同一入口記錄 lifecycle 事件。"""
        return self._watch_editor_service.enable_watch_item(watch_item_id)

    def disable_watch(self, watch_item_id: str):
        """停用 watch，阻止後續排程與手動立即檢查。"""
        return self._watch_editor_service.disable_watch_item(watch_item_id)

    def pause_watch(self, watch_item_id: str):
        """暫停 watch，阻止後續排程與手動立即檢查。"""
        return self._watch_editor_service.pause_watch_item(watch_item_id)

    def resume_watch(self, watch_item_id: str):
        """恢復 watch，使其重新進入 runtime 可檢查狀態。"""
        return self._watch_editor_service.resume_watch_item(watch_item_id)

    async def request_check_now(self, watch_item_id: str) -> None:
        """檢查 watch 是否可執行後，才轉交 runtime 立即檢查。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise WatchLifecycleError("watch item not found")
        latest_snapshot = self._runtime_repository.get_latest_check_snapshot(watch_item_id)
        current_state = derive_watch_runtime_state(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
        )
        if not watch_item.enabled or watch_item.paused_reason is not None:
            raise WatchLifecycleError(f"watch is not checkable in state {current_state.value}")
        if self._monitor_runtime is None:
            raise WatchLifecycleError("background monitor runtime is not available")
        await self._monitor_runtime.request_check_now(watch_item_id)
