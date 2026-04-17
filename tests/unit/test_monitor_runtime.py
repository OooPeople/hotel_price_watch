from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    CheckEvent,
    CheckResult,
    NotificationDecision,
    NotificationState,
    PriceSnapshot,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationDeliveryStatus,
    NotificationEventKind,
    NotificationLeafKind,
    RuntimeStateEventKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser.chrome_cdp_fetcher import ChromeTabCapture, ChromeTabSummary
from app.infrastructure.browser.page_strategy import (
    BrowserBlockedPageError,
    BrowserBlockingOutcome,
)
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.monitor import runtime as runtime_module
from app.monitor.runtime import (
    ChromeDrivenMonitorRuntime,
    _map_runtime_exception_to_error_code_typed,
)
from app.notifiers.base import Notifier
from app.notifiers.models import NotificationMessage
from app.sites.base import CandidateSelection, SiteAdapter
from app.sites.ikyu.page_guards import IkyuBlockedPageError
from app.sites.registry import SiteRegistry


class _FakeChromeFetcher:
    """?? monitor runtime 皜祈岫?函??箏? Chrome capture??"""

    def __init__(self) -> None:
        """記錄啟動恢復分頁時的輸入，方便驗證 runtime 行為。"""
        self.ensure_calls: list[tuple[str, str | None, str | None, tuple[str, ...]]] = []

    def is_debuggable_chrome_running(self) -> bool:
        """回傳測試用的可附著狀態。"""
        return True

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy=None,
    ) -> ChromeTabSummary:
        """模擬 runtime 啟動時重建或找回既有 watch 分頁。"""
        del page_strategy
        self.ensure_calls.append(
            (
                expected_url,
                fallback_url,
                preferred_tab_id,
                excluded_tab_ids,
            )
        )
        return ChromeTabSummary(
            tab_id=preferred_tab_id or f"restored-tab-{len(self.ensure_calls)}",
            title="Dormy Inn",
            url=fallback_url or expected_url,
            visibility_state="visible",
            has_focus=True,
        )

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """??箏???????HTML嚗芋?砍?啣?????"""
        del fallback_url, preferred_tab_id, page_strategy
        return ChromeTabCapture(
            tab=ChromeTabSummary(
                tab_id="tab-1",
                title="Dormy Inn",
                url=expected_url,
                visibility_state="visible",
                has_focus=True,
            ),
            html="<html><body>browser snapshot</body></html>",
        )


class _ThrottledChromeFetcher(_FakeChromeFetcher):
    """??撣嗆??蝭瘚??? Chrome capture??"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """? hidden / not_focused ????閬?"""
        del fallback_url, preferred_tab_id, page_strategy
        return ChromeTabCapture(
            tab=ChromeTabSummary(
                tab_id="tab-1",
                title="Dormy Inn",
                url=expected_url,
                visibility_state="hidden",
                has_focus=False,
            ),
            html="<html><body>browser snapshot</body></html>",
        )


class _DiscardedChromeFetcher(_FakeChromeFetcher):
    """???曇◤?汗?其?璉???Chrome capture??"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """?撣嗆? `was_discarded` 閮?????閬?"""
        del fallback_url, preferred_tab_id, page_strategy
        return ChromeTabCapture(
            tab=ChromeTabSummary(
                tab_id="tab-1",
                title="Dormy Inn",
                url=expected_url,
                visibility_state="visible",
                has_focus=True,
                was_discarded=True,
            ),
            html="<html><body>browser snapshot</body></html>",
        )


class _RecordingChromeFetcher(_FakeChromeFetcher):
    """閮? runtime 閬???preferred tab ??fallback URL嚗?霅?watch-to-tab 撠???"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None, str | None]] = []

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """閮? runtime 撖阡??喳????蝝Ｕ?"""
        del page_strategy
        self.calls.append((expected_url, fallback_url, preferred_tab_id))
        return super().refresh_capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
        )


class _ForbiddenChromeFetcher(_FakeChromeFetcher):
    """模擬 Chrome 分頁在刷新時被站方以 403 阻擋。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """直接拋出含 403 訊號的例外，驗證 runtime 會進入暫停流程。"""
        del expected_url, fallback_url, preferred_tab_id, page_strategy
        raise IkyuBlockedPageError("ikyu 已回傳阻擋頁面。")


class _TimeoutChromeFetcher(_FakeChromeFetcher):
    """模擬專用 Chrome 分頁刷新逾時。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """直接拋出逾時錯誤，驗證 runtime 會映射成 network_timeout。"""
        del expected_url, fallback_url, preferred_tab_id, page_strategy
        raise TimeoutError("refresh timed out")


class _BlockingChromeFetcher(_FakeChromeFetcher):
    """模擬長時間刷新，驗證同一 watch 的檢查會共用同一個 inflight task。"""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """在外部釋放前暫停刷新流程，模擬已在進行中的背景檢查。"""
        del page_strategy
        self.call_count += 1
        self.started.set()
        self.release.wait(timeout=2)
        return super().refresh_capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
        )


