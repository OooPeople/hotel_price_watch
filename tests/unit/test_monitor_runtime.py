from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import PriceSnapshot, WatchItem
from app.domain.enums import Availability, CheckErrorCode, NotificationLeafKind, SourceKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser.chrome_cdp_fetcher import ChromeTabCapture, ChromeTabSummary
from app.infrastructure.browser.ikyu_page_guards import IkyuBlockedPageError
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.monitor.runtime import (
    ChromeDrivenMonitorRuntime,
    _map_runtime_exception_to_error_code_typed,
)
from app.notifiers.base import Notifier
from app.notifiers.models import NotificationMessage
from app.sites.base import CandidateSelection, SiteAdapter
from app.sites.registry import SiteRegistry


class _FakeChromeFetcher:
    """?? monitor runtime 皜祈岫?函??箏? Chrome capture??"""

    def is_debuggable_chrome_running(self) -> bool:
        """回傳測試用的可附著狀態。"""
        return True

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
    ) -> ChromeTabCapture:
        """??箏???????HTML嚗芋?砍?啣?????"""
        del fallback_url, preferred_tab_id
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
    ) -> ChromeTabCapture:
        """? hidden / not_focused ????閬?"""
        del fallback_url, preferred_tab_id
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
    ) -> ChromeTabCapture:
        """?撣嗆? `was_discarded` 閮?????閬?"""
        del fallback_url, preferred_tab_id
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
        self.calls: list[tuple[str, str | None, str | None]] = []

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
    ) -> ChromeTabCapture:
        """閮? runtime 撖阡??喳????蝝Ｕ?"""
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
    ) -> ChromeTabCapture:
        """直接拋出含 403 訊號的例外，驗證 runtime 會進入暫停流程。"""
        del expected_url, fallback_url, preferred_tab_id
        raise IkyuBlockedPageError("ikyu 已回傳阻擋頁面。")


class _TimeoutChromeFetcher(_FakeChromeFetcher):
    """模擬專用 Chrome 分頁刷新逾時。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
    ) -> ChromeTabCapture:
        """直接拋出逾時錯誤，驗證 runtime 會映射成 network_timeout。"""
        del expected_url, fallback_url, preferred_tab_id
        raise TimeoutError("refresh timed out")


class _RecordingNotifier:
    """閮?撖阡??閮?批捆?陛??notifier??"""

    channel_name = "desktop"

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        """靽? dispatch ?????荔?靘葫閰阡?霅?"""
        self.messages.append(message)


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

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    updated_watch_item = watch_repository.get(watch_item.id)
    assert updated_watch_item is not None
    assert updated_watch_item.enabled is False
    assert updated_watch_item.paused_reason == "http_403"

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.last_error_code == "http_403"
    assert latest_snapshot.consecutive_failures == 1

    debug_artifacts = runtime_repository.list_debug_artifacts(watch_item.id)
    assert len(debug_artifacts) == 1
    assert debug_artifacts[0].reason == "http_403"

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
    )

    async def _exercise_runtime() -> None:
        """啟動 background loop，等待多筆 watch 都被處理。"""
        await runtime.start()
        try:
            await asyncio.sleep(0.08)
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
            await asyncio.sleep(0.15)
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


def _build_latest_snapshot(
    *,
    watch_item_id: str,
    amount: Decimal,
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
        availability=Availability.AVAILABLE,
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
