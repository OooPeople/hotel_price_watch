"""Core domain models."""

from app.domain.entities import (
    CheckEvent,
    CheckResult,
    DebugArtifact,
    ErrorHandlingDecision,
    LatestCheckSnapshot,
    MonitorCheckArtifacts,
    NotificationDecision,
    NotificationDispatchResult,
    NotificationState,
    NotificationThrottleState,
    PriceHistoryEntry,
    PriceSnapshot,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import (
    Availability,
    CheckErrorCode,
    LogicalOperator,
    NotificationDeliveryStatus,
    NotificationEventKind,
    NotificationLeafKind,
    RuntimeStateEventKind,
    SourceKind,
    WatchRuntimeState,
)
from app.domain.notification_engine import compare_snapshots, evaluate_notification_rule
from app.domain.notification_rules import CompositeRule, NotificationRule, RuleLeaf
from app.domain.pricing import calculate_price_per_person_per_night
from app.domain.value_objects import SearchDraft, WatchTarget
from app.domain.watch_runtime_state import (
    derive_watch_runtime_state,
    describe_watch_runtime_state,
)

__all__ = [
    "Availability",
    "CheckEvent",
    "CheckErrorCode",
    "CheckResult",
    "CompositeRule",
    "DebugArtifact",
    "ErrorHandlingDecision",
    "LatestCheckSnapshot",
    "LogicalOperator",
    "MonitorCheckArtifacts",
    "NotificationDispatchResult",
    "NotificationDeliveryStatus",
    "NotificationDecision",
    "NotificationEventKind",
    "NotificationLeafKind",
    "NotificationRule",
    "NotificationState",
    "NotificationThrottleState",
    "PriceHistoryEntry",
    "PriceSnapshot",
    "RuntimeStateEvent",
    "RuntimeStateEventKind",
    "RuleLeaf",
    "SearchDraft",
    "SourceKind",
    "WatchItem",
    "WatchRuntimeState",
    "WatchTarget",
    "calculate_price_per_person_per_night",
    "compare_snapshots",
    "derive_watch_runtime_state",
    "describe_watch_runtime_state",
    "evaluate_notification_rule",
]
