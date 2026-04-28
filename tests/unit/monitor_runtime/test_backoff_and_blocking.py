from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.domain.entities import WatchItem
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationEventKind,
    NotificationLeafKind,
    RuntimeStateEventKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
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
from app.monitor.check_executor import _map_runtime_exception_to_error_code_typed
from app.monitor.runtime import ChromeDrivenMonitorRuntime
from app.sites.ikyu.client import _build_target_page_url
from app.sites.ikyu.page_guards import IkyuBlockedPageError
from app.sites.registry import SiteRegistry

from .helpers import (
    _build_latest_snapshot,
    _build_notification_state,
    _build_runtime_draft,
    _build_runtime_watch_item,
    _DiscardedChromeFetcher,
    _FakeChromeFetcher,
    _FakeRuntimeAdapter,
    _ForbiddenChromeFetcher,
    _ThrottledChromeFetcher,
    _TimeoutChromeFetcher,
)


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
    """驗證可能被節流的 Chrome 分頁會寫入 runtime debug artifact。"""
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
    assert debug_artifacts[0].source_url == _build_target_page_url(watch_item.target)


def test_runtime_records_discarded_page_debug_artifact(tmp_path) -> None:
    """驗證 Chrome discarded 分頁會寫入 page discarded debug artifact。"""
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
