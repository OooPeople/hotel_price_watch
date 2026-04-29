from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import CheckEvent, WatchItem
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationDeliveryStatus,
    NotificationEventKind,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
    SqliteWatchItemRepository,
)
from app.monitor.runtime import (
    ChromeDrivenMonitorRuntime,
)
from app.sites.ikyu.client import _build_target_page_url
from app.sites.registry import SiteRegistry

from .helpers import (
    _build_latest_snapshot,
    _build_notification_state,
    _build_notifiers_for_test,
    _build_runtime_draft,
    _build_runtime_watch_item,
    _FakeChromeFetcher,
    _FakeRuntimeAdapter,
    _PausingChromeFetcher,
    _PausingNotifier,
    _PausingOnGetWatchRepository,
    _RecordingChromeFetcher,
    _RecordingNotifier,
)


def test_runtime_run_watch_check_once_persists_snapshot_and_history(tmp_path) -> None:
    """驗證 runtime 單次檢查會保存 latest snapshot、事件與價格歷史。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.availability is Availability.AVAILABLE
    assert latest_snapshot.normalized_price_amount == Decimal("22990")
    assert latest_snapshot.currency == "JPY"

    check_events = runtime_history_repository.list_check_events(watch_item.id)
    assert len(check_events) == 1
    assert check_events[0].event_kinds == ("checked",)

    price_history = runtime_history_repository.list_price_history(watch_item.id)
    assert len(price_history) == 1
    assert price_history[0].normalized_price_amount == Decimal("22990")
    assert price_history[0].source_kind is SourceKind.BROWSER

def test_runtime_discards_result_when_watch_is_paused_midflight(tmp_path) -> None:
    """in-flight 檢查期間若 watch 被暫停，不應寫入新結果或發送通知。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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
    assert runtime_history_repository.list_check_events(watch_item.id) == []
    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(watch_item.id)
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
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert notifier.messages == []
    assert runtime_history_repository.list_check_events(watch_item.id) == []
    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(watch_item.id)
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
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert len(notifier.messages) == 1
    assert runtime_history_repository.list_check_events(watch_item.id) == []
    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("25000")
    paused_watch = watch_repository.get(watch_item.id)
    assert paused_watch is not None
    assert paused_watch.paused_reason == "manually_paused"

def test_runtime_does_not_treat_unknown_to_available_as_became_available(tmp_path) -> None:
    """中間若只有 unknown 雜訊，不應把 available 判成恢復可訂。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-no-false-recovery")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))
    runtime_write_repository.append_check_event(
        CheckEvent(
            watch_item_id=watch_item.id,
            checked_at=datetime(2026, 4, 14, 15, 30, tzinfo=UTC),
            availability=Availability.AVAILABLE,
            event_kinds=("checked",),
            normalized_price_amount=Decimal("18434"),
            currency="JPY",
        )
    )
    runtime_write_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("18434"),
            checked_at=datetime(2026, 4, 14, 16, 12, tzinfo=UTC),
            last_error_code=CheckErrorCode.NETWORK_ERROR.value,
        )
    )
    runtime_write_repository.append_check_event(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_event = runtime_history_repository.list_check_events(watch_item.id)[-1]
    assert NotificationEventKind.BECAME_AVAILABLE.value not in latest_event.event_kinds
    assert latest_event.notification_status.value == "not_requested"
    assert notifier.messages == []

def test_runtime_prefers_saved_browser_tab_hint(tmp_path) -> None:
    """驗證 runtime 刷新時會優先使用 watch draft 保存的 browser tab hint。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    operation_url = _build_target_page_url(watch_item.target)
    assert fetcher.calls == [
        (
            operation_url,
            operation_url,
            "target-keep-me",
        )
    ]
    updated_draft = watch_repository.get_draft(watch_item.id)
    assert updated_draft is not None
    assert updated_draft.browser_tab_id == "tab-1"
    assert updated_draft.browser_page_url == operation_url


def test_runtime_check_uses_seed_url_when_canonical_url_is_hotel_root(tmp_path) -> None:
    """正式 canonical 是飯店根頁時，browser refresh 仍應使用精確 seed URL。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    precise_seed_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
        "&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )
    watch_item = replace(
        _build_runtime_watch_item("watch-runtime-check-precise-url"),
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        replace(
            _build_runtime_draft(precise_seed_url),
            browser_tab_id="stale-tab",
            browser_page_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        ),
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    fetcher = _RecordingChromeFetcher()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=fetcher,
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    operation_url = _build_target_page_url(watch_item.target)
    assert fetcher.calls == [(operation_url, operation_url, "stale-tab")]
    updated_draft = watch_repository.get_draft(watch_item.id)
    assert updated_draft is not None
    assert updated_draft.browser_tab_id == "tab-1"
    assert updated_draft.browser_page_url == operation_url

def test_runtime_success_resets_previous_failure_and_degraded_state(tmp_path) -> None:
    """前次失敗後若本次成功，runtime 應清掉 failure/backoff/degraded 狀態。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-recovery")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )
    runtime_write_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("26000"),
            consecutive_failures=3,
            last_error_code="parse_failed",
        )
    )
    runtime_write_repository.save_notification_state(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.last_error_code is None
    assert latest_snapshot.consecutive_failures == 0
    assert latest_snapshot.backoff_until is None
    assert latest_snapshot.is_degraded is False

    notification_state = runtime_history_repository.get_notification_state(watch_item.id)
    assert notification_state is not None
    assert notification_state.consecutive_failures == 0
    assert notification_state.consecutive_parse_failures == 0
    assert notification_state.degraded_notified_at is None