class _PausingChromeFetcher(_FakeChromeFetcher):
    """在刷新途中暫停 watch，模擬使用者於 in-flight check 期間操作控制面。"""

    def __init__(
        self,
        *,
        watch_repository: SqliteWatchItemRepository,
        watch_item_id: str,
    ) -> None:
        super().__init__()
        self._watch_repository = watch_repository
        self._watch_item_id = watch_item_id

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """先暫停 watch，再回傳正常 capture，驗證 runtime 會丟棄結果。"""
        del page_strategy
        watch_item = self._watch_repository.get(self._watch_item_id)
        assert watch_item is not None
        self._watch_repository.save(
            replace(watch_item, enabled=True, paused_reason="manually_paused")
        )
        return super().refresh_capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
        )


class _PausingOnGetWatchRepository:
    """在第 N 次讀取 watch 時暫停它，模擬後段 control state 變更。"""

    def __init__(
        self,
        repository: SqliteWatchItemRepository,
        *,
        watch_item_id: str,
        pause_on_get_call: int,
    ) -> None:
        """建立會代理原 repository 的測試替身。"""
        self._repository = repository
        self._watch_item_id = watch_item_id
        self._pause_on_get_call = pause_on_get_call
        self.get_call_count = 0

    def __getattr__(self, name: str):
        """未覆寫的方法直接委派給原 repository。"""
        return getattr(self._repository, name)

    def get(self, watch_item_id: str) -> WatchItem | None:
        """在指定讀取次數先暫停 watch，再回傳目前狀態。"""
        self.get_call_count += 1
        if watch_item_id == self._watch_item_id and (
            self.get_call_count == self._pause_on_get_call
        ):
            watch_item = self._repository.get(watch_item_id)
            assert watch_item is not None
            self._repository.save(
                replace(watch_item, enabled=True, paused_reason="manually_paused")
            )
        return self._repository.get(watch_item_id)


class _FailingRestoreChromeFetcher(_FakeChromeFetcher):
    """模擬啟動恢復階段某個分頁建立失敗。"""

    def __init__(self) -> None:
        super().__init__()
        self.failed_once = False

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy=None,
    ) -> ChromeTabSummary:
        """第一次恢復失敗，後續仍允許其它 watch 繼續恢復。"""
        del page_strategy
        self.ensure_calls.append(
            (
                expected_url,
                fallback_url,
                preferred_tab_id,
                excluded_tab_ids,
            )
        )
        if not self.failed_once:
            self.failed_once = True
            raise RuntimeError("restore failed")
        return super().ensure_tab_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
        )


class _RecordingNotifier:
    """閮?撖阡??閮?批捆?陛??notifier??"""

    channel_name = "desktop"

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        """靽? dispatch ?????荔?靘葫閰阡?霅?"""
        self.messages.append(message)


class _FailingNotifier:
    """模擬單一通知通道失敗，驗證 runtime 不會因此中止。"""

    def __init__(self, channel_name: str, message: str = "forced failure") -> None:
        self.channel_name = channel_name
        self._message = message

    def send(self, message: NotificationMessage) -> None:
        """固定拋出錯誤，模擬外部通知通道失敗。"""
        del message
        raise RuntimeError(self._message)


class _PausingNotifier(_RecordingNotifier):
    """送出通知時暫停 watch，模擬 dispatch 期間的手動控制命令。"""

    def __init__(
        self,
        *,
        watch_repository: SqliteWatchItemRepository,
        watch_item_id: str,
    ) -> None:
        """建立會在 send 時改變 control state 的 notifier。"""
        super().__init__()
        self._watch_repository = watch_repository
        self._watch_item_id = watch_item_id

    def send(self, message: NotificationMessage) -> None:
        """先記錄通知，再暫停 watch。"""
        super().send(message)
        watch_item = self._watch_repository.get(self._watch_item_id)
        assert watch_item is not None
        self._watch_repository.save(
            replace(watch_item, enabled=True, paused_reason="manually_paused")
        )


class _CountingNotifierFactory:
    """記錄 notifier factory 呼叫次數，驗證 dispatcher 快取是否生效。"""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(
        self,
        settings: NotificationChannelSettings,
    ) -> tuple[Notifier, ...]:
        """依設定建立最小 notifier 集合。"""
        self.call_count += 1
        if not settings.desktop_enabled:
            return ()
        return (_RecordingNotifier(),)


