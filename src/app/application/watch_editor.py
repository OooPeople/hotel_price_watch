"""watch editor 的 application service。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.domain import derive_watch_runtime_state
from app.domain.entities import RuntimeStateEvent, WatchItem
from app.domain.enums import NotificationLeafKind, RuntimeStateEventKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.db.repositories import SqliteRuntimeRepository, SqliteWatchItemRepository
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
    existing_watch_id: str | None = None


class WatchEditorService:
    """負責從 seed URL 建立 watch item 的 editor 流程。"""

    MIN_SCHEDULER_INTERVAL_SECONDS = 60

    def __init__(
        self,
        *,
        site_registry: SiteRegistry,
        watch_item_repository: SqliteWatchItemRepository,
        runtime_repository: SqliteRuntimeRepository,
    ) -> None:
        self._site_registry = site_registry
        self._watch_item_repository = watch_item_repository
        self._runtime_repository = runtime_repository

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
        self._validate_scheduler_interval(scheduler_interval_seconds)
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
        existing_watch = self.find_existing_watch_by_target(target)
        if existing_watch is not None:
            raise ValueError("該房型方案已建立 watch")
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

    def enable_watch_item(self, watch_item_id: str) -> WatchItem:
        """啟用既有 watch item，並清除人工停用或暫停狀態。"""
        watch_item = self._get_watch_item_or_raise(watch_item_id)
        updated_watch_item = replace(
            watch_item,
            enabled=True,
            paused_reason=None,
        )
        self._watch_item_repository.save(updated_watch_item)
        self._record_runtime_state_event(
            watch_item_id=watch_item_id,
            event_kind=RuntimeStateEventKind.MANUAL_ENABLE,
            from_watch_item=watch_item,
            to_watch_item=updated_watch_item,
        )
        return updated_watch_item

    def disable_watch_item(self, watch_item_id: str) -> WatchItem:
        """停用既有 watch item，使其不再進入 background monitor。"""
        watch_item = self._get_watch_item_or_raise(watch_item_id)
        updated_watch_item = replace(
            watch_item,
            enabled=False,
            paused_reason="manually_disabled",
        )
        self._watch_item_repository.save(updated_watch_item)
        self._record_runtime_state_event(
            watch_item_id=watch_item_id,
            event_kind=RuntimeStateEventKind.MANUAL_DISABLE,
            from_watch_item=watch_item,
            to_watch_item=updated_watch_item,
        )
        return updated_watch_item

    def pause_watch_item(self, watch_item_id: str) -> WatchItem:
        """暫停既有 watch item，但保留啟用設定以便後續恢復。"""
        watch_item = self._get_watch_item_or_raise(watch_item_id)
        updated_watch_item = replace(
            watch_item,
            enabled=True,
            paused_reason="manually_paused",
        )
        self._watch_item_repository.save(updated_watch_item)
        self._record_runtime_state_event(
            watch_item_id=watch_item_id,
            event_kind=RuntimeStateEventKind.MANUAL_PAUSE,
            from_watch_item=watch_item,
            to_watch_item=updated_watch_item,
        )
        return updated_watch_item

    def resume_watch_item(self, watch_item_id: str) -> WatchItem:
        """恢復先前被暫停或人工停用的 watch item。"""
        watch_item = self._get_watch_item_or_raise(watch_item_id)
        updated_watch_item = replace(
            watch_item,
            enabled=True,
            paused_reason=None,
        )
        self._watch_item_repository.save(updated_watch_item)
        self._record_runtime_state_event(
            watch_item_id=watch_item_id,
            event_kind=RuntimeStateEventKind.MANUAL_RESUME,
            from_watch_item=watch_item,
            to_watch_item=updated_watch_item,
        )
        return updated_watch_item

    def mark_existing_watch_for_preview(
        self,
        preview: WatchCreationPreview,
    ) -> WatchCreationPreview:
        """標記目前預設候選是否已對應到既有 watch。"""
        if (
            preview.preselected_still_valid is False
            or preview.preselected_room_id is None
            or preview.preselected_plan_id is None
        ):
            return preview

        adapter = self._site_registry.for_url(preview.draft.seed_url)
        target = adapter.resolve_watch_target(
            draft=preview.draft,
            selection=CandidateSelection(
                room_id=preview.preselected_room_id,
                plan_id=preview.preselected_plan_id,
            ),
        )
        existing_watch = self.find_existing_watch_by_target(target)
        if existing_watch is None:
            return preview
        return replace(preview, existing_watch_id=existing_watch.id)

    def find_existing_watch_by_target(self, target: WatchTarget) -> WatchItem | None:
        """依 watch target identity 找出是否已有相同 watch。"""
        target_identity = target.identity_key()
        for watch_item in self._watch_item_repository.list_all():
            if watch_item.target.identity_key() == target_identity:
                return watch_item
        return None

    def _get_watch_item_or_raise(self, watch_item_id: str) -> WatchItem:
        """讀取既有 watch item；若不存在則明確拋錯。"""
        watch_item = self._watch_item_repository.get(watch_item_id)
        if watch_item is None:
            raise ValueError("watch item not found")
        return watch_item

    def _validate_scheduler_interval(self, scheduler_interval_seconds: int) -> None:
        """驗證輪詢秒數下限，避免不合理排程直接寫入 DB。"""
        if scheduler_interval_seconds < self.MIN_SCHEDULER_INTERVAL_SECONDS:
            raise ValueError(
                f"輪詢秒數至少需 {self.MIN_SCHEDULER_INTERVAL_SECONDS} 秒"
            )

    def _record_runtime_state_event(
        self,
        *,
        watch_item_id: str,
        event_kind: RuntimeStateEventKind,
        from_watch_item: WatchItem,
        to_watch_item: WatchItem,
    ) -> None:
        """在人工操作後補記正式狀態轉移事件。"""
        latest_snapshot = self._runtime_repository.get_latest_check_snapshot(watch_item_id)
        self._runtime_repository.append_runtime_state_event(
            RuntimeStateEvent(
                watch_item_id=watch_item_id,
                occurred_at=datetime.now(UTC),
                event_kind=event_kind,
                from_state=derive_watch_runtime_state(
                    watch_item=from_watch_item,
                    latest_snapshot=latest_snapshot,
                ),
                to_state=derive_watch_runtime_state(
                    watch_item=to_watch_item,
                    latest_snapshot=latest_snapshot,
                ),
            )
        )


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
