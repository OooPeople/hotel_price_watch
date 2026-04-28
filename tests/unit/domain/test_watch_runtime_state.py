from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.domain.entities import LatestCheckSnapshot, WatchItem
from app.domain.enums import Availability, NotificationLeafKind, WatchRuntimeState
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.domain.watch_runtime_state import derive_watch_runtime_state


def test_derive_watch_runtime_state_marks_disabled_watch_correctly() -> None:
    """人工停用的 watch 應統一解讀為停用，而不是一般暫停。"""
    watch_item = _build_watch_item(enabled=False, paused_reason="manually_disabled")

    state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=None,
    )

    assert state is WatchRuntimeState.MANUALLY_DISABLED


def test_derive_watch_runtime_state_marks_resume_after_403_as_recover_pending() -> None:
    """403 暫停後人工恢復、尚未重新驗證前，應顯示恢復待驗證。"""
    watch_item = _build_watch_item(enabled=True, paused_reason=None)
    latest_snapshot = LatestCheckSnapshot(
        watch_item_id=watch_item.id,
        checked_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        availability=Availability.UNKNOWN,
        normalized_price_amount=None,
        currency=None,
        last_error_code="http_403",
    )

    state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )

    assert state is WatchRuntimeState.RECOVER_PENDING


def test_watch_item_rejects_illegal_enabled_and_paused_reason_combinations() -> None:
    """WatchItem 應拒絕明顯矛盾的啟用旗標與暫停原因組合。"""
    with pytest.raises(ValueError):
        _build_watch_item(enabled=True, paused_reason="manually_disabled")

    with pytest.raises(ValueError):
        _build_watch_item(enabled=False, paused_reason="manually_paused")

    with pytest.raises(ValueError):
        _build_watch_item(enabled=False, paused_reason="http_403")


def _build_watch_item(*, enabled: bool, paused_reason: str | None) -> WatchItem:
    """建立 runtime state 測試共用的 watch item。"""
    return WatchItem(
        id="watch-runtime-state-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="標準雙人房",
        plan_name="不含餐",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/?rm=10191605&pln=11035620",
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        enabled=enabled,
        paused_reason=paused_reason,
    )
