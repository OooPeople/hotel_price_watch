"""GUI 顯示格式化 helper 測試。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.web.view_formatters import (
    format_datetime_for_display,
    format_datetime_lines_for_display,
)


def test_format_datetime_for_display_supports_24_hour_time() -> None:
    """24 小時制應使用 `HH:MM` 顯示時間。"""
    value = datetime(2026, 4, 21, 15, 30, tzinfo=timezone.utc)

    text = format_datetime_for_display(value, use_24_hour_time=True)

    assert "AM" not in text
    assert "PM" not in text


def test_format_datetime_for_display_supports_12_hour_time() -> None:
    """12 小時制應使用中文上午 / 下午顯示時間。"""
    value = datetime(2026, 4, 21, 15, 30, tzinfo=timezone.utc)

    text = format_datetime_for_display(value, use_24_hour_time=False)

    assert "上午" in text or "下午" in text
    assert "AM" not in text
    assert "PM" not in text


def test_format_datetime_lines_for_display_moves_period_to_time_line() -> None:
    """摘要卡片分行時，上午 / 下午應留在時間行。"""
    value = datetime(2026, 4, 21, 15, 30, tzinfo=timezone.utc)

    date_text, time_text = format_datetime_lines_for_display(
        value,
        use_24_hour_time=False,
    )

    assert "上午" not in date_text
    assert "下午" not in date_text
    assert "上午" in time_text or "下午" in time_text
    assert "AM" not in time_text
    assert "PM" not in time_text
