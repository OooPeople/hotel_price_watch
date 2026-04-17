"""定義 Chrome page strategy 介面，隔離站點特有的 browser 判斷規則。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class BrowserBlockingOutcome:
    """描述站點判定的阻擋型態，供 runtime 統一轉成監看錯誤。"""

    kind: str
    message: str
    reason: str = "blocked_page"


class BrowserBlockedPageError(ValueError):
    """表示 browser page strategy 判定目前頁面為站方阻擋頁。"""

    def __init__(
        self,
        message: str | None = None,
        *,
        outcome: BrowserBlockingOutcome | None = None,
    ) -> None:
        """保存阻擋 outcome，讓 runtime 不再依賴錯誤訊息片段判斷。"""
        resolved_message = message or "browser page strategy detected a blocked page"
        self.outcome = outcome or BrowserBlockingOutcome(
            kind="forbidden",
            message=resolved_message,
        )
        super().__init__(resolved_message)


class BrowserPageStrategy(Protocol):
    """描述 CDP fetcher 需要的站點 browser page 能力。"""

    profile_start_url: str

    def raise_if_blocked_page(self, html: str) -> None:
        """若 HTML 是站方阻擋頁，應丟出站點專用錯誤。"""

    def is_ready_page(self, *, current_url: str, expected_url: str) -> bool:
        """判斷目前分頁是否已進入可讀取目標內容的頁面。"""

    def score_page(self, current_url: str, *, expected_url: str) -> int:
        """評分目前分頁與目標 URL 的接近程度。"""

    def page_signature(self, url: str):
        """回傳目前分頁 URL 的站點比對 signature。"""

    def is_confident_page_match(
        self,
        *,
        current_signature,
        expected_signature,
        score: int,
        minimum_score: int,
    ) -> bool:
        """判斷 signature 與分數是否足以沿用既有分頁。"""


class BasicBrowserPageStrategy:
    """提供無站點假設的基本 browser page strategy。"""

    profile_start_url = "about:blank"

    def raise_if_blocked_page(self, html: str) -> None:
        """基本策略不辨識站方阻擋頁。"""
        del html

    def is_ready_page(self, *, current_url: str, expected_url: str) -> bool:
        """以同 host 且 path 接近作為基本 ready page 判斷。"""
        current = urlparse(current_url)
        expected = urlparse(expected_url)
        if not current.scheme or not current.netloc:
            return False
        return current.netloc == expected.netloc and current.path.rstrip("/").startswith(
            expected.path.rstrip("/")
        )

    def score_page(self, current_url: str, *, expected_url: str) -> int:
        """提供站點無關的 URL 相似度評分。"""
        current = urlparse(current_url)
        expected = urlparse(expected_url)
        if current_url == expected_url:
            return 100
        if current_url in {"about:blank", ""}:
            return 1
        if not current.scheme or not current.netloc:
            return 0
        if current.netloc != expected.netloc:
            return 0
        if current.path.rstrip("/") == expected.path.rstrip("/"):
            return 20
        if current.path.rstrip("/").startswith(expected.path.rstrip("/")):
            return 10
        return 1

    def page_signature(self, url: str):
        """基本策略直接使用 URL 作為 signature。"""
        return url

    def is_confident_page_match(
        self,
        *,
        current_signature,
        expected_signature,
        score: int,
        minimum_score: int,
    ) -> bool:
        """基本策略只看分數門檻。"""
        del current_signature, expected_signature
        return score >= minimum_score
