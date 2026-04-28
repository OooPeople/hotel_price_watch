from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from app.application.watch_editor import WatchCreationPreview
from app.domain.entities import PriceHistoryEntry, WatchItem
from app.domain.enums import (
    Availability,
    NotificationDeliveryStatus,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.sites.base import CandidateBundle, OfferCandidate


def _write_debug_capture(
    tmp_path,
    *,
    capture_id: str = "ikyu_preview_20260412T022211Z",
    site_name: str = "ikyu",
    captured_at: datetime | None = None,
    include_html: bool = True,
) -> dict[str, str]:
    """建立 debug capture 測試資料。"""
    debug_dir = tmp_path / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    html_path = debug_dir / f"{capture_id}.html"
    meta_path = debug_dir / f"{capture_id}_meta.json"
    if include_html:
        html_path.write_text("<html><body>candidate page</body></html>", encoding="utf-8")

    payload = {
        "site_name": site_name,
        "captured_at_utc": (
            captured_at or datetime(2026, 4, 12, 2, 22, 11, tzinfo=timezone.utc)
        ).isoformat(),
        "seed_url": "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        "parsed_hotel_name": "Ocean Hotel",
        "html_path": str(html_path) if include_html else None,
        "metadata_path": str(meta_path),
        "candidate_count": 1,
        "diagnostics": [
            {
                "stage": "candidate_parse",
                "status": "success",
                "detail": "成功解析出 1 筆候選房型方案。",
                "cooldown_seconds": None,
            }
        ],
    }
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "capture_id": capture_id,
        "html_path": str(html_path),
        "meta_path": str(meta_path),
    }


def _build_preview(
    seed_url: str,
    *,
    browser_tab_id: str | None = None,
    browser_tab_title: str | None = None,
) -> WatchCreationPreview:
    """建立新增頁測試共用的 preview。"""
    return WatchCreationPreview(
        draft=SearchDraft(
            seed_url=seed_url,
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
            room_id="room-1",
            plan_id="plan-1",
        ),
        candidate_bundle=CandidateBundle(
            hotel_id="00082173",
            hotel_name="Ocean Hotel",
            canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            candidates=(
                OfferCandidate(
                    room_id="room-1",
                    room_name="Standard Twin",
                    plan_id="plan-1",
                    plan_name="Room Only",
                    display_price_text="JPY 24000",
                    normalized_price_amount=Decimal("24000"),
                    currency="JPY",
                ),
            ),
        ),
        preselected_room_id="room-1",
        preselected_plan_id="plan-1",
        preselected_still_valid=True,
        browser_tab_id=browser_tab_id,
        browser_tab_title=browser_tab_title,
    )


def _build_watch_item() -> WatchItem:
    """建立列表頁測試共用的 watch item。"""
    return WatchItem(
        id="watch-list-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="room-1",
            plan_id="plan-1",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Ocean Hotel",
        room_name="Standard Twin",
        plan_name="Room Only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
    )


def _build_watch_item_with_below_target_rule() -> WatchItem:
    """建立通知設定頁測試用的低於目標價 watch item。"""
    return WatchItem(
        id="watch-list-2",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="room-2",
            plan_id="plan-2",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Ocean Hotel",
        room_name="Standard Twin",
        plan_name="Room Only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("20000"),
        ),
        scheduler_interval_seconds=600,
    )


def _build_latest_snapshot():
    """建立 watch 詳細頁測試用的最新摘要。"""
    from app.domain.entities import LatestCheckSnapshot

    return LatestCheckSnapshot(
        watch_item_id="watch-list-1",
        checked_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        availability=Availability.AVAILABLE,
        normalized_price_amount=Decimal("22990"),
        currency="JPY",
        is_degraded=False,
        consecutive_failures=1,
        last_error_code="http_403",
    )


def _build_price_history_entry(*, amount: Decimal, hour: int) -> PriceHistoryEntry:
    """建立首頁 24 小時價格變動測試用的歷史價格。"""
    return PriceHistoryEntry(
        watch_item_id="watch-list-1",
        captured_at=datetime(2026, 4, 12, hour, 0, tzinfo=timezone.utc),
        display_price_text=f"JPY {amount}",
        normalized_price_amount=amount,
        currency="JPY",
        source_kind=SourceKind.BROWSER,
    )


def _build_check_event():
    """建立 watch 詳細頁測試用的檢查事件。"""
    from app.domain.entities import CheckEvent

    return CheckEvent(
        watch_item_id="watch-list-1",
        checked_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        availability=Availability.AVAILABLE,
        event_kinds=("price_drop",),
        normalized_price_amount=Decimal("22990"),
        currency="JPY",
        error_code="http_403",
        notification_status=NotificationDeliveryStatus.SENT,
        sent_channels=("desktop",),
    )


def _build_notification_state():
    """建立 watch 詳細頁測試用的通知狀態。"""
    from app.domain.entities import NotificationState

    return NotificationState(
        watch_item_id="watch-list-1",
        last_notified_price=Decimal("22990"),
        last_notified_availability=Availability.AVAILABLE,
        last_notified_at=datetime(2026, 4, 12, 10, 5, tzinfo=timezone.utc),
        consecutive_failures=1,
        consecutive_parse_failures=0,
    )


def _build_debug_artifact():
    """建立 watch 詳細頁測試用的 debug artifact。"""
    from app.domain.entities import DebugArtifact

    return DebugArtifact(
        watch_item_id="watch-list-1",
        captured_at=datetime(2026, 4, 12, 10, 1, tzinfo=timezone.utc),
        reason="parse_failed",
        payload_text="<html>blocked</html>",
        source_url="https://www.ikyu.com/zh-tw/00082173/",
        http_status=403,
    )


def _build_discarded_debug_artifact():
    """建立 watch 詳細頁測試用的 page discarded debug artifact。"""
    from app.domain.entities import DebugArtifact

    return DebugArtifact(
        watch_item_id="watch-list-1",
        captured_at=datetime(2026, 4, 12, 10, 2, tzinfo=timezone.utc),
        reason="page_was_discarded",
        payload_text="<html>discarded</html>",
        source_url="https://www.ikyu.com/zh-tw/00082173/",
        http_status=None,
    )
