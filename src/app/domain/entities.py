"""Primary entities and runtime records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import Availability, SourceKind
from app.domain.notification_rules import NotificationRule
from app.domain.value_objects import WatchTarget


@dataclass(frozen=True, slots=True)
class WatchItem:
    """Pure watch configuration stored separately from runtime state."""

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


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    """A normalized result from one site fetch."""

    watch_item_id: str
    captured_at: datetime
    display_price_text: str
    normalized_price_amount: Decimal
    currency: str
    availability: Availability
    source_kind: SourceKind


@dataclass(frozen=True, slots=True)
class LatestCheckSnapshot:
    """Latest runtime summary displayed in the list view."""

    watch_item_id: str
    checked_at: datetime
    availability: Availability
    normalized_price_amount: Decimal | None
    currency: str | None
    backoff_until: datetime | None = None
    is_degraded: bool = False
    last_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CheckEvent:
    """One check attempt stored for history/audit purposes."""

    watch_item_id: str
    checked_at: datetime
    availability: Availability
    event_kind: str
    normalized_price_amount: Decimal | None = None
    currency: str | None = None
    error_code: str | None = None
    notification_sent: bool = False


@dataclass(frozen=True, slots=True)
class NotificationState:
    """Deduplication state kept outside the watch configuration."""

    watch_item_id: str
    last_notified_price: Decimal | None = None
    last_notified_availability: Availability | None = None
    last_notified_at: datetime | None = None
