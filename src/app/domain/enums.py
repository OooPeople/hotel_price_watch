"""Domain enums shared across the app."""

from enum import StrEnum


class Availability(StrEnum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"
    PARSE_ERROR = "parse_error"
    TARGET_MISSING = "target_missing"


class SourceKind(StrEnum):
    HTTP = "http"
    BROWSER = "browser"


class NotificationLeafKind(StrEnum):
    ANY_DROP = "any_drop"
    BELOW_TARGET_PRICE = "below_target_price"


class LogicalOperator(StrEnum):
    AND = "and"
    OR = "or"