class _FakeRuntimeAdapter(SiteAdapter):
    """?? Chrome-driven runtime 皜祈岫?函??撠?暺?adapter??"""

    site_name = "ikyu"

    def match_url(self, url: str) -> bool:
        """?亙??桀?皜祈岫?函? `ikyu` URL??"""
        return "ikyu.com" in url

    def parse_seed_url(self, url: str) -> SearchDraft:
        """??seed URL 頧??箏??亥岷?阮??"""
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
        """皜祈岫 adapter 銝憭??渲?蝔踴?"""
        return draft

    def fetch_candidates(self, draft: SearchDraft):
        """?祆葫閰虫?雿輻??亥岷瘚???"""
        raise NotImplementedError

    def build_preview_from_browser_page(self, *, page_url: str, html: str, diagnostics=()):
        """?祆葫閰虫?雿輻 preview 瘚???"""
        raise NotImplementedError

    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        """??browser HTML ?湔撱箇??箏??寞敹怎??"""
        return PriceSnapshot(
            display_price_text="JPY 22990",
            normalized_price_amount=Decimal("22990"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        )

    def resolve_watch_target(
        self,
        draft: SearchDraft,
        selection: CandidateSelection,
    ) -> WatchTarget:
        """?祆葫閰虫?雿輻 watch editor 撱箇?瘚???"""
        del draft, selection
        raise NotImplementedError


class _AmountByPlanRuntimeAdapter(_FakeRuntimeAdapter):
    """依 plan_id 回傳不同價格，方便驗證多筆 watch 的背景檢查結果。"""

    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        """依不同 plan_id 產生不同 snapshot，確認 runtime 不會互相污染。"""
        del page_url, html
        amount_by_plan = {
            "11035620": Decimal("22990"),
            "11035621": Decimal("24800"),
        }
        amount = amount_by_plan.get(target.plan_id, Decimal("20000"))
        return PriceSnapshot(
            display_price_text=f"JPY {amount}",
            normalized_price_amount=amount,
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        )


def test_runtime_run_watch_check_once_persists_snapshot_and_history(tmp_path) -> None:
    """?格活 runtime 瑼Ｘ?神?交??唳?閬?隞嗉??寞甇瑕??"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)
    app_settings_service.settings_repository.save_notification_channel_settings(
        NotificationChannelSettings(
            desktop_enabled=False,
            ntfy_enabled=False,
            discord_enabled=False,
        )
    )

    watch_item = WatchItem(
        id="watch-runtime-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        SearchDraft(
            seed_url=watch_item.canonical_url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.availability is Availability.AVAILABLE
    assert latest_snapshot.normalized_price_amount == Decimal("22990")
    assert latest_snapshot.currency == "JPY"

    check_events = runtime_repository.list_check_events(watch_item.id)
    assert len(check_events) == 1
    assert check_events[0].event_kinds == ("checked",)

    price_history = runtime_repository.list_price_history(watch_item.id)
    assert len(price_history) == 1
    assert price_history[0].normalized_price_amount == Decimal("22990")
    assert price_history[0].source_kind is SourceKind.BROWSER


def test_runtime_dispatches_notification_and_records_sent_status(tmp_path) -> None:
    """?賭葉?閬???runtime ??銝行?蝯?撖怠瑼Ｘ甇瑕??"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = WatchItem(
        id="watch-runtime-notify",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("23000"),
        ),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        SearchDraft(
            seed_url=watch_item.canonical_url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("25000"),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier = _RecordingNotifier()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert len(notifier.messages) == 1
    check_events = runtime_repository.list_check_events(watch_item.id)
    assert len(check_events) == 1
    assert check_events[0].notification_status.value == "sent"
    assert check_events[0].sent_channels == ("desktop",)


def test_runtime_discards_result_when_watch_is_paused_midflight(tmp_path) -> None:
    """in-flight 檢查期間若 watch 被暫停，不應寫入新結果或發送通知。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = WatchItem(
        id="watch-runtime-midflight-pause",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("23000"),
        ),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("25000"),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier = _RecordingNotifier()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_PausingChromeFetcher(
            watch_repository=watch_repository,
            watch_item_id=watch_item.id,
        ),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert notifier.messages == []
    assert runtime_repository.list_check_events(watch_item.id) == []
    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("25000")
    paused_watch = watch_repository.get(watch_item.id)
    assert paused_watch is not None
    assert paused_watch.paused_reason == "manually_paused"


def test_runtime_skips_notification_when_watch_pauses_before_dispatch(tmp_path) -> None:
    """通知前若 control state 已改變，本次檢查不應通知或持久化結果。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = replace(
        _build_runtime_watch_item("watch-runtime-pause-before-dispatch"),
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("23000"),
        ),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("25000"),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier = _RecordingNotifier()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=_PausingOnGetWatchRepository(
            watch_repository,
            watch_item_id=watch_item.id,
            pause_on_get_call=3,
        ),
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert notifier.messages == []
    assert runtime_repository.list_check_events(watch_item.id) == []
    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("25000")
    paused_watch = watch_repository.get(watch_item.id)
    assert paused_watch is not None
    assert paused_watch.paused_reason == "manually_paused"


def test_runtime_skips_persist_when_watch_pauses_during_dispatch(tmp_path) -> None:
    """dispatch 期間若 watch 被暫停，本次結果不應再提交到 runtime history。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = replace(
        _build_runtime_watch_item("watch-runtime-pause-during-dispatch"),
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("23000"),
        ),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("25000"),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier = _PausingNotifier(
        watch_repository=watch_repository,
        watch_item_id=watch_item.id,
    )
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert len(notifier.messages) == 1
    assert runtime_repository.list_check_events(watch_item.id) == []
    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("25000")
    paused_watch = watch_repository.get(watch_item.id)
    assert paused_watch is not None
    assert paused_watch.paused_reason == "manually_paused"


def test_runtime_notification_throttle_persists_across_runtime_restart(tmp_path) -> None:
    """同一通道冷卻應跨 runtime 重啟保留，不可因 app 重啟而重置。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-persistent-throttle")
    watch_repository.save(watch_item)
    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier = _RecordingNotifier()
    check_result = CheckResult(
        checked_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        current_snapshot=PriceSnapshot(
            display_price_text="JPY 22990",
            normalized_price_amount=Decimal("22990"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        ),
        previous_snapshot=PriceSnapshot(
            display_price_text="JPY 25000",
            normalized_price_amount=Decimal("25000"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        ),
        price_changed=True,
        availability_changed=False,
        price_dropped=True,
        became_available=False,
        parse_failed=False,
    )
    decision = NotificationDecision(
        event_kinds=(NotificationEventKind.PRICE_DROP,),
        next_state=NotificationState(watch_item_id=watch_item.id),
    )

    runtime_one = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )
    first_result = runtime_one._dispatch_notification(
        watch_item,
        check_result,
        decision,
        datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )
    assert first_result is not None
    assert first_result.sent_channels == ("desktop",)
    assert len(notifier.messages) == 1

    runtime_two = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )
    second_result = runtime_two._dispatch_notification(
        watch_item,
        check_result,
        decision,
        datetime(2026, 4, 13, 10, 0, 30, tzinfo=UTC),
    )
    assert second_result is not None
    assert second_result.sent_channels == ()
    assert second_result.throttled_channels == ("desktop",)
    assert len(notifier.messages) == 1


def test_runtime_records_partial_notification_failure_without_aborting_check(tmp_path) -> None:
    """單一通知通道失敗時，runtime 仍應寫入檢查結果並保留其他成功通道。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-partial-notify")
    watch_item = replace(
        watch_item,
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("23000"),
        ),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("25000"),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    successful_notifier = _RecordingNotifier()
    failing_notifier = _FailingNotifier(channel_name="discord", message="discord boom")
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: (successful_notifier, failing_notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert len(successful_notifier.messages) == 1
    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("22990")

    check_events = runtime_repository.list_check_events(watch_item.id)
    assert len(check_events) == 1
    assert check_events[0].notification_status.value == "partial"
    assert check_events[0].sent_channels == ("desktop",)
    assert check_events[0].failed_channels == ("discord",)


def test_runtime_does_not_treat_unknown_to_available_as_became_available(tmp_path) -> None:
    """中間若只有 unknown 雜訊，不應把 available 判成恢復可訂。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-no-false-recovery")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))
    runtime_repository.append_check_event(
        CheckEvent(
            watch_item_id=watch_item.id,
            checked_at=datetime(2026, 4, 14, 15, 30, tzinfo=UTC),
            availability=Availability.AVAILABLE,
            event_kinds=("checked",),
            normalized_price_amount=Decimal("18434"),
            currency="JPY",
        )
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("18434"),
            checked_at=datetime(2026, 4, 14, 16, 12, tzinfo=UTC),
            last_error_code=CheckErrorCode.NETWORK_ERROR.value,
        )
    )
    runtime_repository.append_check_event(
        CheckEvent(
            watch_item_id=watch_item.id,
            checked_at=datetime(2026, 4, 14, 16, 12, tzinfo=UTC),
            availability=Availability.UNKNOWN,
            event_kinds=("price_changed",),
            error_code=CheckErrorCode.NETWORK_ERROR.value,
            notification_status=NotificationDeliveryStatus.NOT_REQUESTED,
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier = _RecordingNotifier()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_event = runtime_repository.list_check_events(watch_item.id)[-1]
    assert NotificationEventKind.BECAME_AVAILABLE.value not in latest_event.event_kinds
    assert latest_event.notification_status.value == "not_requested"
    assert notifier.messages == []


def test_runtime_network_timeout_backoff_grows_across_consecutive_failures(
    tmp_path,
    monkeypatch,
) -> None:
    """連續 timeout 時，退避時間應依失敗次數遞增。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-timeout-backoff")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))

    checked_times = iter(
        (
            datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            datetime(2026, 4, 14, 10, 6, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(runtime_module, "_utcnow", lambda: next(checked_times))

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_TimeoutChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))
    first_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert first_snapshot is not None
    assert first_snapshot.consecutive_failures == 1
    assert first_snapshot.last_error_code == CheckErrorCode.NETWORK_TIMEOUT.value
    assert first_snapshot.backoff_until == datetime(2026, 4, 14, 10, 5, tzinfo=UTC)

    asyncio.run(runtime.run_watch_check_once(watch_item.id))
    second_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert second_snapshot is not None
    assert second_snapshot.consecutive_failures == 2
    assert second_snapshot.backoff_until == datetime(2026, 4, 14, 10, 16, tzinfo=UTC)


def test_runtime_success_after_backoff_clears_timeout_failure_state(tmp_path, monkeypatch) -> None:
    """timeout 退避過後若成功，應清掉 backoff 與 failure streak。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-timeout-recovery")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("18434"),
            availability=Availability.UNKNOWN,
            checked_at=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            consecutive_failures=2,
            last_error_code=CheckErrorCode.NETWORK_TIMEOUT.value,
            backoff_until=datetime(2026, 4, 14, 10, 16, tzinfo=UTC),
        )
    )
    runtime_repository.save_notification_state(
        _build_notification_state(
            watch_item_id=watch_item.id,
            consecutive_failures=2,
            consecutive_parse_failures=0,
        )
    )

    monkeypatch.setattr(
        runtime_module,
        "_utcnow",
        lambda: datetime(2026, 4, 14, 10, 17, tzinfo=UTC),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.consecutive_failures == 0
    assert latest_snapshot.backoff_until is None
    assert latest_snapshot.last_error_code is None

    notification_state = runtime_repository.get_notification_state(watch_item.id)
    assert notification_state is not None
    assert notification_state.consecutive_failures == 0


def test_runtime_records_possible_throttling_debug_artifact(tmp_path) -> None:
    """?蝭瘚???靽???runtime debug artifact??"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = WatchItem(
        id="watch-runtime-throttle",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        SearchDraft(
            seed_url=watch_item.canonical_url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_ThrottledChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    debug_artifacts = runtime_repository.list_debug_artifacts(watch_item.id)
    assert len(debug_artifacts) == 1
    assert debug_artifacts[0].reason == "possible_throttling"
    assert debug_artifacts[0].source_url == watch_item.canonical_url


def test_runtime_records_discarded_page_debug_artifact(tmp_path) -> None:
    """?亙??鋡怎汗?其?璉?runtime ??摮???debug artifact??"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = WatchItem(
        id="watch-runtime-discarded",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        SearchDraft(
            seed_url=watch_item.canonical_url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_DiscardedChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    debug_artifacts = runtime_repository.list_debug_artifacts(watch_item.id)
    assert len(debug_artifacts) == 1
    assert debug_artifacts[0].reason == "page_was_discarded"


def test_runtime_prefers_saved_browser_tab_hint(tmp_path) -> None:
    """runtime 頛芾岷???芸?瘝輻撱箇? watch ??摮? Chrome ??蝺揣??"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = WatchItem(
        id="watch-runtime-tab-hint",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        SearchDraft(
            seed_url=watch_item.canonical_url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
            browser_tab_id="target-keep-me",
            browser_page_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        ),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    fetcher = _RecordingChromeFetcher()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert fetcher.calls == [
        (
            watch_item.canonical_url,
            "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            "target-keep-me",
        )
    ]


def test_runtime_pauses_watch_when_chrome_refresh_hits_403(tmp_path) -> None:
    """Chrome 刷新若命中 403，runtime 應暫停該 watch 並記錄錯誤摘要。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-403")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_ForbiddenChromeFetcher(),
        app_settings_service=app_settings_service,
    )
    runtime._scheduler.register_watch(
        watch_item_id=watch_item.id,
        interval_seconds=watch_item.scheduler_interval_seconds,
        now=datetime.now(UTC),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    updated_watch_item = watch_repository.get(watch_item.id)
    assert updated_watch_item is not None
    assert updated_watch_item.enabled is True
    assert updated_watch_item.paused_reason == "http_403"

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.last_error_code == "http_403"
    assert latest_snapshot.consecutive_failures == 1

    debug_artifacts = runtime_repository.list_debug_artifacts(watch_item.id)
    assert len(debug_artifacts) == 1
    assert debug_artifacts[0].reason == "http_403"

    runtime_state_events = runtime_repository.list_runtime_state_events(watch_item.id)
    assert len(runtime_state_events) == 1
    assert runtime_state_events[0].event_kind is RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING
    assert runtime_state_events[0].detail_text is not None
    assert "kind=forbidden" in runtime_state_events[0].detail_text
    assert runtime._scheduler.list_registered_ids() == ()

    price_history = runtime_repository.list_price_history(watch_item.id)
    assert price_history == []


def test_runtime_records_timeout_as_network_timeout(tmp_path) -> None:
    """Chrome 刷新逾時時，runtime 應記錄為 network_timeout。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-timeout")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_TimeoutChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.last_error_code == "network_timeout"


def test_runtime_recovers_cleanly_after_manual_resume_from_403_pause(tmp_path) -> None:
    """403 暫停後若手動恢復並成功檢查，應清掉錯誤狀態並保留合理歷史。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-403-resume")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())

    import asyncio

    blocked_runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_ForbiddenChromeFetcher(),
        app_settings_service=app_settings_service,
    )
    asyncio.run(blocked_runtime.run_watch_check_once(watch_item.id))

    paused_watch = watch_repository.get(watch_item.id)
    assert paused_watch is not None
    assert paused_watch.enabled is True
    assert paused_watch.paused_reason == "http_403"

    resumed_watch = replace(paused_watch, enabled=True, paused_reason=None)
    watch_repository.save(resumed_watch)

    recovered_runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )
    asyncio.run(recovered_runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.availability is Availability.AVAILABLE
    assert latest_snapshot.last_error_code is None
    assert latest_snapshot.consecutive_failures == 0
    assert latest_snapshot.backoff_until is None

    updated_watch = watch_repository.get(watch_item.id)
    assert updated_watch is not None
    assert updated_watch.enabled is True
    assert updated_watch.paused_reason is None

    check_events = runtime_repository.list_check_events(watch_item.id)
    assert len(check_events) == 2
    assert check_events[0].error_code == "http_403"
    assert check_events[1].availability is Availability.AVAILABLE
    assert NotificationEventKind.BECAME_AVAILABLE.value not in check_events[1].event_kinds

    runtime_state_events = runtime_repository.list_runtime_state_events(watch_item.id)
    event_kinds = tuple(event.event_kind for event in runtime_state_events)
    assert RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING in event_kinds
    assert RuntimeStateEventKind.RECOVERED_AFTER_SUCCESS in event_kinds


def test_runtime_error_mapping_no_longer_depends_on_message_fragments() -> None:
    """錯誤映射應以型別為主，不再因訊息片段誤判。"""
    assert (
        _map_runtime_exception_to_error_code_typed(IkyuBlockedPageError("blocked"))
        is CheckErrorCode.FORBIDDEN_403
    )
    assert (
        _map_runtime_exception_to_error_code_typed(TimeoutError("timeout"))
        is CheckErrorCode.NETWORK_TIMEOUT
    )
    assert (
        _map_runtime_exception_to_error_code_typed(RuntimeError("room 403-B"))
        is CheckErrorCode.NETWORK_ERROR
    )


def test_runtime_maps_generic_rate_limit_blocking_outcome() -> None:
    """generic browser blocking outcome 應能表達非 403 的站方節流。"""
    error = BrowserBlockedPageError(
        outcome=BrowserBlockingOutcome(
            kind="rate_limited",
            message="rate limited by site",
            reason="site_rate_limit",
        )
    )

    assert (
        _map_runtime_exception_to_error_code_typed(error)
        is CheckErrorCode.RATE_LIMITED_429
    )


def test_runtime_success_resets_previous_failure_and_degraded_state(tmp_path) -> None:
    """前次失敗後若本次成功，runtime 應清掉 failure/backoff/degraded 狀態。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-recovery")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("26000"),
            consecutive_failures=3,
            last_error_code="parse_failed",
        )
    )
    runtime_repository.save_notification_state(
        _build_notification_state(
            watch_item_id=watch_item.id,
            consecutive_failures=3,
            consecutive_parse_failures=3,
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.last_error_code is None
    assert latest_snapshot.consecutive_failures == 0
    assert latest_snapshot.backoff_until is None
    assert latest_snapshot.is_degraded is False

    notification_state = runtime_repository.get_notification_state(watch_item.id)
    assert notification_state is not None
    assert notification_state.consecutive_failures == 0
    assert notification_state.consecutive_parse_failures == 0
    assert notification_state.degraded_notified_at is None


def test_runtime_start_registers_only_active_watches_and_stop_clears_scheduler(
    tmp_path,
) -> None:
    """runtime 啟停時只同步 active watch，且停止後會清空 scheduler 狀態。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    active_watch = _build_runtime_watch_item("watch-runtime-active")
    disabled_watch = _build_runtime_watch_item("watch-runtime-disabled")
    disabled_watch = replace(disabled_watch, enabled=False)
    paused_watch = _build_runtime_watch_item("watch-runtime-paused")
    paused_watch = replace(paused_watch, paused_reason="http_403")
    for watch_item in (active_watch, disabled_watch, paused_watch):
        watch_repository.save(watch_item)

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        tick_seconds=60,
        restore_delay_seconds=0,
    )

    async def _exercise_runtime() -> None:
        """在同一個 event loop 內驗證啟停與 scheduler 狀態。"""
        await runtime.start()
        status = runtime.get_status()
        assert status.is_running is True
        assert status.enabled_watch_count == 1
        assert status.registered_watch_count == 1
        assert runtime._scheduler.list_registered_ids() == (active_watch.id,)

        await runtime.stop()
        stopped_status = runtime.get_status()
        assert stopped_status.is_running is False
        assert stopped_status.registered_watch_count == 0
        assert runtime._scheduler.list_registered_ids() == ()

    import asyncio

    asyncio.run(_exercise_runtime())


