"""watch runtime 狀態的正式解讀邏輯。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.entities import LatestCheckSnapshot, WatchItem
from app.domain.enums import WatchRuntimeState


def derive_watch_runtime_state(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    now: datetime | None = None,
) -> WatchRuntimeState:
    """把 watch 設定與最新 runtime 摘要整理成單一狀態。"""
    current_time = now or datetime.now(UTC)

    if not watch_item.enabled:
        return WatchRuntimeState.MANUALLY_DISABLED
    if watch_item.paused_reason == "http_403":
        return WatchRuntimeState.PAUSED_BLOCKED
    if watch_item.paused_reason == "manually_paused":
        return WatchRuntimeState.MANUALLY_PAUSED
    if watch_item.paused_reason is not None:
        return WatchRuntimeState.PAUSED_OTHER
    if (
        latest_snapshot is not None
        and latest_snapshot.last_error_code == "http_403"
    ):
        return WatchRuntimeState.RECOVER_PENDING
    if (
        latest_snapshot is not None
        and latest_snapshot.backoff_until is not None
        and latest_snapshot.backoff_until > current_time
    ):
        return WatchRuntimeState.BACKOFF_ACTIVE
    if latest_snapshot is not None and latest_snapshot.is_degraded:
        return WatchRuntimeState.DEGRADED_ACTIVE
    return WatchRuntimeState.ACTIVE


def describe_watch_runtime_state(state: WatchRuntimeState) -> str:
    """把 runtime 狀態整理成 GUI 可直接顯示的文字。"""
    labels = {
        WatchRuntimeState.ACTIVE: "啟用",
        WatchRuntimeState.BACKOFF_ACTIVE: "退避中",
        WatchRuntimeState.DEGRADED_ACTIVE: "降級運作",
        WatchRuntimeState.RECOVER_PENDING: "恢復待驗證",
        WatchRuntimeState.MANUALLY_PAUSED: "人工暫停",
        WatchRuntimeState.MANUALLY_DISABLED: "停用",
        WatchRuntimeState.PAUSED_BLOCKED: "站方阻擋已暫停",
        WatchRuntimeState.PAUSED_BLOCKED_403: "站方阻擋已暫停",
        WatchRuntimeState.PAUSED_OTHER: "暫停",
    }
    return labels[state]
