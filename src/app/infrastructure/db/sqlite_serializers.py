"""SQLite repository 共用的序列化與反序列化 helper。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.domain.enums import LogicalOperator, NotificationLeafKind
from app.domain.notification_rules import CompositeRule, NotificationRule, RuleLeaf


def serialize_notification_rule(rule: NotificationRule) -> dict[str, object]:
    """把 notification rule 轉成可寫入 JSON 的結構。"""
    if isinstance(rule, RuleLeaf):
        return {
            "type": "leaf",
            "kind": rule.kind.value,
            "target_price": decimal_to_text(rule.target_price),
        }
    return {
        "type": "composite",
        "operator": rule.operator.value,
        "children": [serialize_notification_rule(child) for child in rule.children],
    }


def deserialize_notification_rule(payload: dict[str, object]) -> NotificationRule:
    """把 JSON payload 還原成 notification rule。"""
    payload_type = payload["type"]
    if payload_type == "leaf":
        return RuleLeaf(
            kind=NotificationLeafKind(str(payload["kind"])),
            target_price=text_to_decimal(payload.get("target_price")),
        )
    children = tuple(
        deserialize_notification_rule(child) for child in payload["children"]  # type: ignore[index]
    )
    return CompositeRule(
        operator=LogicalOperator(str(payload["operator"])),
        children=children,
    )


def datetime_to_text(value: datetime | None) -> str | None:
    """把 `datetime` 轉成可存入 SQLite 的 ISO 字串。"""
    if value is None:
        return None
    return value.isoformat()


def text_to_datetime(value: str | None) -> datetime | None:
    """把 SQLite 內的 ISO 字串轉回 `datetime`。"""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def date_to_text(value: date | None) -> str | None:
    """把 `date` 轉成可存入 SQLite 的 ISO 字串。"""
    if value is None:
        return None
    return value.isoformat()


def text_to_date(value: str | None) -> date | None:
    """把 SQLite 內的 ISO 字串轉回 `date`。"""
    if value is None:
        return None
    return date.fromisoformat(value)


def decimal_to_text(value: Decimal | str | None) -> str | None:
    """把 `Decimal` 類值轉成 SQLite 內部使用的字串。"""
    if value is None:
        return None
    return str(value)


def text_to_decimal(value: object) -> Decimal | None:
    """把 SQLite / JSON 內的值轉回 `Decimal`。"""
    if value is None:
        return None
    return Decimal(str(value))