def test_runtime_start_restores_only_enabled_and_unpaused_watch_tabs(tmp_path) -> None:
    """runtime 啟動時只應低速恢復 enabled 且未 paused 的 watch 分頁。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    active_watch = _build_runtime_watch_item("watch-runtime-restore-active")
    disabled_watch = replace(
        _build_runtime_watch_item("watch-runtime-restore-disabled"),
        enabled=False,
    )
    paused_watch = replace(
        _build_runtime_watch_item("watch-runtime-restore-paused"),
        paused_reason="manually_paused",
    )
    for watch_item in (active_watch, disabled_watch, paused_watch):
        watch_repository.save(watch_item)
        watch_repository.save_draft(
            watch_item.id,
            _build_runtime_draft(watch_item.canonical_url),
        )

    fetcher = _FakeChromeFetcher()
    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
        tick_seconds=60,
        restore_delay_seconds=0,
    )

    import asyncio

    async def _exercise_runtime() -> None:
        await runtime.start()
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    assert fetcher.ensure_calls == [
        (
            active_watch.canonical_url,
            active_watch.canonical_url,
            None,
            (),
        )
    ]


def test_runtime_start_continues_when_single_tab_restore_fails(tmp_path) -> None:
    """啟動恢復若單一 watch 分頁失敗，不應中止整體 runtime 啟動。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    first_watch = _build_runtime_watch_item("watch-runtime-restore-first")
    second_watch = replace(
        _build_runtime_watch_item("watch-runtime-restore-second"),
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191606",
            plan_id="11035621",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035621"
            "&ppc=2&rc=1&rm=10191606&si=1&st=1"
        ),
    )
    for watch_item in (first_watch, second_watch):
        watch_repository.save(watch_item)
        watch_repository.save_draft(
            watch_item.id,
            _build_runtime_draft(watch_item.canonical_url),
        )

    fetcher = _FailingRestoreChromeFetcher()
    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
        tick_seconds=60,
        restore_delay_seconds=0,
    )

    import asyncio

    async def _exercise_runtime() -> None:
        await runtime.start()
        status = runtime.get_status()
        assert status.is_running is True
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    assert len(fetcher.ensure_calls) >= 2
    assert any(call[0] == second_watch.canonical_url for call in fetcher.ensure_calls)


