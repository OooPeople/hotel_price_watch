"""集中處理 `ikyu` 頁面是否為阻擋頁的辨識邏輯。"""

from __future__ import annotations

import re

from app.infrastructure.browser.page_strategy import (
    BrowserBlockedPageError,
    BrowserBlockingOutcome,
)


class IkyuBlockedPageError(BrowserBlockedPageError):
    """表示目前取得的是 `ikyu` 站方阻擋頁，而非正常資料頁。"""

    def __init__(self, message: str | None = None) -> None:
        """把 `ikyu` 阻擋頁轉成 generic browser blocking outcome。"""
        resolved_message = message or (
            "ikyu 已回傳阻擋頁面；目前連 browser fallback 都被站方防護攔下。"
        )
        super().__init__(
            resolved_message,
            outcome=BrowserBlockingOutcome(
                kind="forbidden",
                message=resolved_message,
                reason="ikyu_blocked_page",
            ),
        )


def raise_if_ikyu_block_page(html: str) -> None:
    """辨識 `ikyu` 的阻擋頁，避免把它誤當成正常資料頁。"""
    lowered = html.lower()
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    normalized_title = title.lower()

    blocked_title_markers = [
        "アクセスしようとしたページは表示できませんでした".lower(),
        "access denied",
        "forbidden",
    ]
    blocked_body_markers = [
        'meta name="robots" content="noindex"',
        'meta name="robots" content="nofollow"',
    ]

    if any(marker in normalized_title for marker in blocked_title_markers) or all(
        marker in lowered for marker in blocked_body_markers
    ):
        raise IkyuBlockedPageError(
            "ikyu 已回傳阻擋頁面；目前連 browser fallback 都被站方防護攔下。"
            " 這不是本機瀏覽器安裝問題，而是需要後續評估更接近人工操作的流程。"
        )
