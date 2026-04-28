"""單次 watch check pipeline 的資料 context。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.entities import (
    CheckResult,
    DebugArtifact,
    ErrorHandlingDecision,
    LatestCheckSnapshot,
    NotificationDecision,
    NotificationDispatchResult,
    NotificationState,
    PriceSnapshot,
    WatchItem,
)
from app.domain.enums import Availability, CheckErrorCode
from app.domain.value_objects import SearchDraft
from app.infrastructure.browser.chrome_models import ChromeTabCapture
from app.infrastructure.browser.page_strategy import BrowserBlockingOutcome
from app.sites.base import SiteAdapter


@dataclass(frozen=True, slots=True)
class CheckSetupContext:
    """保存 check 開始時一次性讀取與推導出的資料。"""

    watch_item: WatchItem
    draft: SearchDraft | None
    adapter: SiteAdapter
    operation_url: str
    latest_snapshot: LatestCheckSnapshot | None
    previous_snapshot: PriceSnapshot | None
    previous_effective_availability: Availability | None
    notification_state: NotificationState
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class CapturedCheckContext:
    """保存 capture 階段完成後交給 compare/policy 的資料。"""

    current_snapshot: PriceSnapshot
    capture: ChromeTabCapture | None
    error_code: CheckErrorCode | None
    debug_artifact: DebugArtifact | None
    browser_blocking_outcome: BrowserBlockingOutcome | None
    failure_detail: str | None


@dataclass(frozen=True, slots=True)
class EvaluatedCheckContext:
    """保存 compare、notification 與 error handling 後的中間結果。"""

    check_result: CheckResult
    notification_decision: NotificationDecision
    next_notification_state: NotificationState
    error_handling: ErrorHandlingDecision
    dispatch_result: NotificationDispatchResult | None = None
