"""runtime 內部協調流程共用的結果模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WatchCheckOutcome:
    """描述一次 watch 檢查完成後，協調流程需要接續處理的摘要。"""

    persisted: bool
    tab_id: str | None = None
    tab_url: str | None = None
    backoff_until: datetime | None = None
    removed_from_scheduler: bool = False
    failure_detail: str | None = None
