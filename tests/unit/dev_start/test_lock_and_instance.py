"""dev_start single-instance lock 與既有實例沿用測試。"""

from __future__ import annotations

from datetime import datetime

from app.tools import dev_start

from .helpers import _FailingOpenFetcher, _FakeFetcher


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
