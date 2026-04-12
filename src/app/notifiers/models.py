"""通知層共用資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    """表示要送往各種通知通道的標準化訊息。"""

    watch_item_id: str
    dedupe_key: str
    title: str
    body: str
    tags: tuple[str, ...] = ()
