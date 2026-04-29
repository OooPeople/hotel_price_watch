"""SQLite repository façade 的相容匯出入口。

新實作請直接放在對應 repository / record module，不要再把 SQL 或流程塞回此檔。
"""

from __future__ import annotations

from app.infrastructure.db.app_settings_repository import SqliteAppSettingsRepository
from app.infrastructure.db.runtime_repositories import (
    SqliteNotificationThrottleStateRepository,
    SqliteRuntimeFragmentQueryRepository,
    SqliteRuntimeHistoryQueryRepository,
    SqliteRuntimeWriteRepository,
)
from app.infrastructure.db.runtime_repository_compat import SqliteRuntimeRepository
from app.infrastructure.db.watch_item_repository import SqliteWatchItemRepository

__all__ = [
    "SqliteAppSettingsRepository",
    "SqliteNotificationThrottleStateRepository",
    "SqliteRuntimeFragmentQueryRepository",
    "SqliteRuntimeHistoryQueryRepository",
    "SqliteRuntimeRepository",
    "SqliteRuntimeWriteRepository",
    "SqliteWatchItemRepository",
]
