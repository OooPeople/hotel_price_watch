"""dev_start 測試共用 fake 與 builder。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget


class _FakeFetcher:
    """模擬可偵測與喚醒專用 Chrome 的 fetcher。"""

    def __init__(self, *, running: bool) -> None:
        """建立測試用 fetcher，並記錄是否已有可附著 Chrome。"""
        self.running = running
        self.opened = False
        self.open_start_url: str | None = None

    def is_debuggable_chrome_running(self) -> bool:
        """回傳目前是否已有可附著 Chrome。"""
        return self.running

    def open_profile_window(self, start_url: str | None = None) -> None:
        """記錄是否有嘗試喚醒專用 Chrome。"""
        self.opened = True
        self.open_start_url = start_url


class _FailingOpenFetcher(_FakeFetcher):
    """模擬專用 Chrome profile 啟動失敗的 fetcher。"""

    def open_profile_window(self, start_url: str | None = None) -> None:
        """記錄啟動嘗試後丟出錯誤，驗證 lock 會被清理。"""
        super().open_profile_window(start_url=start_url)
        raise ValueError("chrome launch failed")


def _build_dev_start_watch_item(watch_item_id: str) -> WatchItem:
    """建立 dev_start 測試用的最小 IKYU watch item。"""
    target = WatchTarget(
        site="ikyu",
        hotel_id="00082173",
        room_id="10191605",
        plan_id="11035620",
        check_in_date=date(2026, 9, 18),
        check_out_date=date(2026, 9, 19),
        people_count=2,
        room_count=1,
    )
    return WatchItem(
        id=watch_item_id,
        target=target,
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("20000"),
        ),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
