"""核心實體與 runtime 紀錄模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import (
    Availability,
    CheckErrorCode,
    NotificationDeliveryStatus,
    NotificationEventKind,
    RuntimeStateEventKind,
    SourceKind,
    WatchRuntimeState,
)
from app.domain.notification_rules import NotificationRule
from app.domain.value_objects import WatchTarget


@dataclass(frozen=True, slots=True)
class WatchItem:
    """表示純設定用途的監看項，不混入 runtime 狀態。"""

    id: str
    target: WatchTarget
    hotel_name: str
    room_name: str
    plan_name: str
    canonical_url: str
    notification_rule: NotificationRule
    scheduler_interval_seconds: int
    enabled: bool = True
    paused_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """驗證 watch 啟用旗標與暫停原因的組合，避免寫入矛盾狀態。"""
        if self.enabled and self.paused_reason == "manually_disabled":
            raise ValueError("enabled watch must not carry manually_disabled")
        if not self.enabled and self.paused_reason in {"manually_paused", "http_403"}:
            raise ValueError("disabled watch must not carry active pause reason")


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    """表示 site adapter 回傳的單次站點價格快照。"""

    display_price_text: str | None
    normalized_price_amount: Decimal | None
    currency: str | None
    availability: Availability
    source_kind: SourceKind


@dataclass(frozen=True, slots=True)
class PriceHistoryEntry:
    """表示 monitor 寫入 `price_history` 的成功價格紀錄。"""

    watch_item_id: str
    captured_at: datetime
    display_price_text: str
    normalized_price_amount: Decimal
    currency: str
    source_kind: SourceKind


@dataclass(frozen=True, slots=True)
class LatestCheckSnapshot:
    """表示列表頁會顯示的最新檢查摘要。"""

    watch_item_id: str
    checked_at: datetime
    availability: Availability
    normalized_price_amount: Decimal | None
    currency: str | None
    backoff_until: datetime | None = None
    is_degraded: bool = False
    consecutive_failures: int = 0
    last_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CheckEvent:
    """表示歷史頁與追蹤用途的單次檢查事件。"""

    watch_item_id: str
    checked_at: datetime
    availability: Availability
    event_kinds: tuple[str, ...]
    normalized_price_amount: Decimal | None = None
    currency: str | None = None
    error_code: str | None = None
    notification_status: NotificationDeliveryStatus = NotificationDeliveryStatus.NOT_REQUESTED
    sent_channels: tuple[str, ...] = ()
    throttled_channels: tuple[str, ...] = ()
    failed_channels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckResult:
    """表示 compare engine 對本次檢查做出的整理結果。"""

    checked_at: datetime
    current_snapshot: PriceSnapshot
    previous_snapshot: PriceSnapshot | None
    price_changed: bool
    availability_changed: bool
    price_dropped: bool
    became_available: bool
    parse_failed: bool


@dataclass(frozen=True, slots=True)
class NotificationState:
    """表示獨立於 watch 設定之外的通知去重狀態。"""

    watch_item_id: str
    last_notified_price: Decimal | None = None
    last_notified_availability: Availability | None = None
    last_notified_at: datetime | None = None
    consecutive_failures: int = 0
    consecutive_parse_failures: int = 0
    degraded_notified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    """表示通知規則評估後的事件與下一步去重狀態。"""

    event_kinds: tuple[NotificationEventKind, ...]
    next_state: NotificationState

    @property
    def should_notify(self) -> bool:
        """回傳這次檢查是否需要對外發送通知。"""
        return bool(self.event_kinds)


@dataclass(frozen=True, slots=True)
class NotificationDispatchResult:
    """表示通知 dispatcher 對各通道的實際發送結果。"""

    sent_channels: tuple[str, ...]
    throttled_channels: tuple[str, ...]
    failed_channels: tuple[str, ...]
    attempted_at: datetime
    failure_details: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class NotificationThrottleState:
    """表示通道級節流所需的最近成功發送時間。"""

    channel_name: str
    dedupe_key: str
    last_sent_at: datetime


@dataclass(frozen=True, slots=True)
class MonitorCheckArtifacts:
    """表示 monitor 單次檢查後要寫入的整理結果。"""

    latest_check_snapshot: LatestCheckSnapshot
    check_event: CheckEvent
    price_history_entry: PriceHistoryEntry | None = None


@dataclass(frozen=True, slots=True)
class ErrorHandlingDecision:
    """表示錯誤處理策略對本次檢查得出的退避與暫停決策。"""

    backoff_until: datetime | None = None
    should_pause: bool = False
    paused_reason: CheckErrorCode | None = None


@dataclass(frozen=True, slots=True)
class DebugArtifact:
    """表示解析失敗或異常時保存的除錯快照。"""

    watch_item_id: str
    captured_at: datetime
    reason: str
    payload_text: str
    source_url: str | None = None
    http_status: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeStateEvent:
    """表示 watch 在背景運作或人工操作中的正式狀態轉移事件。"""

    watch_item_id: str
    occurred_at: datetime
    event_kind: RuntimeStateEventKind
    from_state: WatchRuntimeState | None = None
    to_state: WatchRuntimeState | None = None
    detail_text: str | None = None
