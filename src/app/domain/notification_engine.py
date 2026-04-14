"""單次檢查比較與通知判定邏輯。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from app.domain.entities import (
    CheckResult,
    NotificationDecision,
    NotificationState,
    PriceSnapshot,
)
from app.domain.enums import (
    Availability,
    LogicalOperator,
    NotificationEventKind,
    NotificationLeafKind,
)
from app.domain.notification_rules import NotificationRule, RuleLeaf


def compare_snapshots(
    *,
    checked_at: datetime,
    current_snapshot: PriceSnapshot,
    previous_snapshot: PriceSnapshot | None,
    previous_effective_availability: Availability | None = None,
) -> CheckResult:
    """比較前後兩次快照，整理出後續判定需要的變化資訊。"""
    current_price = current_snapshot.normalized_price_amount
    previous_price = previous_snapshot.normalized_price_amount if previous_snapshot else None
    effective_previous_availability = (
        previous_effective_availability
        if previous_effective_availability is not None
        else previous_snapshot.availability if previous_snapshot is not None else None
    )

    return CheckResult(
        checked_at=checked_at,
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        price_changed=current_price != previous_price,
        availability_changed=(
            previous_snapshot is None
            or current_snapshot.availability != previous_snapshot.availability
        ),
        price_dropped=(
            current_price is not None
            and previous_price is not None
            and current_price < previous_price
        ),
        became_available=(
            effective_previous_availability is Availability.SOLD_OUT
            and current_snapshot.availability is Availability.AVAILABLE
        ),
        parse_failed=current_snapshot.availability is Availability.PARSE_ERROR,
    )


def evaluate_notification_rule(
    *,
    rule: NotificationRule,
    check_result: CheckResult,
    notification_state: NotificationState,
) -> NotificationDecision:
    """依規則、比較結果與既有去重狀態決定是否通知。"""
    next_state = _update_parse_failure_state(
        state=notification_state,
        check_result=check_result,
    )
    matched_events = list(
        _evaluate_rule_events(
            rule=rule,
            check_result=check_result,
            notification_state=next_state,
        )
    )

    if check_result.became_available:
        matched_events.append(NotificationEventKind.BECAME_AVAILABLE)

    if (
        check_result.parse_failed
        and next_state.consecutive_parse_failures >= 3
        and next_state.degraded_notified_at is None
    ):
        matched_events.append(NotificationEventKind.PARSE_FAILED)
        next_state = replace(next_state, degraded_notified_at=check_result.checked_at)

    deduped_events = _dedupe_events(matched_events)
    if deduped_events:
        next_state = replace(
            next_state,
            last_notified_price=check_result.current_snapshot.normalized_price_amount,
            last_notified_availability=check_result.current_snapshot.availability,
            last_notified_at=check_result.checked_at,
        )

    return NotificationDecision(
        event_kinds=deduped_events,
        next_state=next_state,
    )


def _evaluate_rule_events(
    *,
    rule: NotificationRule,
    check_result: CheckResult,
    notification_state: NotificationState,
) -> tuple[NotificationEventKind, ...]:
    """判斷規則本身對這次檢查是否產生通知事件。"""
    if isinstance(rule, RuleLeaf):
        return _evaluate_leaf_rule(
            rule=rule,
            check_result=check_result,
            notification_state=notification_state,
        )

    child_event_sets = tuple(
        _evaluate_rule_events(
            rule=child,
            check_result=check_result,
            notification_state=notification_state,
        )
        for child in rule.children
    )
    if rule.operator is LogicalOperator.AND:
        if all(child_event_sets):
            return _dedupe_events(event for events in child_event_sets for event in events)
        return ()
    if rule.operator is LogicalOperator.OR:
        return _dedupe_events(event for events in child_event_sets for event in events)
    raise ValueError(f"unsupported logical operator: {rule.operator}")


def _evaluate_leaf_rule(
    *,
    rule: RuleLeaf,
    check_result: CheckResult,
    notification_state: NotificationState,
) -> tuple[NotificationEventKind, ...]:
    """判斷單一通知規則是否在本次檢查中命中。"""
    snapshot = check_result.current_snapshot

    if rule.kind is NotificationLeafKind.ANY_DROP:
        if check_result.price_dropped:
            return (NotificationEventKind.PRICE_DROP,)
        return ()

    if rule.kind is NotificationLeafKind.BELOW_TARGET_PRICE:
        if rule.target_price is None:
            raise ValueError("below_target_price requires target_price")
        current_price = snapshot.normalized_price_amount
        if current_price is None or current_price >= rule.target_price:
            return ()
        if (
            notification_state.last_notified_price == current_price
            and notification_state.last_notified_availability == snapshot.availability
        ):
            return ()
        return (NotificationEventKind.BELOW_TARGET_PRICE,)

    raise ValueError(f"unsupported notification rule kind: {rule.kind}")


def _update_parse_failure_state(
    *,
    state: NotificationState,
    check_result: CheckResult,
) -> NotificationState:
    """更新 parse failure streak 與 degraded 去重狀態。"""
    if check_result.parse_failed:
        return replace(
            state,
            consecutive_failures=state.consecutive_failures + 1,
            consecutive_parse_failures=state.consecutive_parse_failures + 1,
        )

    return replace(
        state,
        consecutive_failures=0,
        consecutive_parse_failures=0,
        degraded_notified_at=None,
    )


def _dedupe_events(
    events: Iterable[NotificationEventKind],
) -> tuple[NotificationEventKind, ...]:
    """保留事件順序並移除重複事件。"""
    ordered: list[NotificationEventKind] = []
    seen: set[NotificationEventKind] = set()
    for event in events:
        if event not in seen:
            ordered.append(event)
            seen.add(event)
    return tuple(ordered)
