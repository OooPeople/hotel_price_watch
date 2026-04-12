"""領域層共用列舉定義。"""

from enum import StrEnum


class Availability(StrEnum):
    """表示站點回傳的可訂狀態。"""

    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"
    PARSE_ERROR = "parse_error"
    TARGET_MISSING = "target_missing"


class SourceKind(StrEnum):
    """表示價格快照的資料來源。"""

    HTTP = "http"
    BROWSER = "browser"


class NotificationLeafKind(StrEnum):
    """表示 V1 UI 可選的單一通知規則。"""

    ANY_DROP = "any_drop"
    BELOW_TARGET_PRICE = "below_target_price"


class LogicalOperator(StrEnum):
    """表示複合通知規則的布林運算子。"""

    AND = "and"
    OR = "or"


class NotificationEventKind(StrEnum):
    """表示通知模組可能對外發送的事件類型。"""

    PRICE_DROP = "price_drop"
    BELOW_TARGET_PRICE = "below_target_price"
    BECAME_AVAILABLE = "became_available"
    PARSE_FAILED = "parse_failed"


class NotificationDeliveryStatus(StrEnum):
    """表示通知事件在實際分派後的結果狀態。"""

    NOT_REQUESTED = "not_requested"
    PENDING_DISPATCH = "pending_dispatch"
    SENT = "sent"
    THROTTLED = "throttled"
    FAILED = "failed"
    PARTIAL = "partial"


class CheckErrorCode(StrEnum):
    """表示 monitor 在檢查過程中可能記錄的錯誤代碼。"""

    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED_429 = "http_429"
    FORBIDDEN_403 = "http_403"
    PARSE_FAILED = "parse_failed"
    TARGET_MISSING = "target_missing"