def test_runtime_start_excludes_already_restored_tabs_from_later_watches(tmp_path) -> None:
    """多筆 watch 啟動恢復時，後續 watch 不應重用前一筆已佔用的 tab。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    first_watch = _build_runtime_watch_item("watch-runtime-restore-exclude-first")
    second_watch = replace(
        _build_runtime_watch_item("watch-runtime-restore-exclude-second"),
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191606",
            plan_id="11035621",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035621"
            "&ppc=2&rc=1&rm=10191606&si=1&st=1"
        ),
    )
    for watch_item in (first_watch, second_watch):
        watch_repository.save(watch_item)
        watch_repository.save_draft(
            watch_item.id,
            _build_runtime_draft(watch_item.canonical_url),
        )

    fetcher = _FakeChromeFetcher()
    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
        tick_seconds=60,
        restore_delay_seconds=0,
    )

    import asyncio

    async def _exercise_runtime() -> None:
        await runtime.start()
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    assert len(fetcher.ensure_calls) == 2
    assert fetcher.ensure_calls[0][3] == ()
    assert fetcher.ensure_calls[1][3] == ("restored-tab-1",)


def test_runtime_sync_removes_watch_after_pause_or_disable(tmp_path) -> None:
    """watch 若被停用或標記 paused，下一次同步時應從 scheduler 移除。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-resync")
    watch_repository.save(watch_item)

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime._sync_watch_definitions(now=datetime.now(UTC)))
    assert runtime._scheduler.list_registered_ids() == (watch_item.id,)

    paused_watch = replace(watch_item, paused_reason="http_403")
    watch_repository.save(paused_watch)

    asyncio.run(runtime._sync_watch_definitions(now=datetime.now(UTC)))
    assert runtime._scheduler.list_registered_ids() == ()


