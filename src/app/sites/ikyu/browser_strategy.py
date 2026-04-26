"""提供 `ikyu` 專用的 Chrome browser page strategy。"""

from __future__ import annotations

from urllib.parse import urlparse

from app.sites.ikyu.browser_matching import (
    extract_ikyu_browser_page_signature,
    ikyu_signatures_match_confidently,
    is_confident_ikyu_page_match,
    score_ikyu_browser_page,
)
from app.sites.ikyu.page_guards import raise_if_ikyu_block_page


class IkyuBrowserPageStrategy:
    """封裝 `ikyu` 在 CDP fetcher 內需要的頁面判斷規則。"""

    profile_start_url = "https://www.ikyu.com/"

    def raise_if_blocked_page(self, html: str) -> None:
        """辨識 `ikyu` 阻擋頁，避免誤當成正常資料頁。"""
        raise_if_ikyu_block_page(html)

    def is_ready_page(self, *, current_url: str, expected_url: str) -> bool:
        """判斷目前頁面是否已離開首頁並進到與目標飯店相符的 `ikyu` 頁面。"""
        current = urlparse(current_url)
        expected = urlparse(expected_url)
        profile_start = urlparse(self.profile_start_url)
        current_signature = extract_ikyu_browser_page_signature(current_url)
        expected_signature = extract_ikyu_browser_page_signature(expected_url)

        if not current.scheme or not current.netloc:
            return False
        if current.netloc != expected.netloc:
            return False
        if current.path.rstrip("/") == profile_start.path.rstrip("/"):
            return False
        if expected_signature.room_id is not None or expected_signature.plan_id is not None:
            return ikyu_signatures_match_confidently(
                left=current_signature,
                right=expected_signature,
            )
        return current.path.rstrip("/").startswith(expected.path.rstrip("/"))

    def score_page(self, current_url: str, *, expected_url: str) -> int:
        """依 `ikyu` URL signature 評分目前分頁是否接近目標頁。"""
        return score_ikyu_browser_page(
            current_url,
            expected_url=expected_url,
            profile_start_url=self.profile_start_url,
        )

    def page_signature(self, url: str):
        """回傳 `ikyu` browser page signature。"""
        return extract_ikyu_browser_page_signature(url)

    def is_confident_page_match(
        self,
        *,
        current_signature,
        expected_signature,
        score: int,
        minimum_score: int,
    ) -> bool:
        """判斷 `ikyu` 分頁是否足夠接近精確 room-plan target。"""
        return is_confident_ikyu_page_match(
            current_signature=current_signature,
            expected_signature=expected_signature,
            score=score,
            minimum_score=minimum_score,
        )
