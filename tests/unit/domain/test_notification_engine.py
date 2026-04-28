from datetime import datetime
from decimal import Decimal

from app.domain.entities import NotificationState, PriceSnapshot
from app.domain.enums import Availability, NotificationEventKind, NotificationLeafKind, SourceKind
from app.domain.notification_engine import compare_snapshots, evaluate_notification_rule
from app.domain.notification_rules import RuleLeaf


def test_any_drop_notifies_on_price_drop() -> None:
    """驗證任意降價規則在價格下降時會產生通知決策。"""
    result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=_snapshot(amount="24000"),
        current_snapshot=_snapshot(amount="22000"),
    )

    decision = evaluate_notification_rule(
        rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        check_result=result,
        notification_state=NotificationState(watch_item_id="watch-1"),
    )

    assert decision.should_notify is True
    assert decision.event_kinds == (NotificationEventKind.PRICE_DROP,)
    assert decision.next_state.last_notified_price == Decimal("22000")


def test_below_target_price_notifies_when_price_changes_under_threshold() -> None:
    """驗證低於目標價規則在低於門檻且價格變動時會通知。"""
    rule = RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )
    first_result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=_snapshot(amount="21000"),
        current_snapshot=_snapshot(amount="19000"),
    )
    first_decision = evaluate_notification_rule(
        rule=rule,
        check_result=first_result,
        notification_state=NotificationState(watch_item_id="watch-1"),
    )

    second_result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 10, 0),
        previous_snapshot=_snapshot(amount="19000"),
        current_snapshot=_snapshot(amount="19500"),
    )
    second_decision = evaluate_notification_rule(
        rule=rule,
        check_result=second_result,
        notification_state=first_decision.next_state,
    )

    assert first_decision.event_kinds == (NotificationEventKind.BELOW_TARGET_PRICE,)
    assert second_decision.event_kinds == (NotificationEventKind.BELOW_TARGET_PRICE,)
    assert second_decision.next_state.last_notified_price == Decimal("19500")


def test_below_target_price_dedupes_same_price_and_availability() -> None:
    """驗證同價格與同 availability 的低於目標價通知會去重。"""
    rule = RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )
    current = _snapshot(amount="19000")
    result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=_snapshot(amount="19000"),
        current_snapshot=current,
    )

    decision = evaluate_notification_rule(
        rule=rule,
        check_result=result,
        notification_state=NotificationState(
            watch_item_id="watch-1",
            last_notified_price=Decimal("19000"),
            last_notified_availability=Availability.AVAILABLE,
        ),
    )

    assert decision.should_notify is False
    assert decision.event_kinds == ()


def test_became_available_is_notified_independently() -> None:
    """驗證從售完變可訂會獨立觸發恢復可訂通知。"""
    result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=_snapshot(amount=None, availability=Availability.SOLD_OUT),
        current_snapshot=_snapshot(amount="24000", availability=Availability.AVAILABLE),
    )

    decision = evaluate_notification_rule(
        rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        check_result=result,
        notification_state=NotificationState(watch_item_id="watch-1"),
    )

    assert decision.event_kinds == (NotificationEventKind.BECAME_AVAILABLE,)


def test_became_available_ignores_immediate_unknown_when_last_effective_is_available() -> None:
    """驗證 unknown 到 available 若上個有效狀態已可訂，不算恢復可訂。"""
    result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=_snapshot(amount=None, availability=Availability.UNKNOWN),
        current_snapshot=_snapshot(amount="24000", availability=Availability.AVAILABLE),
        previous_effective_availability=Availability.AVAILABLE,
    )

    decision = evaluate_notification_rule(
        rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        check_result=result,
        notification_state=NotificationState(watch_item_id="watch-1"),
    )

    assert decision.event_kinds == ()


def test_became_available_looks_back_to_last_effective_sold_out() -> None:
    """驗證 unknown 之前最後有效狀態為售完時，回到 available 會通知。"""
    result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=_snapshot(amount=None, availability=Availability.UNKNOWN),
        current_snapshot=_snapshot(amount="24000", availability=Availability.AVAILABLE),
        previous_effective_availability=Availability.SOLD_OUT,
    )

    decision = evaluate_notification_rule(
        rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        check_result=result,
        notification_state=NotificationState(watch_item_id="watch-1"),
    )

    assert decision.event_kinds == (NotificationEventKind.BECAME_AVAILABLE,)


def test_first_successful_snapshot_is_not_treated_as_became_available() -> None:
    """驗證第一筆成功 snapshot 不會被誤判為恢復可訂。"""
    result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        previous_snapshot=None,
        current_snapshot=_snapshot(amount="24000", availability=Availability.AVAILABLE),
    )

    decision = evaluate_notification_rule(
        rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        check_result=result,
        notification_state=NotificationState(watch_item_id="watch-1"),
    )

    assert decision.event_kinds == ()


def test_parse_failed_only_notifies_when_streak_reaches_three() -> None:
    """驗證解析失敗需達到指定連續次數才會通知，且通知後會去重。"""
    rule = RuleLeaf(kind=NotificationLeafKind.ANY_DROP)
    state = NotificationState(watch_item_id="watch-1")

    for minute in (0, 10):
        result = compare_snapshots(
            checked_at=datetime(2026, 4, 12, 10, minute, 0),
            previous_snapshot=None,
            current_snapshot=_snapshot(amount=None, availability=Availability.PARSE_ERROR),
        )
        decision = evaluate_notification_rule(
            rule=rule,
            check_result=result,
            notification_state=state,
        )
        assert decision.should_notify is False
        state = decision.next_state

    third_result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 20, 0),
        previous_snapshot=None,
        current_snapshot=_snapshot(amount=None, availability=Availability.PARSE_ERROR),
    )
    third_decision = evaluate_notification_rule(
        rule=rule,
        check_result=third_result,
        notification_state=state,
    )

    fourth_result = compare_snapshots(
        checked_at=datetime(2026, 4, 12, 10, 30, 0),
        previous_snapshot=None,
        current_snapshot=_snapshot(amount=None, availability=Availability.PARSE_ERROR),
    )
    fourth_decision = evaluate_notification_rule(
        rule=rule,
        check_result=fourth_result,
        notification_state=third_decision.next_state,
    )

    assert third_decision.event_kinds == (NotificationEventKind.PARSE_FAILED,)
    assert fourth_decision.should_notify is False


def _snapshot(
    *,
    amount: str | None,
    availability: Availability = Availability.AVAILABLE,
) -> PriceSnapshot:
    """建立通知規則測試用的價格快照。"""
    return PriceSnapshot(
        display_price_text=None if amount is None else f"JPY {amount}",
        normalized_price_amount=None if amount is None else Decimal(amount),
        currency=None if amount is None else "JPY",
        availability=availability,
        source_kind=SourceKind.HTTP,
    )
