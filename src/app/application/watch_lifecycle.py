"""watch lifecycle 控制面的 application service。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.domain.entities import RuntimeStateEvent, WatchItem
from app.domain.enums import RuntimeStateEventKind, WatchRuntimeState
from app.domain.watch_runtime_state import (
    derive_watch_runtime_state,
)
from app.infrastructure.db.repositories import SqliteRuntimeRepository, SqliteWatchItemRepository
from app.monitor.runtime import ChromeDrivenMonitorRuntime


class WatchLifecycleError(RuntimeError):
    """表示 watch lifecycle 命令目前不可執行。"""


@dataclass(frozen=True, slots=True)
class WatchLifecycleTransitionResult:
    """描述單次 watch lifecycle transition 的輸出結果。"""

    watch_item: WatchItem
    event: RuntimeStateEvent


@dataclass(frozen=True, slots=True)
class WatchControlSnapshot:
    """保存判斷 control command 時需要的 watch 與目前 runtime state。"""

    watch_item: WatchItem
    runtime_state: WatchRuntimeState


class WatchLifecycleCoordinator:
    """統一協調 watch 手動控制命令與 runtime 執行入口。"""

    def __init__(
        self,
        *,
        watch_item_repository: SqliteWatchItemRepository,
        runtime_repository: SqliteRuntimeRepository,
        monitor_runtime: ChromeDrivenMonitorRuntime | None,
    ) -> None:
        self._watch_item_repository = watch_item_repository
        self._runtime_repository = runtime_repository
        self._monitor_runtime = monitor_runtime

    def enable_watch(self, watch_item_id: str):
        """啟用 watch，並由 lifecycle owner 記錄正式 transition event。"""
        return self._apply_manual_transition(
            watch_item_id=watch_item_id,
            enabled=True,
            paused_reason=None,
            event_kind=RuntimeStateEventKind.MANUAL_ENABLE,
        ).watch_item

    def disable_watch(self, watch_item_id: str):
        """停用 watch，阻止後續排程與手動立即檢查。"""
        return self._apply_manual_transition(
            watch_item_id=watch_item_id,
            enabled=False,
            paused_reason="manually_disabled",
            event_kind=RuntimeStateEventKind.MANUAL_DISABLE,
        ).watch_item

    def pause_watch(self, watch_item_id: str):
        """暫停 watch，阻止後續排程與手動立即檢查。"""
        return self._apply_manual_transition(
            watch_item_id=watch_item_id,
            enabled=True,
            paused_reason="manually_paused",
            event_kind=RuntimeStateEventKind.MANUAL_PAUSE,
        ).watch_item

    def resume_watch(self, watch_item_id: str):
        """恢復 watch，使其重新進入 runtime 可檢查狀態。"""
        return self._apply_manual_transition(
            watch_item_id=watch_item_id,
            enabled=True,
            paused_reason=None,
            event_kind=RuntimeStateEventKind.MANUAL_RESUME,
        ).watch_item

    async def request_check_now(self, watch_item_id: str) -> None:
        """檢查 watch 是否可執行後，才轉交 runtime 立即檢查。"""
        control_snapshot = self._get_control_snapshot(watch_item_id)
        self._ensure_check_now_allowed(control_snapshot)
        if self._monitor_runtime is None:
            raise WatchLifecycleError("background monitor runtime is not available")
        await self._monitor_runtime.request_check_now(watch_item_id)

    def _apply_manual_transition(
        self,
        *,
        watch_item_id: str,
        enabled: bool,
        paused_reason: str | None,
        event_kind: RuntimeStateEventKind,
    ) -> WatchLifecycleTransitionResult:
        """套用人工 control transition，並由同一權威入口保存事件。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise WatchLifecycleError("watch item not found")
        latest_snapshot = self._runtime_repository.get_latest_check_snapshot(watch_item_id)
        updated_watch_item = replace(
            watch_item,
            enabled=enabled,
            paused_reason=paused_reason,
        )
        self._watch_item_repository.save(updated_watch_item)
        event = RuntimeStateEvent(
            watch_item_id=watch_item_id,
            occurred_at=datetime.now(UTC),
            event_kind=event_kind,
            from_state=derive_watch_runtime_state(
                watch_item=watch_item,
                latest_snapshot=latest_snapshot,
            ),
            to_state=derive_watch_runtime_state(
                watch_item=updated_watch_item,
                latest_snapshot=latest_snapshot,
            ),
        )
        self._runtime_repository.append_runtime_state_event(event)
        return WatchLifecycleTransitionResult(
            watch_item=updated_watch_item,
            event=event,
        )

    def _get_control_snapshot(self, watch_item_id: str) -> WatchControlSnapshot:
        """讀取 watch 與目前 runtime state，作為 control command 判斷依據。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise WatchLifecycleError("watch item not found")
        latest_snapshot = self._runtime_repository.get_latest_check_snapshot(watch_item_id)
        return WatchControlSnapshot(
            watch_item=watch_item,
            runtime_state=derive_watch_runtime_state(
                watch_item=watch_item,
                latest_snapshot=latest_snapshot,
            ),
        )

    def _ensure_check_now_allowed(
        self,
        control_snapshot: WatchControlSnapshot,
    ) -> None:
        """確認目前 watch control state 允許立即檢查。"""
        watch_item = control_snapshot.watch_item
        if not watch_item.enabled or watch_item.paused_reason is not None:
            raise WatchLifecycleError(
                f"watch is not checkable in state {control_snapshot.runtime_state.value}"
            )
