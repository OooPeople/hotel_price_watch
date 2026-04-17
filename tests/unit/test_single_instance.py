from datetime import datetime
from pathlib import Path

from app.monitor.single_instance import (
    SingleInstanceAction,
    create_lock_record,
    decide_single_instance_startup,
    read_lock_record,
)


def test_start_new_when_no_port_and_no_lock() -> None:
    """驗證沒有埠占用與 lock 時會決定啟動新實例。"""
    decision = decide_single_instance_startup(
        port_in_use=False,
        lock_record=None,
        pid_exists=None,
        pid_matches_app=None,
    )

    assert decision.action is SingleInstanceAction.START_NEW


def test_reuse_existing_when_port_and_lock_match_running_app() -> None:
    """驗證埠與 lock 都指向同一執行中 app 時會重用既有實例。"""
    decision = decide_single_instance_startup(
        port_in_use=True,
        lock_record=create_lock_record(
            pid=100,
            started_at=datetime(2026, 4, 12, 10, 0, 0),
            instance_id="instance-1",
        ),
        pid_exists=True,
        pid_matches_app=True,
    )

    assert decision.action is SingleInstanceAction.REUSE_EXISTING


def test_clean_stale_lock_when_pid_is_gone() -> None:
    """驗證 lock 指向的 PID 已不存在時會清掉 stale lock 後啟動。"""
    decision = decide_single_instance_startup(
        port_in_use=False,
        lock_record=create_lock_record(
            pid=100,
            started_at=datetime(2026, 4, 12, 10, 0, 0),
            instance_id="instance-1",
        ),
        pid_exists=False,
        pid_matches_app=None,
    )

    assert decision.action is SingleInstanceAction.CLEAN_STALE_LOCK_AND_START


def test_error_when_port_belongs_to_another_process() -> None:
    """驗證埠被非本 app 程序占用時會回報 port conflict。"""
    decision = decide_single_instance_startup(
        port_in_use=True,
        lock_record=None,
        pid_exists=None,
        pid_matches_app=None,
    )

    assert decision.action is SingleInstanceAction.ERROR_PORT_CONFLICT


def test_read_lock_record_returns_none_for_malformed_json(tmp_path: Path) -> None:
    """驗證 lock 檔 JSON 損毀時會安全回傳 None。"""
    lock_path = tmp_path / "monitor.lock"
    lock_path.write_text("{not-json", encoding="utf-8")

    assert read_lock_record(lock_path) is None
