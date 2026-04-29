from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    CheckResult,
    NotificationDecision,
    NotificationState,
    PriceSnapshot,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    NotificationEventKind,
    NotificationLeafKind,
    SourceKind,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteNotificationThrottleStateRepository,
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
    SqliteWatchItemRepository,
)
from app.monitor.notification_dispatch import NotificationDispatchCoordinator
from app.monitor.runtime import (
    ChromeDrivenMonitorRuntime,
)
from app.notifiers import PersistentNotificationThrottle
from app.sites.registry import SiteRegistry

from .helpers import (
    _build_latest_snapshot,
    _build_notifiers_for_test,
    _build_runtime_draft,
    _build_runtime_watch_item,
    _CountingNotifierFactory,
    _FailingNotifier,
    _FakeChromeFetcher,
    _FakeRuntimeAdapter,
    _RecordingNotifier,
)


def test_runtime_dispatches_notification_and_records_sent_status(tmp_path) -> None:
    """驗證 runtime 觸發通知後會保存 sent 狀態與通知通道資訊。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert len(notifier.messages) == 1
    check_events = runtime_history_repository.list_check_events(watch_item.id)
    assert len(check_events) == 1
    assert check_events[0].notification_status.value == "sent"
    assert check_events[0].sent_channels == ("desktop",)


def test_runtime_notification_throttle_persists_across_runtime_restart(tmp_path) -> None:
    """同一通道冷卻應跨 runtime 重啟保留，不可因 app 重啟而重置。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    notification_throttle_repository = SqliteNotificationThrottleStateRepository(
        database
    )
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

    runtime_one = NotificationDispatchCoordinator(
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
        notification_throttle=PersistentNotificationThrottle(
            notification_throttle_repository
        ),
    )
    first_result = runtime_one.dispatch_notification(
        watch_item=watch_item,
        check_result=check_result,
        notification_decision=decision,
        attempted_at=datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )
    assert first_result is not None
    assert first_result.sent_channels == ("desktop",)
    assert len(notifier.messages) == 1

    runtime_two = NotificationDispatchCoordinator(
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: _build_notifiers_for_test(settings, notifier),
        notification_throttle=PersistentNotificationThrottle(
            notification_throttle_repository
        ),
    )
    second_result = runtime_two.dispatch_notification(
        watch_item=watch_item,
        check_result=check_result,
        notification_decision=decision,
        attempted_at=datetime(2026, 4, 13, 10, 0, 30, tzinfo=UTC),
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
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=lambda settings: (successful_notifier, failing_notifier),
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert len(successful_notifier.messages) == 1
    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("22990")

    check_events = runtime_history_repository.list_check_events(watch_item.id)
    assert len(check_events) == 1
    assert check_events[0].notification_status.value == "partial"
    assert check_events[0].sent_channels == ("desktop",)
    assert check_events[0].failed_channels == ("discord",)

def test_runtime_reuses_dispatcher_when_settings_unchanged(tmp_path) -> None:
    """runtime 在設定未變時不應每次檢查都重建 dispatcher。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-dispatcher-cache")
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
    app_settings_service.settings_repository.save_notification_channel_settings(
        NotificationChannelSettings(desktop_enabled=True)
    )

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    notifier_factory = _CountingNotifierFactory()
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
        site_registry=site_registry,
        chrome_fetcher=_FakeChromeFetcher(),
        app_settings_service=app_settings_service,
        notifier_factory=notifier_factory,
    )

    import asyncio

    asyncio.run(runtime.run_watch_check_once(watch_item.id))
    runtime_write_repository.save_latest_check_snapshot(
        _build_latest_snapshot(
            watch_item_id=watch_item.id,
            amount=Decimal("26000"),
        )
    )
    asyncio.run(runtime.run_watch_check_once(watch_item.id))

    assert notifier_factory.call_count == 1