def test_runtime_loop_processes_multiple_active_watches(tmp_path) -> None:
    """background loop 應能在同一輪運作內處理多筆 active watch。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_a = _build_runtime_watch_item("watch-runtime-multi-a")
    watch_b = replace(
        _build_runtime_watch_item("watch-runtime-multi-b"),
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191606",
            plan_id="11035621",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        room_name="double room",
        plan_name="breakfast; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035621"
            "&ppc=2&rc=1&rm=10191606&si=1&st=1"
        ),
    )
    for watch_item in (watch_a, watch_b):
        watch_repository.save(watch_item)
        watch_repository.save_draft(
            watch_item.id,
            _build_runtime_draft(watch_item.canonical_url),
        )

    site_registry = SiteRegistry()
    site_registry.register(_AmountByPlanRuntimeAdapter())
    fetcher = _RecordingChromeFetcher()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
        tick_seconds=0.01,
        max_workers=2,
        restore_delay_seconds=0,
    )

    async def _exercise_runtime() -> None:
        """啟動 background loop，等待多筆 watch 都被處理。"""
        await runtime.start()
        try:
            for _ in range(50):
                if (
                    runtime_repository.get_latest_check_snapshot(watch_a.id) is not None
                    and runtime_repository.get_latest_check_snapshot(watch_b.id) is not None
                ):
                    break
                await asyncio.sleep(0.01)
        finally:
            await runtime.stop()

    import asyncio

    asyncio.run(_exercise_runtime())

    latest_a = runtime_repository.get_latest_check_snapshot(watch_a.id)
    latest_b = runtime_repository.get_latest_check_snapshot(watch_b.id)
    assert latest_a is not None
    assert latest_b is not None
    assert latest_a.normalized_price_amount == Decimal("22990")
    assert latest_b.normalized_price_amount == Decimal("24800")
    assert len(fetcher.calls) >= 2


def test_runtime_loop_syncs_watch_added_after_start(tmp_path) -> None:
    """runtime 啟動後新增的 watch，應在後續 tick 被同步並完成檢查。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        tick_seconds=0.01,
        max_workers=1,
        restore_delay_seconds=0,
    )

    async def _exercise_runtime() -> None:
        """先啟動空的 runtime，再動態加入 watch 驗證後續 sync。"""
        await runtime.start()
        try:
            await asyncio.sleep(0.05)
            watch_item = _build_runtime_watch_item("watch-runtime-added-later")
            watch_repository.save(watch_item)
            watch_repository.save_draft(
                watch_item.id,
                _build_runtime_draft(watch_item.canonical_url),
            )
            deadline = asyncio.get_running_loop().time() + 1.0
            while (
                runtime_repository.get_latest_check_snapshot(watch_item.id) is None
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)
        finally:
            await runtime.stop()

    import asyncio

    asyncio.run(_exercise_runtime())

    latest_snapshot = runtime_repository.get_latest_check_snapshot(
        "watch-runtime-added-later"
    )
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("22990")


