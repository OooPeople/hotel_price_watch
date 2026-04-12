"""集中處理 `ikyu` 頁面是否為阻擋頁的辨識邏輯。"""

from __future__ import annotations

import re


class IkyuBlockedPageError(ValueError):
    """表示目前取得的是 `ikyu` 站方阻擋頁，而非正常資料頁。"""


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
