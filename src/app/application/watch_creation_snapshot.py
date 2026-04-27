"""建立 watch 時保存初始價格摘要的 application service。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.watch_editor import WatchCreationPreview
from app.domain.entities import CheckEvent, LatestCheckSnapshot, PriceHistoryEntry
from app.domain.enums import Availability, SourceKind
from app.infrastructure.db.repositories import SqliteRuntimeRepository
from app.sites.base import OfferCandidate


class WatchCreationSnapshotService:
    """負責把新增監視 preview 取得的價格保存成初始 runtime snapshot。"""

    def __init__(self, runtime_repository: SqliteRuntimeRepository) -> None:
        self._runtime_repository = runtime_repository

    def persist_initial_snapshot_from_preview(
        self,
        *,
        preview: WatchCreationPreview,
        watch_item_id: str,
        room_id: str,
        plan_id: str,
    ) -> None:
        """從 preview 候選方案保存初始價格；沒有可用價格時不寫入。"""
        candidate = _find_candidate_for_initial_snapshot(
            preview=preview,
            room_id=room_id,
            plan_id=plan_id,
        )
        if candidate is None or candidate.normalized_price_amount is None:
            return

        captured_at = datetime.now(UTC)
        currency = candidate.currency or "JPY"
        self._runtime_repository.persist_initial_check_snapshot(
            latest_snapshot=LatestCheckSnapshot(
                watch_item_id=watch_item_id,
                checked_at=captured_at,
                availability=Availability.AVAILABLE,
                normalized_price_amount=candidate.normalized_price_amount,
                currency=currency,
            ),
            check_event=CheckEvent(
                watch_item_id=watch_item_id,
                checked_at=captured_at,
                availability=Availability.AVAILABLE,
                event_kinds=("initial_snapshot",),
                normalized_price_amount=candidate.normalized_price_amount,
                currency=currency,
            ),
            price_history_entry=PriceHistoryEntry(
                watch_item_id=watch_item_id,
                captured_at=captured_at,
                display_price_text=_display_price_text_for_initial_snapshot(
                    candidate=candidate,
                    currency=currency,
                ),
                normalized_price_amount=candidate.normalized_price_amount,
                currency=currency,
                source_kind=SourceKind.BROWSER,
            ),
        )


def _find_candidate_for_initial_snapshot(
    *,
    preview: WatchCreationPreview,
    room_id: str,
    plan_id: str,
) -> OfferCandidate | None:
    """從建立表單選取的 room/plan 找回 preview 內的候選方案。"""
    return next(
        (
            candidate
            for candidate in preview.candidate_bundle.candidates
            if candidate.room_id == room_id and candidate.plan_id == plan_id
        ),
        None,
    )


def _display_price_text_for_initial_snapshot(
    *,
    candidate: OfferCandidate,
    currency: str,
) -> str:
    """取得初始價格歷史要顯示的價格字串。"""
    if candidate.display_price_text:
        return candidate.display_price_text
    return f"{currency} {candidate.normalized_price_amount}"
