from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.application.preview_guard import PreviewAttemptGuard
from app.domain.enums import NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.sites.base import LookupDiagnostic

from .helpers import (
    _build_test_container,
)


def test_watch_editor_service_creates_watch_item_and_saves_it(tmp_path) -> None:
    """驗證 watch editor service 可由 preview 建立並保存 watch item。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )

    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )

    saved_items = container.watch_item_repository.list_all()
    assert len(saved_items) == 1
    assert saved_items[0].id == watch_item.id
    assert saved_items[0].notification_rule == RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )
    assert saved_items[0].target.check_in_date == date(2026, 9, 18)


def test_watch_editor_service_can_delete_saved_watch_item(tmp_path) -> None:
    """watch editor service 應能刪除既有 watch item。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )

    container.watch_editor_service.delete_watch_item(watch_item.id)

    assert container.watch_item_repository.list_all() == []


def test_watch_editor_service_can_update_notification_rule(tmp_path) -> None:
    """watch editor service 應能更新既有 watch item 的通知條件。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )

    updated_watch_item = container.watch_editor_service.update_notification_rule(
        watch_item_id=watch_item.id,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )

    assert updated_watch_item.notification_rule == RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )
    assert container.watch_item_repository.get(watch_item.id) == updated_watch_item


def test_preview_guard_blocks_immediate_retry_after_blocked_page() -> None:
    """命中阻擋頁後，下一次 preview 應直接被 guard 擋下。"""
    guard = PreviewAttemptGuard(
        min_interval_seconds=20.0,
        blocked_page_cooldown_seconds=1800.0,
    )

    guard.register_result(
        site_name="ikyu",
        diagnostics=(
            LookupDiagnostic(
                stage="browser_fallback_direct",
                status="failed",
                detail="ikyu 已回傳阻擋頁面；目前連 browser fallback 都被站方防護攔下。",
            ),
        )
    )

    try:
        guard.ensure_allowed(site_name="ikyu")
    except ValueError as exc:
        assert "冷卻中" in str(exc)
        assert exc.diagnostics[0].stage == "preview_rate_guard"
    else:
        raise AssertionError("expected preview guard to block immediate retry")


def test_preview_guard_cooldown_is_scoped_by_site() -> None:
    """不同站點的 preview 冷卻不應互相阻擋。"""
    guard = PreviewAttemptGuard(
        min_interval_seconds=20.0,
        blocked_page_cooldown_seconds=1800.0,
    )

    guard.register_result(
        site_name="ikyu",
        diagnostics=(
            LookupDiagnostic(
                stage="browser_fallback_direct",
                status="failed",
                detail="ikyu 已回傳阻擋頁面；目前連 browser fallback 都被站方防護攔下。",
            ),
        ),
    )

    guard.ensure_allowed(site_name="second_site")
    try:
        guard.ensure_allowed(site_name="ikyu")
    except ValueError:
        return
    raise AssertionError("expected ikyu cooldown to remain active")
