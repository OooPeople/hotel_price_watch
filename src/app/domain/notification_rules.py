"""Notification rule model with room for future composite rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TypeAlias

from app.domain.enums import LogicalOperator, NotificationLeafKind


@dataclass(frozen=True, slots=True)
class RuleLeaf:
    """A single notification condition exposed by the V1 UI."""

    kind: NotificationLeafKind
    target_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.kind is NotificationLeafKind.BELOW_TARGET_PRICE and self.target_price is None:
            raise ValueError("below_target_price requires target_price")
        if self.kind is NotificationLeafKind.ANY_DROP and self.target_price is not None:
            raise ValueError("any_drop must not carry target_price")


@dataclass(frozen=True, slots=True)
class CompositeRule:
    """Domain-level extension point for future AND/OR rule composition."""

    operator: LogicalOperator
    children: tuple["NotificationRule", ...]

    def __post_init__(self) -> None:
        if len(self.children) < 2:
            raise ValueError("composite rules require at least two child rules")


NotificationRule: TypeAlias = RuleLeaf | CompositeRule
