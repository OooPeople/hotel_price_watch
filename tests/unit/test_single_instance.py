from datetime import datetime
from pathlib import Path

from app.monitor.single_instance import (
    SingleInstanceAction,
    create_lock_record,
    decide_single_instance_startup,
    read_lock_record,
)


def test_start_new_when_no_port_and_no_lock() -> None:
    decision = decide_single_instance_startup(
        port_in_use=False,
        lock_record=None,
        pid_exists=None,
        pid_matches_app=None,
    )

    assert decision.action is SingleInstanceAction.START_NEW


def test_reuse_existing_when_port_and_lock_match_running_app() -> None:
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
    decision = decide_single_instance_startup(
        port_in_use=True,
        lock_record=None,
        pid_exists=None,
        pid_matches_app=None,
    )

    assert decision.action is SingleInstanceAction.ERROR_PORT_CONFLICT


def test_read_lock_record_returns_none_for_malformed_json(tmp_path: Path) -> None:
    lock_path = tmp_path / "monitor.lock"
    lock_path.write_text("{not-json", encoding="utf-8")

    assert read_lock_record(lock_path) is None
