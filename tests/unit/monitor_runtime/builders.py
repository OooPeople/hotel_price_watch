from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.entities import NotificationState, WatchItem
from app.domain.enums import Availability, NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget


def _build_latest_snapshot(
    *,
    watch_item_id: str,
    amount: Decimal,
    availability: Availability = Availability.AVAILABLE,
    consecutive_failures: int = 0,
    last_error_code: str | None = None,
    backoff_until: datetime | None = None,
    checked_at: datetime | None = None,
):
    """建立 runtime 測試用的 latest snapshot。"""
    from app.domain.entities import LatestCheckSnapshot

    return LatestCheckSnapshot(
        watch_item_id=watch_item_id,
        checked_at=checked_at or datetime.now(UTC),
        availability=availability,
        normalized_price_amount=amount,
        currency="JPY",
        backoff_until=backoff_until,
        consecutive_failures=consecutive_failures,
        last_error_code=last_error_code,
    )


def _build_notification_state(
    *,
    watch_item_id: str,
    consecutive_failures: int,
    consecutive_parse_failures: int,
):
    """建立 runtime 恢復測試用的既有通知狀態。"""

    return NotificationState(
        watch_item_id=watch_item_id,
        consecutive_failures=consecutive_failures,
        consecutive_parse_failures=consecutive_parse_failures,
        degraded_notified_at=datetime.now(UTC),
    )


def _build_runtime_watch_item(watch_item_id: str) -> WatchItem:
    """建立 background runtime 測試共用的 watch item。"""
    return WatchItem(
        id=watch_item_id,
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
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_runtime_draft(seed_url: str) -> SearchDraft:
    """建立 background runtime 測試共用的 draft。"""
    return SearchDraft(
        seed_url=seed_url,
        hotel_id="00082173",
        room_id="10191605",
        plan_id="11035620",
        check_in_date=date(2026, 9, 18),
        check_out_date=date(2026, 9, 19),
        people_count=2,
        room_count=1,
    )
