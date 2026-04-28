"""monitor error handling 與 backoff policy 測試。"""

from __future__ import annotations

from datetime import datetime

from app.domain.enums import CheckErrorCode
from app.monitor.policies import decide_error_handling


def test_rate_limited_backoff_caps_at_two_hours() -> None:
    """驗證 rate limited 連續失敗的退避時間最高限制為兩小時。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.RATE_LIMITED_429,
        consecutive_failures=5,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 12, 0, 0)
    assert decision.should_pause is False

def test_forbidden_pauses_watch_item() -> None:
    """驗證 forbidden 類阻擋會建議暫停 watch 而不是只做 backoff。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.FORBIDDEN_403,
        consecutive_failures=1,
    )

    assert decision.should_pause is True
    assert decision.paused_reason is CheckErrorCode.FORBIDDEN_403
    assert decision.backoff_until is None

def test_network_error_backoff_caps_at_thirty_minutes() -> None:
    """驗證網路錯誤連續失敗的退避時間最高限制為三十分鐘。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.NETWORK_TIMEOUT,
        consecutive_failures=4,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 10, 30, 0)

def test_parse_failed_backoff_matches_short_retry_strategy() -> None:
    """驗證 parse_failed 也會進入短退避，而不是高頻重試。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.PARSE_FAILED,
        consecutive_failures=3,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 10, 20, 0)
    assert decision.should_pause is False

def test_target_missing_uses_longer_backoff_strategy() -> None:
    """目標房型方案消失時應進入較長退避，避免近入住日高頻重試。"""
    decision = decide_error_handling(
        checked_at=datetime(2026, 4, 12, 10, 0, 0),
        error_code=CheckErrorCode.TARGET_MISSING,
        consecutive_failures=4,
    )

    assert decision.backoff_until == datetime(2026, 4, 12, 14, 0, 0)
    assert decision.should_pause is False
