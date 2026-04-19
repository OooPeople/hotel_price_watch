"""Chrome 分頁 matching 與 URL 相似度判定。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.infrastructure.browser.page_strategy import BrowserPageStrategy


@dataclass(frozen=True, slots=True)
class ChromePageMatcher:
    """依 browser page strategy 從目前 Chrome 分頁中選出最適合的目標頁。"""

    minimum_confident_match_score: int
    get_page_stable_id: Callable[[object], str]

    def find_best_page(
        self,
        context,
        *,
        expected_url: str,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy: BrowserPageStrategy,
    ):
        """在目前所有分頁中挑出最接近目標 URL 的頁面。"""
        best_page = None
        best_score = -1
        best_signature = None
        expected_signature = page_strategy.page_signature(expected_url)
        excluded_ids = set(excluded_tab_ids)
        for page in context.pages:
            if page.is_closed():
                continue
            if excluded_ids and self.get_page_stable_id(page) in excluded_ids:
                continue
            score = self.score_page(
                page.url,
                expected_url=expected_url,
                page_strategy=page_strategy,
            )
            if score > best_score:
                best_page = page
                best_score = score
                best_signature = page_strategy.page_signature(page.url)
        if (
            best_score <= 0
            or best_signature is None
            or not self.is_confident_page_match(
                current_signature=best_signature,
                expected_signature=expected_signature,
                score=best_score,
                page_strategy=page_strategy,
            )
        ):
            return None
        return best_page

    def score_page(
        self,
        current_url: str,
        *,
        expected_url: str,
        page_strategy: BrowserPageStrategy,
    ) -> int:
        """依 URL 相似度為目前分頁評分。"""
        return page_strategy.score_page(current_url, expected_url=expected_url)

    def is_confident_page_match(
        self,
        *,
        current_signature,
        expected_signature,
        score: int,
        page_strategy: BrowserPageStrategy,
    ) -> bool:
        """判斷目前分頁是否足夠接近目標條件。"""
        return page_strategy.is_confident_page_match(
            current_signature=current_signature,
            expected_signature=expected_signature,
            score=score,
            minimum_score=self.minimum_confident_match_score,
        )
