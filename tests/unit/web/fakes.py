from __future__ import annotations

import time
from datetime import date, datetime, timezone
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.application.preview_guard import PreviewAttemptGuard
from app.application.watch_creation_cache import WatchCreationPreviewCache
from app.application.watch_creation_snapshot import WatchCreationSnapshotService
from app.application.watch_editor import WatchCreationPreview, WatchEditorService
from app.application.watch_lifecycle import WatchLifecycleCoordinator
from app.bootstrap.container import AppContainer
from app.domain.entities import NotificationDispatchResult, WatchItem
from app.domain.enums import NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser import ChromeCdpHtmlFetcher, ChromeTabSummary
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteNotificationThrottleStateRepository,
    SqliteRuntimeFragmentQueryRepository,
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeRepository,
    SqliteRuntimeWriteRepository,
    SqliteWatchItemRepository,
)
from app.monitor.runtime import MonitorRuntimeStatus
from app.sites.base import CandidateBundle
from app.sites.ikyu import IkyuAdapter
from app.sites.registry import SiteRegistry

from .builders import _build_preview


class _FakeMonitorRuntime:
    """模擬 app lifespan 用的最小 monitor runtime。"""

    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.check_now_calls: list[str] = []

    async def start(self) -> None:
        """記錄 runtime 已啟動。"""
        self.started += 1

    async def stop(self) -> None:
        """記錄 runtime 已停止。"""
        self.stopped += 1

    def get_status(self) -> MonitorRuntimeStatus:
        """提供首頁與 health endpoint 使用的 runtime 狀態摘要。"""
        return MonitorRuntimeStatus(
            is_running=self.started > self.stopped,
            enabled_watch_count=1,
            registered_watch_count=1,
            inflight_watch_count=0,
            chrome_debuggable=True,
            last_tick_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
            last_watch_sync_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        )

    async def request_check_now(self, watch_item_id: str) -> None:
        """記錄 GUI 是否要求立刻檢查指定 watch。"""
        self.check_now_calls.append(watch_item_id)


def _local_request_headers() -> dict[str, str]:
    """建立通過本機管理介面來源驗證所需的測試 header。"""
    return {
        "origin": "http://127.0.0.1",
        "referer": "http://127.0.0.1/",
    }


class FakeWatchEditorService(WatchEditorService):
    """用固定資料模擬 watch editor 流程。"""

    def __init__(
        self,
        watch_item_repository: SqliteWatchItemRepository,
    ) -> None:
        super().__init__(
            site_registry=SiteRegistry(),
            watch_item_repository=watch_item_repository,
        )
        self._watch_item_repository = watch_item_repository

    def preview_from_seed_url(self, seed_url: str) -> WatchCreationPreview:
        """回傳固定的預覽結果，避免在 web 測試中依賴真站抓取。"""
        return _build_preview(seed_url)

    def mark_existing_watch_for_preview(
        self,
        preview: WatchCreationPreview,
    ) -> WatchCreationPreview:
        """web route 測試不依賴真實 target 比對，直接回傳原 preview。"""
        return preview

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
        """回傳並保存固定的 watch item。"""
        watch_item = WatchItem(
            id="watch-test-1",
            target=WatchTarget(
                site="ikyu",
                hotel_id=preview.draft.hotel_id or "00082173",
                room_id=room_id,
                plan_id=plan_id,
                check_in_date=preview.draft.check_in_date or date(2026, 9, 18),
                check_out_date=preview.draft.check_out_date or date(2026, 9, 19),
                people_count=preview.draft.people_count or 2,
                room_count=preview.draft.room_count or 1,
            ),
            hotel_name="Ocean Hotel",
            room_name="Standard Twin",
            plan_name="Room Only",
            canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            notification_rule=RuleLeaf(
                kind=notification_rule_kind,
                target_price=target_price,
            ),
            scheduler_interval_seconds=scheduler_interval_seconds,
        )
        self._watch_item_repository.save(watch_item)
        return watch_item


class FakeChromeTabPreviewService:
    """提供固定 Chrome 分頁與 preview 的測試替身。"""

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """回傳固定的 `ikyu` Chrome 分頁清單。"""
        return (
            ChromeTabSummary(
                tab_id="0",
                title="Dormy Inn",
                url="https://www.ikyu.com/zh-tw/00082173/?pln=11035620&rm=10191605",
                visibility_state="visible",
                has_focus=True,
            ),
        )

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """依指定分頁回傳固定 preview。"""
        assert tab_id == "0"
        return _build_preview(
            "https://www.ikyu.com/zh-tw/00082173/?pln=11035620&rm=10191605",
            browser_tab_id="0",
            browser_tab_title="Dormy Inn",
        )


class _StaticChromeTabPreviewService:
    """提供固定分頁清單的假 Chrome preview service。"""

    def __init__(self, *, tabs: tuple[ChromeTabSummary, ...]) -> None:
        """保存測試用固定分頁，讓 route-level 測試可精準控制輸入。"""
        self._tabs = tabs

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """回傳預先配置的 Chrome 分頁清單。"""
        return self._tabs

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """依 tab id 回傳對應分頁的最小 preview。"""
        tab = next(tab for tab in self._tabs if tab.tab_id == tab_id)
        return _build_preview(
            tab.url,
            browser_tab_id=tab.tab_id,
            browser_tab_title=tab.title,
        )


