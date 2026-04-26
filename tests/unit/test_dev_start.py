"""驗證單一啟動入口的 Chrome 檢查與 GUI 啟動流程。"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.entities import WatchItem
from app.domain.enums import NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import WatchTarget
from app.infrastructure.db import SqliteDatabase, SqliteWatchItemRepository
from app.sites.ikyu.client import _build_target_page_url
from app.tools import dev_start


@pytest.fixture(autouse=True)
def _isolate_dev_start_database(monkeypatch, tmp_path) -> None:
    """讓 dev_start 測試固定使用測試資料庫，避免讀到本機真實監視資料。"""
    monkeypatch.setenv(
        "HOTEL_PRICE_WATCH_DB_PATH",
        str(tmp_path / "hotel_price_watch.db"),
    )


class _FakeFetcher:
    """模擬可偵測與喚醒專用 Chrome 的 fetcher。"""

    def __init__(self, *, running: bool) -> None:
        """建立測試用 fetcher，並記錄是否已有可附著 Chrome。"""
        self.running = running
        self.opened = False
        self.open_start_url: str | None = None

    def is_debuggable_chrome_running(self) -> bool:
        """回傳目前是否已有可附著 Chrome。"""
        return self.running

    def open_profile_window(self, start_url: str | None = None) -> None:
        """記錄是否有嘗試喚醒專用 Chrome。"""
        self.opened = True
        self.open_start_url = start_url


class _FailingOpenFetcher(_FakeFetcher):
    """模擬專用 Chrome profile 啟動失敗的 fetcher。"""

    def open_profile_window(self, start_url: str | None = None) -> None:
        """記錄啟動嘗試後丟出錯誤，驗證 lock 會被清理。"""
        super().open_profile_window(start_url=start_url)
        raise ValueError("chrome launch failed")


def test_dev_start_uses_existing_debuggable_chrome(monkeypatch) -> None:
    """若已存在可附著 Chrome，單一啟動入口不應再重開 profile。"""
    fetcher = _FakeFetcher(running=True)
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(dev_start, "read_lock_record", lambda path: None)
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: False)
    monkeypatch.setattr(dev_start, "write_lock_record", lambda path, record: None)
    monkeypatch.setattr(dev_start, "remove_lock_record", lambda path: None)
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    dev_start.main()

    assert fetcher.opened is False
    assert uvicorn_calls == [
        {
            "args": ("app.main:app",),
            "kwargs": {
                "host": "127.0.0.1",
                "port": 8000,
                "reload": True,
            },
        }
    ]


def test_dev_start_opens_profile_when_debuggable_chrome_missing(monkeypatch) -> None:
    """若尚未啟動專用 Chrome，單一啟動入口應先喚醒 profile 再起 GUI。"""
    fetcher = _FakeFetcher(running=False)
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(dev_start, "read_lock_record", lambda path: None)
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: False)
    monkeypatch.setattr(dev_start, "write_lock_record", lambda path, record: None)
    monkeypatch.setattr(dev_start, "remove_lock_record", lambda path: None)
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    dev_start.main()

    assert fetcher.opened is True
    assert fetcher.open_start_url is None
    assert uvicorn_calls == [
        {
            "args": ("app.main:app",),
            "kwargs": {
                "host": "127.0.0.1",
                "port": 8000,
                "reload": True,
            },
        }
    ]


def test_dev_start_opens_first_active_watch_when_runtime_enabled(monkeypatch) -> None:
    """已有 active watch 時，啟動專用 Chrome 應直接使用第一筆監視 URL。"""
    fetcher = _FakeFetcher(running=False)
    uvicorn_calls: list[dict[str, object]] = []
    watch_item = _build_dev_start_watch_item("watch-dev-start-active")
    database = SqliteDatabase(dev_start._resolve_database_path())
    database.initialize()
    SqliteWatchItemRepository(database).save(watch_item)
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(dev_start, "read_lock_record", lambda path: None)
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: False)
    monkeypatch.setattr(dev_start, "write_lock_record", lambda path, record: None)
    monkeypatch.setattr(dev_start, "remove_lock_record", lambda path: None)
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    dev_start.main()

    assert fetcher.opened is True
    assert fetcher.open_start_url == _build_target_page_url(watch_item.target)
    assert len(uvicorn_calls) == 1


def test_dev_start_opens_blank_profile_when_runtime_auto_start_disabled(
    monkeypatch,
) -> None:
    """安全測試模式啟動專用 Chrome 時不應預設開啟站台頁面。"""
    fetcher = _FakeFetcher(running=False)
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setenv("HOTEL_PRICE_WATCH_RUNTIME_ENABLED", "0")
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(dev_start, "read_lock_record", lambda path: None)
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: False)
    monkeypatch.setattr(dev_start, "write_lock_record", lambda path, record: None)
    monkeypatch.setattr(dev_start, "remove_lock_record", lambda path: None)
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    dev_start.main()

    assert fetcher.opened is True
    assert fetcher.open_start_url == "about:blank"
    assert len(uvicorn_calls) == 1


def _build_dev_start_watch_item(watch_item_id: str) -> WatchItem:
    """建立 dev_start 測試用的最小 IKYU watch item。"""
    target = WatchTarget(
        site="ikyu",
        hotel_id="00082173",
        room_id="10191605",
        plan_id="11035620",
        check_in_date=date(2026, 9, 18),
        check_out_date=date(2026, 9, 19),
        people_count=2,
        room_count=1,
    )
    return WatchItem(
        id=watch_item_id,
        target=target,
        hotel_name="Dormy Inn",
        room_name="standard room",
        plan_name="room only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("20000"),
        ),
        scheduler_interval_seconds=600,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_dev_start_cleans_lock_when_profile_launch_fails(monkeypatch) -> None:
    """專用 Chrome 啟動失敗時也應清理本次寫入的 app lock。"""
    fetcher = _FailingOpenFetcher(running=False)
    removed_paths: list[object] = []
    written_records: list[object] = []
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(dev_start, "read_lock_record", lambda path: None)
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: False)
    monkeypatch.setattr(
        dev_start,
        "write_lock_record",
        lambda path, record: written_records.append((path, record)),
    )
    monkeypatch.setattr(
        dev_start,
        "remove_lock_record",
        lambda path: removed_paths.append(path),
    )
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    try:
        dev_start.main()
    except ValueError as exc:
        assert "chrome launch failed" in str(exc)
    else:
        raise AssertionError("expected Chrome launch failure to raise")

    assert fetcher.opened is True
    assert len(written_records) == 1
    assert len(removed_paths) == 1
    assert uvicorn_calls == []


def test_dev_start_suppresses_node_dep0169_warning_for_playwright(monkeypatch) -> None:
    """單一啟動入口應只抑制 DEP0169，避免 Playwright driver warning 干擾終端機。"""
    monkeypatch.delenv("NODE_OPTIONS", raising=False)

    dev_start._ensure_node_dep0169_warning_suppressed()

    assert dev_start.NODE_DEP0169_SUPPRESSION_OPTION in os.environ["NODE_OPTIONS"]


def test_dev_start_preserves_existing_node_options(monkeypatch) -> None:
    """加入 DEP0169 抑制時應保留使用者既有 NODE_OPTIONS。"""
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")

    dev_start._ensure_node_dep0169_warning_suppressed()

    assert os.environ["NODE_OPTIONS"] == (
        f"--max-old-space-size=4096 {dev_start.NODE_DEP0169_SUPPRESSION_OPTION}"
    )


def test_dev_start_reuses_existing_instance_when_port_and_lock_exist(monkeypatch) -> None:
    """若已有既有 app instance，單一啟動入口應直接沿用而不再啟動 uvicorn。"""
    fetcher = _FakeFetcher(running=True)
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(
        dev_start,
        "read_lock_record",
        lambda path: dev_start.create_lock_record(
            pid=12345,
            started_at=datetime(2026, 4, 12, 10, 0, 0),
            instance_id="instance-1",
        ),
    )
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: True)
    monkeypatch.setattr(dev_start, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        dev_start,
        "_probe_existing_instance_health",
        lambda **kwargs: {
            "status": "ok",
            "instance_id": "instance-1",
            "runtime": {
                "is_running": True,
                "chrome_debuggable": True,
            },
        },
    )
    monkeypatch.setattr(dev_start, "write_lock_record", lambda path, record: None)
    monkeypatch.setattr(dev_start, "remove_lock_record", lambda path: None)
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    dev_start.main()

    assert fetcher.opened is False
    assert uvicorn_calls == []


def test_dev_start_reuse_requires_healthy_existing_instance(monkeypatch) -> None:
    """若偵測到既有實例但 /health 無法取得有效回應，應直接報錯而非靜默沿用。"""
    fetcher = _FakeFetcher(running=True)
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(
        dev_start,
        "read_lock_record",
        lambda path: dev_start.create_lock_record(
            pid=12345,
            started_at=datetime(2026, 4, 12, 10, 0, 0),
            instance_id="instance-1",
        ),
    )
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: True)
    monkeypatch.setattr(dev_start, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        dev_start,
        "_probe_existing_instance_health",
        lambda **kwargs: None,
    )

    try:
        dev_start.main()
    except RuntimeError as exc:
        assert "/health" in str(exc)
    else:
        raise AssertionError("expected existing instance health probe failure to raise")


def test_dev_start_reuse_requires_matching_instance_id(monkeypatch) -> None:
    """既有實例沿用前，lock file 與 `/health` 的 instance_id 必須一致。"""
    fetcher = _FakeFetcher(running=True)
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(
        dev_start,
        "read_lock_record",
        lambda path: dev_start.create_lock_record(
            pid=12345,
            started_at=datetime(2026, 4, 12, 10, 0, 0),
            instance_id="instance-1",
        ),
    )
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: True)
    monkeypatch.setattr(dev_start, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        dev_start,
        "_probe_existing_instance_health",
        lambda **kwargs: {
            "status": "ok",
            "instance_id": "instance-2",
            "runtime": {
                "is_running": True,
                "chrome_debuggable": True,
            },
        },
    )

    try:
        dev_start.main()
    except RuntimeError as exc:
        assert "instance_id" in str(exc)
    else:
        raise AssertionError("expected instance id mismatch to raise")


def test_dev_start_cleans_stale_lock_before_start(monkeypatch) -> None:
    """若 lock 已 stale，啟動流程應先清掉再正常啟動。"""
    fetcher = _FakeFetcher(running=True)
    removed_paths: list[object] = []
    written_records: list[object] = []
    uvicorn_calls: list[dict[str, object]] = []
    monkeypatch.setattr(dev_start, "ChromeCdpHtmlFetcher", lambda **kwargs: fetcher)
    monkeypatch.setattr(
        dev_start,
        "read_lock_record",
        lambda path: dev_start.create_lock_record(
            pid=12345,
            started_at=datetime(2026, 4, 12, 10, 0, 0),
            instance_id="instance-1",
        ),
    )
    monkeypatch.setattr(dev_start, "_is_port_in_use", lambda **kwargs: False)
    monkeypatch.setattr(dev_start, "_pid_exists", lambda pid: False)
    monkeypatch.setattr(
        dev_start,
        "remove_lock_record",
        lambda path: removed_paths.append(path),
    )
    monkeypatch.setattr(
        dev_start,
        "write_lock_record",
        lambda path, record: written_records.append((path, record)),
    )
    monkeypatch.setattr(
        dev_start.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        ),
    )

    dev_start.main()

    assert len(removed_paths) >= 2
    assert len(written_records) == 1
    assert len(uvicorn_calls) == 1
