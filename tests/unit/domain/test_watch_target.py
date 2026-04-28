from datetime import date

import pytest

from app.domain.value_objects import WatchTarget, WatchTargetIdentity


def test_watch_target_identity_excludes_currency_context() -> None:
    """驗證 watch identity 只包含目標條件，不包含價格或幣別上下文。"""
    target = WatchTarget(
        site="ikyu",
        hotel_id="hotel-1",
        room_id="room-1",
        plan_id="plan-1",
        check_in_date=date(2026, 4, 20),
        check_out_date=date(2026, 4, 22),
        people_count=2,
        room_count=1,
    )

    assert target.nights == 2
    assert target.identity_key() == WatchTargetIdentity(
        site="ikyu",
        hotel_id="hotel-1",
        room_id="room-1",
        plan_id="plan-1",
        check_in_date=date(2026, 4, 20),
        check_out_date=date(2026, 4, 22),
        people_count=2,
        room_count=1,
    )


def test_watch_target_rejects_invalid_date_range() -> None:
    """驗證退房日早於入住日會被 watch target 拒絕。"""
    with pytest.raises(ValueError):
        WatchTarget(
            site="ikyu",
            hotel_id="hotel-1",
            room_id="room-1",
            plan_id="plan-1",
            check_in_date=date(2026, 4, 22),
            check_out_date=date(2026, 4, 20),
            people_count=2,
            room_count=1,
        )


def test_watch_target_rejects_blank_identity_fields() -> None:
    """驗證 watch target 的 identity 欄位不可為空白字串。"""
    with pytest.raises(ValueError):
        WatchTarget(
            site="ikyu",
            hotel_id="hotel-1",
            room_id=" ",
            plan_id="plan-1",
            check_in_date=date(2026, 4, 20),
            check_out_date=date(2026, 4, 22),
            people_count=2,
            room_count=1,
        )
