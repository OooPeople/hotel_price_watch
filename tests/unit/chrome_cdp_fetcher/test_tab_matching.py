"""Chrome 分頁選擇、matching 與 re-navigation 測試。"""

from __future__ import annotations

from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher

from .helpers import _build_ikyu_fetcher


def test_get_or_create_page_prefers_existing_target_like_page() -> None:
    """附著既有 session 時，應優先使用最接近目標頁的分頁。"""
    fetcher = _build_ikyu_fetcher()

    class _Page:
        def __init__(self, url: str) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page("https://www.ikyu.com/"),
                _Page("https://www.ikyu.com/zh-tw/00082173/?top=rooms"),
            ]

    page = fetcher._get_or_create_page(
        _Context(),
        expected_url="https://www.ikyu.com/zh-tw/00082173/?adc=1",
    )

    assert page.url == "https://www.ikyu.com/zh-tw/00082173/?top=rooms"

def test_get_page_by_tab_id_uses_stable_page_key(monkeypatch) -> None:
    """依分頁識別碼抓取時，不應再依賴 context.pages 的 index 順序。"""
    fetcher = _build_ikyu_fetcher()

    class _Page:
        def __init__(self, url: str, stable_id: str) -> None:
            self.url = url
            self.stable_id = stable_id

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page("https://www.ikyu.com/zh-tw/00082173/?top=rooms", "target-2"),
                _Page("https://www.ikyu.com/", "target-1"),
            ]

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_get_page_stable_id",
        lambda self, page: page.stable_id,
    )

    page = fetcher._get_page_by_tab_id(_Context(), "target-1")

    assert page is not None
    assert page.url == "https://www.ikyu.com/"

def test_preferred_tab_id_must_match_expected_room_plan(monkeypatch) -> None:
    """preferred tab 只是短期 hint；URL 不符合精確目標時不可沿用。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    class _Page:
        def __init__(self, url: str, stable_id: str) -> None:
            self.url = url
            self.stable_id = stable_id

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page(
                    "https://www.ikyu.com/zh-tw/00082173/"
                    "?adc=1&cid=20260918&pln=99999999&ppc=2&rc=1&rm=88888888",
                    "stale-tab",
                ),
            ]

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_get_page_stable_id",
        lambda self, page: page.stable_id,
    )

    page = fetcher._get_confident_page_by_tab_id(
        _Context(),
        "stale-tab",
        expected_url=expected_url,
    )

    assert page is None

def test_ensure_page_is_on_target_navigates_wrong_room_plan() -> None:
    """同飯店但 room/plan 不同時，應重新導到精確目標 URL。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    class _Page:
        def __init__(self) -> None:
            self.url = (
                "https://www.ikyu.com/zh-tw/00082173/"
                "?adc=1&cid=20260918&pln=99999999&ppc=2&rc=1&rm=88888888"
            )
            self.goto_calls: list[str] = []

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            self.goto_calls.append(url)
            self.url = url

    page = _Page()

    fetcher._ensure_page_is_on_target(
        page=page,
        expected_url=expected_url,
        fallback_url=expected_url,
    )

    assert page.goto_calls == [expected_url]

def test_ensure_tab_reuses_preferred_page_when_it_needs_renavigation(monkeypatch) -> None:
    """preferred tab 屬於同一 watch 時，即使目前 URL 不吻合也應重導而非開新分頁。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&top=rooms"
    )

    class _Page:
        def __init__(self) -> None:
            self.url = "https://www.ikyu.com/"
            self.stable_id = "owned-tab"
            self.goto_calls: list[str] = []

        def is_closed(self) -> bool:
            return False

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            self.goto_calls.append(url)
            self.url = url

        def title(self) -> str:
            return "IKYU"

        def evaluate(self, script: str):
            del script
            return None

    class _Context:
        def __init__(self, page: _Page) -> None:
            self.pages = [page]
            self.new_page_count = 0

        def new_page(self):
            self.new_page_count += 1
            raise AssertionError("should reuse preferred tab")

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

    summary = fetcher.ensure_tab_for_url(
        expected_url=expected_url,
        fallback_url=expected_url,
        preferred_tab_id="owned-tab",
    )

    assert page.goto_calls == [expected_url]
    assert context.new_page_count == 0
    assert summary.tab_id == "owned-tab"
    assert summary.url == expected_url

def test_find_best_page_prefers_matching_query_over_same_hotel_root() -> None:
    """同飯店多分頁存在時，應優先選到條件最接近的房型方案頁。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    class _Page:
        def __init__(self, url: str) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page("https://www.ikyu.com/zh-tw/00082173/?top=rooms"),
                _Page(
                    "https://www.ikyu.com/zh-tw/00082173/"
                    "?adc=1&cid=20260918&pln=99999999&ppc=2&rc=1&rm=88888888&si=1&st=1"
                ),
                _Page(expected_url),
            ]

    best_page = fetcher._find_best_page(_Context(), expected_url=expected_url)

    assert best_page is not None
    assert best_page.url == expected_url

def test_find_best_page_rejects_same_hotel_with_wrong_room_plan() -> None:
    """若同飯店分頁的 room/plan 不吻合，應回傳 None 走保守 fallback。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    class _Page:
        def __init__(self, url: str) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page(
                    "https://www.ikyu.com/zh-tw/00082173/"
                    "?adc=1&cid=20260918&pln=99999999&ppc=2&rc=1&rm=88888888&si=1&st=1"
                ),
            ]

    best_page = fetcher._find_best_page(_Context(), expected_url=expected_url)

    assert best_page is None

def test_find_best_page_rejects_low_confidence_hotel_root_page() -> None:
    """若只有同飯店根頁，應回傳 None 讓 runtime 自行導向精確目標頁。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    class _Page:
        def __init__(self, url: str) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page("https://www.ikyu.com/zh-tw/00082173/?top=rooms"),
            ]

    best_page = fetcher._find_best_page(_Context(), expected_url=expected_url)

    assert best_page is None

def test_find_best_page_skips_excluded_tab_ids(monkeypatch) -> None:
    """恢復多個 watch 分頁時，已被前一個 watch 佔用的 tab 不應再次被沿用。"""
    fetcher = _build_ikyu_fetcher()
    expected_url = (
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    class _Page:
        def __init__(self, url: str, stable_id: str) -> None:
            self.url = url
            self.stable_id = stable_id

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [
                _Page(expected_url, "tab-1"),
                _Page(
                    "https://www.ikyu.com/zh-tw/00082173/"
                    "?adc=1&cid=20260918&pln=11035620&ppc=2&rc=1&rm=10191605&si=1&st=1"
                    "&extra=1",
                    "tab-2",
                ),
            ]

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_get_page_stable_id",
        lambda self, page: page.stable_id,
    )

    best_page = fetcher._find_best_page(
        _Context(),
        expected_url=expected_url,
        excluded_tab_ids=("tab-1",),
    )

    assert best_page is not None
    assert best_page.stable_id == "tab-2"
