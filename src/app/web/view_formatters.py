"""本機 GUI renderer 共用的顯示格式化 helper。"""

from __future__ import annotations

from datetime import datetime


def format_datetime_for_display(
    value: datetime | None,
    *,
    use_24_hour_time: bool = True,
) -> str:
    """將 aware datetime 轉成使用者電腦目前的本地時間格式。"""
    if value is None:
        return "none"
    local_value = value.astimezone()
    if use_24_hour_time:
        return local_value.strftime("%Y/%m/%d %H:%M")

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return f"{local_value:%Y/%m/%d} {period_text} {hour:02d}:{local_value:%M}"


def format_datetime_lines_for_display(
    value: datetime | None,
    *,
    use_24_hour_time: bool = True,
) -> tuple[str, str]:
    """將 datetime 拆成日期與時間兩段，供摘要卡片穩定分行顯示。"""
    if value is None:
        return ("none", "")

    local_value = value.astimezone()
    date_text = local_value.strftime("%Y/%m/%d")
    if use_24_hour_time:
        return (date_text, local_value.strftime("%H:%M"))

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return (date_text, f"{period_text} {hour:02d}:{local_value:%M}")
