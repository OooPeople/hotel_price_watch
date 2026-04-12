"""領域層使用的 value object。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SearchDraft:
    """表示使用者在 watch editor 內可逐步補完的查詢草稿。"""

    seed_url: str
    check_in_date: date | None = None
    check_out_date: date | None = None
    people_count: int | None = None
    room_count: int | None = None
    hotel_id: str | None = None
    room_id: str | None = None
    plan_id: str | None = None
    browser_tab_id: str | None = None
    browser_page_url: str | None = None

    @property
    def nights(self) -> int | None:
        """回傳草稿中的住宿晚數；若日期尚未完整則回傳 `None`。"""
        if self.check_in_date is None or self.check_out_date is None:
            return None
        return (self.check_out_date - self.check_in_date).days

    def is_ready_for_candidate_lookup(self) -> bool:
        """判斷草稿是否已具備查候選方案所需的最低條件。"""
        return (
            self.hotel_id is not None
            and self.check_in_date is not None
            and self.check_out_date is not None
            and self.people_count is not None
            and self.room_count is not None
        )


@dataclass(frozen=True, slots=True)
class WatchTarget:
    """表示已 canonicalize、可交給 monitor 使用的正式目標。"""

    site: str
    hotel_id: str
    room_id: str
    plan_id: str
    check_in_date: date
    check_out_date: date
    people_count: int
    room_count: int

    def __post_init__(self) -> None:
        """驗證進入 monitor 的 target 已具備基本不變條件。"""
        for field_name, value in (
            ("site", self.site),
            ("hotel_id", self.hotel_id),
            ("room_id", self.room_id),
            ("plan_id", self.plan_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        if self.people_count <= 0:
            raise ValueError("people_count must be positive")
        if self.room_count <= 0:
            raise ValueError("room_count must be positive")

    @property
    def nights(self) -> int:
        """回傳 watch target 的住宿晚數。"""
        return (self.check_out_date - self.check_in_date).days

    def identity_key(self) -> tuple[str, str, str, str, date, date, int, int]:
        """回傳不含顯示語境欄位的穩定 identity key。"""
        return (
            self.site,
            self.hotel_id,
            self.room_id,
            self.plan_id,
            self.check_in_date,
            self.check_out_date,
            self.people_count,
            self.room_count,
        )
