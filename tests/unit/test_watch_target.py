from datetime import date

from app.domain.value_objects import WatchTarget


def test_watch_target_identity_excludes_currency_context() -> None:
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
    assert target.identity_key() == (
        "ikyu",
        "hotel-1",
        "room-1",
        "plan-1",
        date(2026, 4, 20),
        date(2026, 4, 22),
        2,
        1,
    )