def test_runtime_wakeup_rescan_reschedules_existing_watch(tmp_path) -> None:
    """睡眠恢復後若不在 backoff 期，既有 watch 應被立即補掃。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-wakeup")
    watch_repository.save(watch_item)
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("22990"),
            checked_at=datetime(2026, 4, 13, 9, 50, tzinfo=UTC),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    initial_now = datetime(2026, 4, 13, 10, 0, tzinfo=UTC)
    resumed_at = datetime(2026, 4, 13, 12, 30, tzinfo=UTC)

    asyncio.run(runtime._sync_watch_definitions(now=initial_now))
    before_schedule = runtime._scheduler.get_schedule(watch_item.id)
    assert before_schedule is not None
    assert before_schedule.next_run_at >= initial_now

    asyncio.run(
        runtime._sync_watch_definitions(
            now=resumed_at,
            resumed_after_sleep=True,
        )
    )
    after_schedule = runtime._scheduler.get_schedule(watch_item.id)
    assert after_schedule is not None
    assert after_schedule.next_run_at == resumed_at


def test_runtime_wakeup_rescan_respects_backoff_window(tmp_path) -> None:
    """睡眠恢復後若仍在 backoff 期，不應強制立即補掃。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-wakeup-backoff")
    watch_repository.save(watch_item)
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("22990"),
            checked_at=datetime(2026, 4, 13, 9, 50, tzinfo=UTC),
            backoff_until=datetime(2026, 4, 13, 13, 0, tzinfo=UTC),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    initial_now = datetime(2026, 4, 13, 10, 0, tzinfo=UTC)
    resumed_at = datetime(2026, 4, 13, 12, 30, tzinfo=UTC)

    asyncio.run(runtime._sync_watch_definitions(now=initial_now))
    asyncio.run(
        runtime._sync_watch_definitions(
            now=resumed_at,
            resumed_after_sleep=True,
        )
    )
    schedule = runtime._scheduler.get_schedule(watch_item.id)
    assert schedule is not None
    assert schedule.next_run_at == datetime(2026, 4, 13, 13, 0, tzinfo=UTC)


