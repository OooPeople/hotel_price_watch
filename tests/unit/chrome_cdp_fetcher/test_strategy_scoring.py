"""Browser page strategy 與分頁分數測試。"""

from __future__ import annotations

from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher

from .helpers import _build_ikyu_fetcher


def test_score_page_can_use_request_scoped_strategy() -> None:
    """單次 request 傳入 strategy 時，fetcher 應優先使用該 strategy。"""

    class _RequestScopedStrategy:
        """測試用 request strategy，固定回傳可辨識分數。"""

        profile_start_url = "https://request.example/"

        def raise_if_blocked_page(self, html: str) -> None:
            del html

        def is_ready_page(self, *, current_url: str, expected_url: str) -> bool:
            return current_url == expected_url

        def score_page(self, current_url: str, *, expected_url: str) -> int:
            del current_url, expected_url
            return 77

        def page_signature(self, url: str):
            return url

        def is_confident_page_match(
            self,
            *,
            current_signature,
            expected_signature,
            score: int,
            minimum_score: int,
        ) -> bool:
            del current_signature, expected_signature, minimum_score
            return score == 77

    fetcher = ChromeCdpHtmlFetcher()

    assert (
        fetcher._score_page(
            "https://request.example/current",
            expected_url="https://request.example/expected",
            page_strategy=_RequestScopedStrategy(),
        )
        == 77
    )

def test_score_page_prefers_matching_room_and_plan_query() -> None:
    """多個 ikyu 分頁同時存在時，應優先匹配同一組 rm/pln 的頁面。"""
    fetcher = _build_ikyu_fetcher()

    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )
    same_hotel_other_plan = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=99999999&ppc=2&rc=1&rm=88888888&si=1&st=1"
    )
    matching_plan_page = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    assert fetcher._score_page(
        matching_plan_page,
        expected_url=expected_url,
    ) > fetcher._score_page(
        same_hotel_other_plan,
        expected_url=expected_url,
    )
