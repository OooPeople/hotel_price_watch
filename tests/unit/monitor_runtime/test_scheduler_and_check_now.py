from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.domain.value_objects import WatchTarget
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
from app.sites.registry import SiteRegistry

from .helpers import (
    _AmountByPlanRuntimeAdapter,
    _BlockingChromeFetcher,
    _build_latest_snapshot,
    _build_runtime_draft,
    _build_runtime_watch_item,
    _FakeChromeFetcher,
    _FakeRuntimeAdapter,
    _RecordingChromeFetcher,
    _wait_for_startup_restore,
)


def test_runtime_sync_removes_watch_after_pause_or_disable(tmp_path) -> None:
    """watch 若被停用或標記 paused，下一次同步時應從 scheduler 移除。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-resync")
    watch_repository.save(watch_item)

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
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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
            await _wait_for_startup_restore(runtime)
            for _ in range(200):
                if (
                    runtime_history_repository.get_latest_check_snapshot(watch_a.id) is not None
                    and runtime_history_repository.get_latest_check_snapshot(watch_b.id) is not None
                ):
                    break
                await asyncio.sleep(0.01)
        finally:
            await runtime.stop()

    import asyncio

    asyncio.run(_exercise_runtime())

    latest_a = runtime_history_repository.get_latest_check_snapshot(watch_a.id)
    latest_b = runtime_history_repository.get_latest_check_snapshot(watch_b.id)
    assert latest_a is not None
    assert latest_b is not None
    assert latest_a.normalized_price_amount == Decimal("22990")
    assert latest_b.normalized_price_amount == Decimal("24800")
    assert fetcher.calls == []
    assert len(fetcher.ensure_calls) == 2


def test_runtime_loop_syncs_watch_added_after_start(tmp_path) -> None:
    """runtime 啟動後新增的 watch，應在後續 tick 被同步並完成檢查。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    runtime = ChromeDrivenMonitorRuntime(
        watch_item_repository=watch_repository,
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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
                runtime_history_repository.get_latest_check_snapshot(watch_item.id) is None
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)
        finally:
            await runtime.stop()

    import asyncio

    asyncio.run(_exercise_runtime())

    latest_snapshot = runtime_history_repository.get_latest_check_snapshot(
        "watch-runtime-added-later"
    )
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("22990")


def test_runtime_wakeup_rescan_reschedules_existing_watch(tmp_path) -> None:
    """睡眠恢復後若不在 backoff 期，既有 watch 應被立即補掃。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-wakeup")
    watch_repository.save(watch_item)
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-wakeup-backoff")
    watch_repository.save(watch_item)
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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


def test_request_check_now_reuses_same_inflight_task_for_same_watch(tmp_path) -> None:
    """同一個 watch 同時觸發兩次立即檢查時，應只執行一次實際刷新。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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
    runtime_write_repository = SqliteRuntimeWriteRepository(database)
    runtime_history_repository = SqliteRuntimeHistoryQueryRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-assignment-lock")
    watch_repository.save(watch_item)
    watch_repository.save_draft(watch_item.id, _build_runtime_draft(watch_item.canonical_url))
    runtime_write_repository.save_latest_check_snapshot(
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
        runtime_write_repository=runtime_write_repository,
        runtime_history_repository=runtime_history_repository,
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
