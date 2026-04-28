"""Chrome 分頁 capture 與 reload 行為測試。"""

from __future__ import annotations

import pytest

from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher

from .helpers import _build_ikyu_fetcher


def test_capture_for_url_can_capture_without_reload_after_navigation(monkeypatch) -> None:
    """啟動恢復後擷取應只導到目標 URL，不應再額外重新整理一次。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&top=rooms"
    )

    class _Page:
        def __init__(self) -> None:
            self.url = "about:blank"
            self.stable_id = "target-tab"
            self.goto_calls: list[str] = []
            self.reload_count = 0

        def is_closed(self) -> bool:
            return False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            self.goto_calls.append(url)
            self.url = url

        def reload(self, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            self.reload_count += 1

        def title(self) -> str:
            return "IKYU"

        def evaluate(self, script: str):
            del script
            return None

        def content(self) -> str:
            return "<html><body>ready</body></html>"

    class _Context:
        def __init__(self, page: _Page) -> None:
            self.pages = [page]

        def new_page(self):
            return self.pages[0]

    class _Browser:
        def __init__(self, context: _Context) -> None:
            self.contexts = [context]

    page = _Page()
    context = _Context(page)

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_get_page_stable_id",
        lambda self, page: page.stable_id,
    )
    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_connect_playwright_browser",
        lambda self: (_Browser(context), type("P", (), {"stop": lambda self: None})()),
    )

    capture = fetcher.capture_for_url(
        expected_url=expected_url,
        fallback_url=expected_url,
        preferred_tab_id="target-tab",
        reload=False,
    )

    assert page.goto_calls == [expected_url]
    assert page.reload_count == 0
    assert capture.tab.tab_id == "target-tab"
    assert capture.tab.url == expected_url

def test_refresh_capture_for_url_still_reload_after_navigation(monkeypatch) -> None:
    """正式排程檢查仍應在導到目標 URL 後刷新頁面再擷取。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&top=rooms"
    )

    class _Page:
        def __init__(self) -> None:
            self.url = "about:blank"
            self.stable_id = "target-tab"
            self.goto_calls: list[str] = []
            self.reload_count = 0

        def is_closed(self) -> bool:
            return False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            self.goto_calls.append(url)
            self.url = url

        def reload(self, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            self.reload_count += 1

        def title(self) -> str:
            return "IKYU"

        def evaluate(self, script: str):
            del script
            return None

        def content(self) -> str:
            return "<html><body>ready</body></html>"

    class _Context:
        def __init__(self, page: _Page) -> None:
            self.pages = [page]

        def new_page(self):
            return self.pages[0]

    class _Browser:
        def __init__(self, context: _Context) -> None:
            self.contexts = [context]

    page = _Page()
    context = _Context(page)

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_get_page_stable_id",
        lambda self, page: page.stable_id,
    )
    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_connect_playwright_browser",
        lambda self: (_Browser(context), type("P", (), {"stop": lambda self: None})()),
    )

    capture = fetcher.refresh_capture_for_url(
        expected_url=expected_url,
        fallback_url=expected_url,
        preferred_tab_id="target-tab",
    )

    assert page.goto_calls == [expected_url]
    assert page.reload_count == 1
    assert capture.tab.tab_id == "target-tab"
    assert capture.tab.url == expected_url

def test_capture_page_uses_injected_page_strategy() -> None:
    """抓取分頁內容時，應透過注入的 strategy 判斷阻擋頁。"""

    class _BlockedPageStrategy:
        """測試用 strategy，固定把頁面判定為 blocked。"""

        profile_start_url = "https://strategy.example/"

        def raise_if_blocked_page(self, html: str) -> None:
            raise ValueError(f"blocked by strategy: {html}")

        def is_ready_page(self, *, current_url: str, expected_url: str) -> bool:
            return current_url == expected_url

        def score_page(self, current_url: str, *, expected_url: str) -> int:
            return 100 if current_url == expected_url else 0

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
            del minimum_score
            return current_signature == expected_signature and score > 0

    class _Page:
        url = "https://strategy.example/target"

        def content(self) -> str:
            return "<html>blocked</html>"

    fetcher = ChromeCdpHtmlFetcher(page_strategy=_BlockedPageStrategy())

    with pytest.raises(ValueError, match="blocked by strategy"):
        fetcher._capture_page(page=_Page())
