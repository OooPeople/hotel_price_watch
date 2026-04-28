from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.app_settings import AppSettingsService
from app.domain.value_objects import WatchTarget
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.monitor.runtime import (
    ChromeDrivenMonitorRuntime,
)
from app.sites.ikyu.client import _build_target_page_url
from app.sites.registry import SiteRegistry

from .helpers import (
    _BlockingRestoreChromeFetcher,
    _build_runtime_draft,
    _build_runtime_watch_item,
    _FailingRestoreChromeFetcher,
    _FakeChromeFetcher,
    _FakeRuntimeAdapter,
    _RecordingChromeFetcher,
    _wait_for_startup_restore,
)


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


def test_runtime_start_restores_only_enabled_and_unpaused_watch_tabs(
    tmp_path,
    capsys,
) -> None:
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
        await _wait_for_startup_restore(runtime)
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    operation_url = _build_target_page_url(active_watch.target)
    assert fetcher.ensure_calls == [
        (
            operation_url,
            operation_url,
            None,
            (),
        )
    ]
    captured = capsys.readouterr()
    assert "啟動恢復監視分頁：準備恢復 1 筆監視。" in captured.out
    assert "啟動恢復監視分頁成功" in captured.out
    assert active_watch.id in captured.out


def test_runtime_start_does_not_wait_for_startup_tab_restore(tmp_path) -> None:
    """runtime 啟動時應先讓 GUI startup 完成，再背景恢復 watch 分頁。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    active_watch = _build_runtime_watch_item("watch-runtime-restore-nonblocking")
    watch_repository.save(active_watch)
    watch_repository.save_draft(
        active_watch.id,
        _build_runtime_draft(active_watch.canonical_url),
    )

    fetcher = _BlockingRestoreChromeFetcher()
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
        await asyncio.wait_for(runtime.start(), timeout=0.5)
        status = runtime.get_status()
        assert status.is_running is True
        assert runtime._startup_restore_task is not None
        assert runtime._startup_restore_task.done() is False

        await asyncio.to_thread(fetcher.started.wait, 1)
        await asyncio.sleep(0.05)
        assert runtime_repository.get_latest_check_snapshot(active_watch.id) is None
        fetcher.release.set()
        await _wait_for_startup_restore(runtime)
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    operation_url = _build_target_page_url(active_watch.target)
    assert fetcher.ensure_calls == [
        (
            operation_url,
            operation_url,
            None,
            (),
        )
    ]


def test_runtime_restore_uses_precise_seed_url_and_heals_tab_assignment(tmp_path) -> None:
    """啟動恢復應用精確 seed URL 找分頁，成功後回寫新的 tab hint。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    precise_seed_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
        "&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )
    watch_item = replace(
        _build_runtime_watch_item("watch-runtime-restore-precise-url"),
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
    )
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        replace(
            _build_runtime_draft(precise_seed_url),
            browser_tab_id="stale-tab",
            browser_page_url=(
                "https://www.ikyu.com/zh-tw/00082173/"
                "?adc=1&cid=20260918&pln=99999999&ppc=2&rc=1&rm=88888888"
            ),
        ),
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
        await _wait_for_startup_restore(runtime)
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    operation_url = _build_target_page_url(watch_item.target)
    assert fetcher.ensure_calls == [(operation_url, operation_url, "stale-tab", ())]
    updated_draft = watch_repository.get_draft(watch_item.id)
    assert updated_draft is not None
    assert updated_draft.browser_tab_id == "stale-tab"
    assert updated_draft.browser_page_url == operation_url


def test_runtime_restore_captures_without_scheduled_reload(tmp_path) -> None:
    """啟動恢復分頁後應直接擷取並推進排程，避免立刻再刷新全部分頁。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    settings_repository = SqliteAppSettingsRepository(database)
    app_settings_service = AppSettingsService(settings_repository)

    watch_item = _build_runtime_watch_item("watch-runtime-restore-capture")
    watch_repository.save(watch_item)
    watch_repository.save_draft(
        watch_item.id,
        _build_runtime_draft(watch_item.canonical_url),
    )

    fetcher = _RecordingChromeFetcher()
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
    registered_at = datetime.now(UTC)

    import asyncio

    async def _exercise_runtime() -> None:
        active_watch_items = await runtime._sync_watch_definitions(now=registered_at)
        assert runtime._scheduler.get_schedule(watch_item.id).next_run_at == registered_at
        await runtime._restore_active_watch_tabs(active_watch_items)

    asyncio.run(_exercise_runtime())

    latest_snapshot = runtime_repository.get_latest_check_snapshot(watch_item.id)
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("22990")
    assert fetcher.calls == []
    assert fetcher.ensure_calls == [
        (
            _build_target_page_url(watch_item.target),
            _build_target_page_url(watch_item.target),
            None,
            (),
        )
    ]
    assert runtime._scheduler.get_schedule(watch_item.id).next_run_at > registered_at


def test_runtime_start_continues_when_single_tab_restore_fails(
    tmp_path,
    capsys,
) -> None:
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
        await _wait_for_startup_restore(runtime)
        status = runtime.get_status()
        assert status.is_running is True
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    assert len(fetcher.ensure_calls) >= 2
    assert any(
        call[0] == _build_target_page_url(second_watch.target)
        for call in fetcher.ensure_calls
    )
    captured = capsys.readouterr()
    assert "啟動恢復監視分頁失敗" in captured.out
    assert first_watch.id in captured.out
    assert "RuntimeError: restore failed" in captured.out
    assert "啟動恢復監視分頁成功" in captured.out
    assert second_watch.id in captured.out


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
        await _wait_for_startup_restore(runtime)
        await runtime.stop()

    asyncio.run(_exercise_runtime())

    assert len(fetcher.ensure_calls) == 2
    assert fetcher.ensure_calls[0][3] == ()
    assert fetcher.ensure_calls[1][3] == ("restored-tab-1",)
