"""watch editor 的 application service。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import uuid4

from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft
from app.infrastructure.db.repositories import SqliteWatchItemRepository
from app.sites.base import CandidateBundle, CandidateSelection, LookupDiagnostic
from app.sites.registry import SiteRegistry


@dataclass(frozen=True, slots=True)
class WatchCreationPreview:
    """表示 watch editor 預覽頁需要的解析結果。"""

    draft: SearchDraft
    candidate_bundle: CandidateBundle
    preselected_room_id: str | None
    preselected_plan_id: str | None
    preselected_still_valid: bool
    diagnostics: tuple[LookupDiagnostic, ...] = ()
    browser_tab_id: str | None = None
    browser_tab_title: str | None = None
    browser_page_url: str | None = None


class WatchEditorService:
    """負責從 seed URL 建立 watch item 的 editor 流程。"""

    def __init__(
        self,
        *,
        site_registry: SiteRegistry,
        watch_item_repository: SqliteWatchItemRepository,
    ) -> None:
        self._site_registry = site_registry
        self._watch_item_repository = watch_item_repository

    def preview_from_seed_url(self, seed_url: str) -> WatchCreationPreview:
        """解析 seed URL，並抓回可供 UI 選擇的候選方案。"""
        adapter = self._site_registry.for_url(seed_url)
        draft = adapter.parse_seed_url(seed_url)
        return self.preview_from_draft(draft)

    def preview_from_draft(self, draft: SearchDraft) -> WatchCreationPreview:
        """依已補完的草稿查詢候選，供 editor 第二段反覆重查使用。"""
        adapter = self._site_registry.for_url(draft.seed_url)
        candidate_bundle = adapter.fetch_candidates(draft)
        preselected_still_valid = any(
            candidate.room_id == draft.room_id and candidate.plan_id == draft.plan_id
            for candidate in candidate_bundle.candidates
        )
        return WatchCreationPreview(
            draft=draft,
            candidate_bundle=candidate_bundle,
            preselected_room_id=draft.room_id,
            preselected_plan_id=draft.plan_id,
            preselected_still_valid=preselected_still_valid,
            diagnostics=candidate_bundle.diagnostics,
        )

    def create_watch_item_from_preview(
        self,
        *,
        preview: WatchCreationPreview,
        room_id: str,
        plan_id: str,
        scheduler_interval_seconds: int,
        notification_rule_kind: NotificationLeafKind,
        target_price: Decimal | None,
    ) -> WatchItem:
        """依使用者在 editor 中確認的條件建立正式 watch item。"""
        selected_candidate = _find_selected_candidate(
            candidate_bundle=preview.candidate_bundle,
            room_id=room_id,
            plan_id=plan_id,
        )
        adapter = self._site_registry.for_url(preview.draft.seed_url)
        target = adapter.resolve_watch_target(
            draft=preview.draft,
            selection=CandidateSelection(room_id=room_id, plan_id=plan_id),
        )
        notification_rule = RuleLeaf(
            kind=notification_rule_kind,
            target_price=target_price,
        )
        watch_item = WatchItem(
            id=f"watch-{uuid4().hex[:12]}",
            target=target,
            hotel_name=preview.candidate_bundle.hotel_name,
            room_name=selected_candidate.room_name,
            plan_name=selected_candidate.plan_name,
            canonical_url=preview.candidate_bundle.canonical_url,
            notification_rule=notification_rule,
            scheduler_interval_seconds=scheduler_interval_seconds,
        )
        self._watch_item_repository.save(watch_item)
        self._watch_item_repository.save_draft(
            watch_item.id,
            replace(
                preview.draft,
                browser_tab_id=preview.browser_tab_id,
                browser_page_url=preview.browser_page_url,
            ),
        )
        return watch_item

    def delete_watch_item(self, watch_item_id: str) -> None:
        """刪除既有 watch item 與其附屬草稿資料。"""
        self._watch_item_repository.delete(watch_item_id)

    def update_notification_rule(
        self,
        *,
        watch_item_id: str,
        notification_rule_kind: NotificationLeafKind,
        target_price: Decimal | None,
    ) -> WatchItem:
        """更新既有 watch item 的通知條件設定。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise ValueError("watch item not found")

        updated_watch_item = replace(
            watch_item,
            notification_rule=RuleLeaf(
                kind=notification_rule_kind,
                target_price=target_price,
            ),
        )
        self._watch_item_repository.save(updated_watch_item)
        return updated_watch_item


def _find_selected_candidate(
    *,
    candidate_bundle: CandidateBundle,
    room_id: str,
    plan_id: str,
):
    """從候選列表中找出使用者選定的房型方案。"""
    for candidate in candidate_bundle.candidates:
        if candidate.room_id == room_id and candidate.plan_id == plan_id:
            return candidate
    raise ValueError("selected room-plan is not present in candidate list")
