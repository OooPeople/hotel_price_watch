"""monitor runtime 使用的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ScheduledWatch:
    """表示 scheduler 追蹤中的單一監看項排程狀態。"""

    watch_item_id: str
    interval_seconds: int
    next_run_at: datetime


@dataclass(frozen=True, slots=True)
class WorkerAssignment:
    """表示 scheduler 指派給 worker 的單次工作。"""

    watch_item_id: str
    scheduled_at: datetime
    started_at: datetime


@dataclass(frozen=True, slots=True)
class WorkerState:
    """表示目前正在執行中的 worker 狀態。"""

    watch_item_id: str
    started_at: datetime
    scheduled_at: datetime
