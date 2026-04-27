"""watch 詳細頁使用的 page-level presentation model。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain import derive_watch_runtime_state
from app.domain.entities import LatestCheckSnapshot, NotificationState, WatchItem
from app.domain.enums import WatchRuntimeState
from app.web.ui_presenters import (
    BadgePresentation,
    availability_badge,
    money_text,
    notification_rule_text,
    runtime_state_badge,
)


@dataclass(frozen=True, slots=True)
class WatchDetailPresentation:
    """集中監視詳情頁首屏與摘要卡需要的顯示資料。"""

    watch_id: str
    hotel_name: str
    room_name: str
    canonical_url: str
    scheduler_interval_seconds: int
    date_range_text: str
    occupancy_text: str
    runtime_state: WatchRuntimeState
    runtime_state_badge: BadgePresentation
    last_checked_at: datetime | None
    current_price_text: str
    availability_text: str
    notification_rule_text: str
    last_notified_at: datetime | None


def build_watch_detail_presentation(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    notification_state: NotificationState | None,
) -> WatchDetailPresentation:
    """把 watch 詳細頁會用到的 domain 資料整理成穩定 view model。"""
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    return WatchDetailPresentation(
        watch_id=watch_item.id,
        hotel_name=watch_item.hotel_name,
        room_name=watch_item.room_name,
        canonical_url=watch_item.canonical_url,
        scheduler_interval_seconds=watch_item.scheduler_interval_seconds,
        date_range_text=(
            f"{watch_item.target.check_in_date.isoformat()} - "
            f"{watch_item.target.check_out_date.isoformat()}"
        ),
        occupancy_text=(
            f"{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房"
        ),
        runtime_state=runtime_state,
        runtime_state_badge=runtime_state_badge(runtime_state),
        last_checked_at=(
            latest_snapshot.checked_at if latest_snapshot is not None else None
        ),
        current_price_text=(
            money_text(
                latest_snapshot.currency,
                latest_snapshot.normalized_price_amount,
            )
            if latest_snapshot is not None
            else "尚未檢查"
        ),
        availability_text=(
            availability_badge(latest_snapshot.availability).label
            if latest_snapshot is not None
            else "尚未檢查"
        ),
        notification_rule_text=notification_rule_text(watch_item),
        last_notified_at=(
            notification_state.last_notified_at
            if notification_state is not None
            else None
        ),
    )
