from decimal import Decimal

import pytest

from app.domain.enums import LogicalOperator, NotificationLeafKind
from app.domain.notification_rules import CompositeRule, RuleLeaf


def test_below_target_price_requires_target_price() -> None:
    with pytest.raises(ValueError):
        RuleLeaf(kind=NotificationLeafKind.BELOW_TARGET_PRICE)


def test_any_drop_rejects_target_price() -> None:
    with pytest.raises(ValueError):
        RuleLeaf(
            kind=NotificationLeafKind.ANY_DROP,
            target_price=Decimal("10000"),
        )


def test_composite_rule_requires_multiple_children() -> None:
    leaf = RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("10000"),
    )

    with pytest.raises(ValueError):
        CompositeRule(operator=LogicalOperator.AND, children=(leaf,))