class _StaticListTabsFetcher:
    """提供 ChromeTabPreviewService 測試用的固定分頁 fetcher。"""

    def __init__(self, *, tabs: tuple[ChromeTabSummary, ...]) -> None:
        """保存測試用固定分頁清單。"""
        self._tabs = tabs

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """回傳固定分頁清單，不進行任何 CDP 操作。"""
        return self._tabs


class _SlowChromeTabPreviewService:
    """模擬列出 Chrome 分頁時卡住的 preview service。"""

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """刻意睡眠一段時間，驗證 route timeout 會先回應。"""
        time.sleep(0.2)
        return ()

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """此測試不會進入 preview 流程。"""
        raise AssertionError(f"unexpected preview request: {tab_id}")


class _FailingChromeTabPreviewService:
    """模擬 Chrome 分頁列舉直接失敗的 preview service。"""

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """丟出固定錯誤，驗證錯誤頁不會再次列分頁。"""
        raise RuntimeError("Chrome 分頁清單失敗")

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """此測試不會進入 preview 流程。"""
        raise AssertionError(f"unexpected preview request: {tab_id}")


class _PreviewTestAdapter:
    """提供真實 preview service 測試用的最小 adapter。"""

    site_name = "ikyu"

    def match_url(self, url: str) -> bool:
        """判斷測試 adapter 是否支援指定 URL。"""
        return "ikyu.com" in url

    def parse_seed_url(self, url: str) -> SearchDraft:
        """將測試 seed URL 轉成固定 SearchDraft。"""
        return SearchDraft(
            seed_url=url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )

    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        """測試 adapter 不額外改寫 SearchDraft。"""
        return draft

    def fetch_candidates(self, draft: SearchDraft) -> CandidateBundle:
        """依 SearchDraft 回傳固定候選方案。"""
        return _build_preview(draft.seed_url).candidate_bundle

    def build_preview_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        diagnostics=(),
    ) -> tuple[SearchDraft, CandidateBundle]:
        """依 browser page 輸入建立固定 preview 結果。"""
        del html, diagnostics
        preview = _build_preview(page_url, browser_tab_id="0", browser_tab_title="Dormy Inn")
        return preview.draft, preview.candidate_bundle

    def resolve_watch_target(self, draft: SearchDraft, selection) -> WatchTarget:
        """依候選選擇建立測試用 WatchTarget。"""
        return WatchTarget(
            site="ikyu",
            hotel_id=draft.hotel_id or "00082173",
            room_id=selection.room_id,
            plan_id=selection.plan_id,
            check_in_date=draft.check_in_date or date(2026, 9, 18),
            check_out_date=draft.check_out_date or date(2026, 9, 19),
            people_count=draft.people_count or 2,
            room_count=draft.room_count or 1,
        )


def _build_real_preview_registry() -> SiteRegistry:
    """建立測試 real watch editor service 時使用的 registry。"""
    registry = SiteRegistry()
    registry.register(_PreviewTestAdapter())
    return registry


def _build_test_container(tmp_path) -> AppContainer:
    """建立 web 測試用的依賴容器。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    app_settings_repository = SqliteAppSettingsRepository(database)
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    runtime_fragment_repository = SqliteRuntimeFragmentQueryRepository(database)
    notification_throttle_state_repository = SqliteNotificationThrottleStateRepository(
        database
    )
    site_registry = SiteRegistry()
    site_registry.register(IkyuAdapter())
    watch_editor_service = FakeWatchEditorService(watch_repository)
    return AppContainer(
        instance_id="test-instance",
        database=database,
        app_settings_repository=app_settings_repository,
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        runtime_fragment_repository=runtime_fragment_repository,
        notification_throttle_state_repository=notification_throttle_state_repository,
        site_registry=site_registry,
        app_settings_service=AppSettingsService(app_settings_repository),
        notification_channel_test_service=_FakeNotificationChannelTestService(),
        watch_editor_service=watch_editor_service,
        watch_lifecycle_coordinator=WatchLifecycleCoordinator(
            watch_item_repository=watch_repository,
            runtime_write_repository=runtime_write_repository,
            runtime_history_repository=runtime_history_repository,
            monitor_runtime=None,
        ),
        chrome_tab_preview_service=FakeChromeTabPreviewService(),
        chrome_cdp_fetcher=ChromeCdpHtmlFetcher(),
        preview_attempt_guard=PreviewAttemptGuard(),
        watch_creation_preview_cache=WatchCreationPreviewCache(),
        watch_creation_snapshot_service=WatchCreationSnapshotService(
            runtime_write_repository=runtime_write_repository,
        ),
        monitor_runtime=None,
    )


class _FakeNotificationChannelTestService:
    """提供全域通知測試 route 所需的最小替身。"""

    def __init__(self) -> None:
        self.enabled = True

    def send_test_notification(self) -> NotificationDispatchResult:
        """回傳固定的測試通知結果，模擬正式 dispatcher 路徑。"""
        if not self.enabled:
            raise ValueError("目前沒有任何已啟用的通知通道可供測試。")
        return NotificationDispatchResult(
            sent_channels=("desktop",),
            throttled_channels=(),
            failed_channels=(),
            attempted_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        )
