"""watch lifecycle 控制面的 application service。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.watch_lifecycle_state_machine import (
    LifecycleSchedulerAction,
    WatchLifecycleCommand,
    WatchLifecycleContext,
    WatchLifecycleDecision,
    WatchLifecycleTransitionResult,
    decide_watch_lifecycle,
)
from app.infrastructure.db.repositories import (
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
    SqliteWatchItemRepository,
)
from app.monitor.runtime import ChromeDrivenMonitorRuntime


class WatchLifecycleError(RuntimeError):
    """表示 watch lifecycle 命令目前不可執行。"""


class WatchLifecycleCoordinator:
    """統一協調 watch 手動控制命令與 runtime 執行入口。"""

    def __init__(
        self,
        *,
        watch_item_repository: SqliteWatchItemRepository,
        monitor_runtime: ChromeDrivenMonitorRuntime | None,
        runtime_write_repository: SqliteRuntimeWriteRepository | None = None,
        runtime_history_repository: SqliteRuntimeHistoryQueryRepository | None = None,
    ) -> None:
        self._watch_item_repository = watch_item_repository
        if runtime_write_repository is None or runtime_history_repository is None:
            raise ValueError("runtime write/history repositories are required")
        self._runtime_write_repository = runtime_write_repository
        self._runtime_history_repository = runtime_history_repository
        self._monitor_runtime = monitor_runtime

    def enable_watch(self, watch_item_id: str):
        """啟用 watch，並由 lifecycle owner 記錄正式 transition event。"""
        return self._apply_transition_command(
            watch_item_id=watch_item_id,
            command=WatchLifecycleCommand.MANUAL_ENABLE,
        ).watch_item

    def disable_watch(self, watch_item_id: str):
        """停用 watch，阻止後續排程與手動立即檢查。"""
        return self._apply_transition_command(
            watch_item_id=watch_item_id,
            command=WatchLifecycleCommand.MANUAL_DISABLE,
        ).watch_item

    def pause_watch(self, watch_item_id: str):
        """暫停 watch，阻止後續排程與手動立即檢查。"""
        return self._apply_transition_command(
            watch_item_id=watch_item_id,
            command=WatchLifecycleCommand.MANUAL_PAUSE,
        ).watch_item

    def resume_watch(self, watch_item_id: str):
        """恢復 watch，使其重新進入 runtime 可檢查狀態。"""
        return self._apply_transition_command(
            watch_item_id=watch_item_id,
            command=WatchLifecycleCommand.MANUAL_RESUME,
        ).watch_item

    async def request_check_now(self, watch_item_id: str) -> None:
        """檢查 watch 是否可執行後，才轉交 runtime 立即檢查。"""
        context = self._get_lifecycle_context(watch_item_id)
        decision = decide_watch_lifecycle(
            context=context,
            command=WatchLifecycleCommand.CHECK_NOW,
            occurred_at=datetime.now(UTC),
        )
        if not decision.allowed:
            raise WatchLifecycleError(decision.rejection_reason or "watch is not checkable")
        if self._monitor_runtime is None:
            raise WatchLifecycleError("background monitor runtime is not available")
        await self._monitor_runtime.request_check_now(watch_item_id)

    def _apply_transition_command(
        self,
        *,
        watch_item_id: str,
        command: WatchLifecycleCommand,
    ) -> WatchLifecycleTransitionResult:
        """套用人工 control transition，並由同一權威入口保存事件。"""
        context = self._get_lifecycle_context(watch_item_id)
        decision = decide_watch_lifecycle(
            context=context,
            command=command,
            occurred_at=datetime.now(UTC),
        )
        if not decision.allowed or decision.watch_item is None:
            raise WatchLifecycleError(
                decision.rejection_reason or f"lifecycle command rejected: {command}"
            )
        return self._persist_transition_decision(decision)

    def _get_lifecycle_context(self, watch_item_id: str) -> WatchLifecycleContext:
        """讀取 state machine 判斷 transition 所需的目前狀態。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise WatchLifecycleError("watch item not found")
        latest_snapshot = self._runtime_history_repository.get_latest_check_snapshot(
            watch_item_id
        )
        return WatchLifecycleContext(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
        )

    def _persist_transition_decision(
        self,
        decision: WatchLifecycleDecision,
    ) -> WatchLifecycleTransitionResult:
        """保存 state machine decision 的 watch 更新與 runtime state event。"""
        assert decision.watch_item is not None
        assert decision.runtime_state_event is not None
        self._watch_item_repository.save(decision.watch_item)
        self._runtime_write_repository.append_runtime_state_event(
            decision.runtime_state_event
        )
        if decision.scheduler_action is LifecycleSchedulerAction.REMOVE:
            self._remove_from_runtime_scheduler(decision.watch_item.id)
        return WatchLifecycleTransitionResult(
            watch_item=decision.watch_item,
            event=decision.runtime_state_event,
        )

    def _remove_from_runtime_scheduler(self, watch_item_id: str) -> None:
        """依 lifecycle decision 盡量立即移除 runtime scheduler active set。"""
        if self._monitor_runtime is None:
            return
        self._monitor_runtime.remove_watch_from_schedule(watch_item_id)
