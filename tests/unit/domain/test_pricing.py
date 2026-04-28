from decimal import Decimal

import pytest

from app.domain.pricing import calculate_price_per_person_per_night


def test_calculate_price_per_person_per_night_from_total_amount() -> None:
    """驗證總價可依晚數與人數換算成每人每晚價格。"""
    result = calculate_price_per_person_per_night(
        Decimal("24000"),
        nights=2,
        people_count=2,
    )

    assert result == Decimal("6000")


def test_calculate_price_per_person_per_night_allows_fractional_display_value() -> None:
    """驗證無法整除的每人每晚價格會保留小數。"""
    result = calculate_price_per_person_per_night(
        Decimal("10001"),
        nights=2,
        people_count=2,
    )

    assert result == Decimal("2500.25")


@pytest.mark.parametrize(
    ("nights", "people_count"),
    [
        (0, 2),
        (2, 0),
    ],
)
def test_calculate_price_per_person_per_night_rejects_non_positive_divisors(
    nights: int,
    people_count: int,
) -> None:
    """驗證晚數或人數不為正數時會拒絕計算。"""
    with pytest.raises(ValueError):
        calculate_price_per_person_per_night(
            Decimal("24000"),
            nights=nights,
            people_count=people_count,
        )