def test_runtime_reuses_dispatcher_when_settings_unchanged(tmp_path) -> None:
    """runtime 在設定未變時不應每次檢查都重建 dispatcher。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-dispatcher-cache")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("25000"),
        )
    )
    app_settings_service.settings_repository.save_notification_channel_settings(
        NotificationChannelSettings(desktop_enabled=True)
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier_factory = _CountingNotifierFactory()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=notifier_factory,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("26000"),
        )
    )
    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert notifier_factory.call_count == 1


def test_request_check_now_reuses_same_inflight_task_for_same_watch(tmp_path) -> None:
    """同一個 watch 同時觸發兩次立即檢查時，應只執行一次實際刷新。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-check-now-lock")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    fetcher = _BlockingChromeFetcher()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
    )

    import asyncio

    async def _scenario() -> None:
        first = asyncio.create_task(runtime.request_check_now(watch_item.id))
        await asyncio.to_thread(fetcher.started.wait, 1)
        second = asyncio.create_task(runtime.request_check_now(watch_item.id))
        await asyncio.sleep(0)
        assert fetcher.call_count == 1
        fetcher.release.set()
        await asyncio.gather(first, second)

    asyncio.run(_scenario())

    assert fetcher.call_count == 1
    assert runtime._inflight_tasks == {}


def test_background_assignment_and_check_now_share_same_inflight_task(tmp_path) -> None:
    """背景排程與立即檢查同時命中同一個 watch 時，應共用同一個檢查 task。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-assignment-lock")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))
    runtime_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("22990"),
            checked_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        )
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    fetcher = _BlockingChromeFetcher()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
    )
    runtime._scheduler.register_watch(
        watch_item_id=watch_item.id,
        interval_seconds=watch_item.scheduler_interval_seconds,
        now=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
        next_run_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )

    import asyncio

    async def _scenario() -> None:
        background = asyncio.create_task(runtime._run_assignment(watch_item.id))
        await asyncio.to_thread(fetcher.started.wait, 1)
        manual = asyncio.create_task(runtime.request_check_now(watch_item.id))
        await asyncio.sleep(0)
        assert fetcher.call_count == 1
        fetcher.release.set()
        await asyncio.gather(background, manual)

    asyncio.run(_scenario())

    assert fetcher.call_count == 1
    assert runtime._inflight_tasks == {}


def _build_latest_snapshot(
    *,
    watch_item_id: str,
    amount: Decimal,
    availability: Availability = Availability.AVAILABLE,
    consecutive_failures: int = 0,
    last_error_code: str | None = None,
    backoff_until: datetime | None = None,
    checked_at: datetime | None = None,
):
    """撱箇? runtime 皜祈岫?函?銝?蝑?latest snapshot??"""
    from app.domain.entities import LatestCheckSnapshot

    return LatestCheckSnapshot(
        watch_item_id=watch_item_id,
        checked_at=checked_at or datetime.now(UTC),
        availability=availability,
        normalized_price_amount=amount,
        currency="JPY",
        backoff_until=backoff_until,
        consecutive_failures=consecutive_failures,
        last_error_code=last_error_code,
    )


def _build_notification_state(
    *,
    watch_item_id: str,
    consecutive_failures: int,
    consecutive_parse_failures: int,
):
    """建立 runtime 恢復測試用的既有通知狀態。"""
    from app.domain.entities import NotificationState

    return NotificationState(
        watch_item_id=watch_item_id,
        consecutive_failures=consecutive_failures,
        consecutive_parse_failures=consecutive_parse_failures,
        degraded_notified_at=datetime.now(UTC),
    )


def _build_runtime_watch_item(watch_item_id: str) -> WatchItem:
    """建立 background runtime 測試共用的 watch item。"""
    return WatchItem(
        id=watch_item_id,
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only; 2 adults",
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
            "&ppc=2&rc=1&rm=10191605&si=1&st=1"
        ),
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_runtime_draft(seed_url: str) -> SearchDraft:
    """建立 background runtime 測試共用的 draft。"""
    return SearchDraft(
        seed_url=seed_url,
        hotel_id="00082173",
        room_id="10191605",
        plan_id="11035620",
        check_in_date=date(2026, 9, 18),
        check_out_date=date(2026, 9, 19),
        people_count=2,
        room_count=1,
    )


def _build_notifiers_for_test(
    settings: NotificationChannelSettings,
    notifier: Notifier,
) -> tuple[Notifier, ...]:
    """靘葫閰衣閮剖?瘙箏??臬? recording notifier??"""
    del settings
    return (notifier,)
