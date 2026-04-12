"""價格衍生計算工具。"""

from __future__ import annotations

from decimal import Decimal


def calculate_price_per_person_per_night(
    total_amount: Decimal,
    *,
    nights: int,
    people_count: int,
) -> Decimal:
    """依 V1 規格，用總價推算每人每晚價格。"""
    if nights <= 0:
        raise ValueError("nights must be positive")
    if people_count <= 0:
        raise ValueError("people_count must be positive")

    return total_amount / Decimal(nights) / Decimal(people_count)
