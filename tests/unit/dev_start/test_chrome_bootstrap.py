"""dev_start 專用 Chrome 啟動決策測試。"""

from __future__ import annotations

from app.infrastructure.db import SqliteDatabase, SqliteWatchItemRepository
from app.sites.ikyu.client import _build_target_page_url
from app.tools import dev_start

from .helpers import _build_dev_start_watch_item, _FakeFetcher


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
