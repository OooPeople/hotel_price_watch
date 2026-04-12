"""單實例啟動與 lock file 決策邏輯。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class SingleInstanceAction(StrEnum):
    """表示啟動時對單實例檢查做出的決策。"""

    START_NEW = "start_new"
    REUSE_EXISTING = "reuse_existing"
    CLEAN_STALE_LOCK_AND_START = "clean_stale_lock_and_start"
    ERROR_PORT_CONFLICT = "error_port_conflict"


@dataclass(frozen=True, slots=True)
class InstanceLockRecord:
    """表示 lock file 中保存的執行個體資訊。"""

    pid: int
    started_at_utc: str
    instance_id: str


@dataclass(frozen=True, slots=True)
class SingleInstanceDecision:
    """表示單實例檢查後的最終行為。"""

    action: SingleInstanceAction
    reason: str


def decide_single_instance_startup(
    *,
    port_in_use: bool,
    lock_record: InstanceLockRecord | None,
    pid_exists: bool | None,
    pid_matches_app: bool | None,
) -> SingleInstanceDecision:
    """依 port / lock / PID 狀態決定是否啟動新 runtime。"""
    if port_in_use:
        if lock_record and pid_exists and pid_matches_app:
            return SingleInstanceDecision(
                action=SingleInstanceAction.REUSE_EXISTING,
                reason="existing app instance already owns the port",
            )
        return SingleInstanceDecision(
            action=SingleInstanceAction.ERROR_PORT_CONFLICT,
            reason="port is occupied by another process or inconsistent instance state",
        )

    if lock_record is None:
        return SingleInstanceDecision(
            action=SingleInstanceAction.START_NEW,
            reason="no existing lock record",
        )

    if pid_exists:
        if pid_matches_app:
            return SingleInstanceDecision(
                action=SingleInstanceAction.REUSE_EXISTING,
                reason="existing app instance already owns the lock",
            )
        return SingleInstanceDecision(
            action=SingleInstanceAction.ERROR_PORT_CONFLICT,
            reason="lock exists but PID belongs to another app",
        )

    return SingleInstanceDecision(
        action=SingleInstanceAction.CLEAN_STALE_LOCK_AND_START,
        reason="stale lock detected because PID no longer exists",
    )


def read_lock_record(path: Path) -> InstanceLockRecord | None:
    """從 lock file 讀取並反序列化執行個體資訊。"""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return InstanceLockRecord(**payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def write_lock_record(path: Path, record: InstanceLockRecord) -> None:
    """把執行個體資訊寫入 lock file。"""
    path.write_text(
        json.dumps(asdict(record), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def remove_lock_record(path: Path) -> None:
    """刪除指定 lock file；若不存在則忽略。"""
    if path.exists():
        path.unlink()


def create_lock_record(
    *,
    pid: int,
    started_at: datetime,
    instance_id: str,
) -> InstanceLockRecord:
    """建立可寫入 lock file 的執行個體紀錄。"""
    return InstanceLockRecord(
        pid=pid,
        started_at_utc=started_at.isoformat(),
        instance_id=instance_id,
    )
