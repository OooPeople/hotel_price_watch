"""monitor policy 測試共用 builder。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.domain.entities import LatestCheckSnapshot, PriceSnapshot, WatchItem
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget


def _snapshot(
    *,
    amount: str | None,
    availability: Availability = Availability.AVAILABLE,
) -> PriceSnapshot:
    """建立 monitor policy 測試共用的價格快照。"""
    return PriceSnapshot(
        display_price_text=None if amount is None else f"JPY {amount}",
        normalized_price_amount=None if amount is None else Decimal(amount),
        currency=None if amount is None else "JPY",
        availability=availability,
        source_kind=SourceKind.HTTP,
    )


def _latest_snapshot(*, checked_at: datetime) -> LatestCheckSnapshot:
    """建立 runtime control recommendation 測試使用的最新檢查摘要。"""
    return LatestCheckSnapshot(
        watch_item_id="watch-1",
        checked_at=checked_at,
        availability=Availability.UNKNOWN,
        normalized_price_amount=None,
        currency=None,
        consecutive_failures=1,
        last_error_code=CheckErrorCode.FORBIDDEN_403.value,
    )


def _watch_item() -> WatchItem:
    """建立 monitor policy 測試使用的 watch item。"""
    return WatchItem(
        id="watch-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=datetime(2026, 9, 18).date(),
            check_out_date=datetime(2026, 9, 19).date(),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="Room",
        plan_name="Plan",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("20000"),
        ),
        scheduler_interval_seconds=600,
    )
