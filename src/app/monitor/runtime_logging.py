"""background runtime 使用的終端機診斷格式化工具。"""

from __future__ import annotations


def compact_log_value(value: str | None, *, max_length: int = 320) -> str:
    """壓縮終端機診斷值，避免換行或過長 URL 讓啟動輸出難讀。"""
    if value is None or not value.strip():
        return "-"
    compacted = " ".join(value.strip().split())
    if len(compacted) <= max_length:
        return compacted
    return f"{compacted[: max_length - 3]}..."
