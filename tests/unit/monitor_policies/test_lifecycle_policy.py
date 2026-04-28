"""monitor task lifecycle 與 wakeup rescan policy 測試。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from app.domain.enums import CheckErrorCode
from app.monitor.policies import (
    TaskDispositionKind,
    TaskLifecycleCheckpoint,
    build_runtime_control_recommendation,
    decide_error_handling,
    evaluate_task_lifecycle_disposition,
    should_trigger_wakeup_rescan,
)

from .helpers import _latest_snapshot, _watch_item


def test_runtime_control_recommendation_pauses_for_forbidden() -> None:
    """runtime control recommendation 應把 forbidden 決策轉成暫停 watch。"""
    watch_item = _watch_item()
    checked_at = datetime(2026, 4, 12, 10, 0, 0)
    recommendation = build_runtime_control_recommendation(
        watch_item=watch_item,
        latest_snapshot=None,
        next_snapshot=_latest_snapshot(checked_at=checked_at),
        error_handling=decide_error_handling(
            checked_at=checked_at,
            error_code=CheckErrorCode.FORBIDDEN_403,
            consecutive_failures=1,
        ),
        error_code=CheckErrorCode.FORBIDDEN_403,
        occurred_at=checked_at,
    )

    assert recommendation.watch_item is not None
    assert recommendation.watch_item.enabled is True
    assert recommendation.watch_item.paused_reason == "http_403"
    assert recommendation.remove_from_scheduler is True

def test_task_lifecycle_policy_allows_active_watch_to_continue() -> None:
    """active watch 在 checkpoint 應可繼續執行下一個 side effect。"""
    disposition = evaluate_task_lifecycle_disposition(
        watch_item=_watch_item(),
        checkpoint=TaskLifecycleCheckpoint.BEFORE_NOTIFICATION_DISPATCH,
    )

    assert disposition.kind is TaskDispositionKind.CONTINUE
    assert disposition.should_continue is True
    assert disposition.reason is None

def test_task_lifecycle_policy_discards_paused_watch() -> None:
    """paused watch 在 checkpoint 應丟棄後續結果。"""
    disposition = evaluate_task_lifecycle_disposition(
        watch_item=replace(_watch_item(), paused_reason="manually_paused"),
        checkpoint=TaskLifecycleCheckpoint.BEFORE_PERSIST_RESULT,
    )

    assert disposition.kind is TaskDispositionKind.DISCARD
    assert disposition.should_discard is True
    assert disposition.reason == "watch_paused:manually_paused"

def test_task_lifecycle_policy_discards_missing_watch() -> None:
    """不存在的 watch 在 checkpoint 應丟棄後續結果。"""
    disposition = evaluate_task_lifecycle_disposition(
        watch_item=None,
        checkpoint=TaskLifecycleCheckpoint.AFTER_CAPTURE,
    )

    assert disposition.kind is TaskDispositionKind.DISCARD
    assert disposition.reason == "watch_missing"

def test_wakeup_rescan_respects_backoff_window() -> None:
    """驗證恢復後喚醒重掃不會繞過尚未結束的 backoff。"""
    resumed_at = datetime(2026, 4, 12, 10, 30, 0)

    assert (
        should_trigger_wakeup_rescan(
            resumed_at=resumed_at,
            last_checked_at=datetime(2026, 4, 12, 9, 0, 0),
            backoff_until=resumed_at + timedelta(minutes=5),
        )
        is False
    )
    assert (
        should_trigger_wakeup_rescan(
            resumed_at=resumed_at,
            last_checked_at=datetime(2026, 4, 12, 9, 0, 0),
            backoff_until=None,
        )
        is True
    )
