"""Chrome CDP fallback 的單元測試。"""

from __future__ import annotations

import json

import pytest

from app.infrastructure.browser.chrome_cdp_fetcher import (
    ChromeCdpHtmlFetcher,
    _build_chrome_launch_command,
    _prepare_chrome_profile,
)
from app.sites.ikyu.browser_strategy import IkyuBrowserPageStrategy


def _build_ikyu_fetcher(**kwargs) -> ChromeCdpHtmlFetcher:
    """建立使用 `ikyu` browser strategy 的 fetcher 測試實例。"""
    return ChromeCdpHtmlFetcher(page_strategy=IkyuBrowserPageStrategy(), **kwargs)


def test_fetch_html_attaches_to_existing_cdp_session(monkeypatch) -> None:
    """若 CDP 端點可用，應附著既有 Chrome session 並等待人工導頁結果。"""
    fetcher = _build_ikyu_fetcher()

    class _Page:
        url = "about:blank"

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.url = url

        def is_closed(self) -> bool:
            return False

    class _Context:
        def __init__(self) -> None:
            self.pages = [_Page()]

    class _Browser:
        def __init__(self) -> None:
            self.contexts = [_Context()]
            self.closed = False

        def close(self) -> None:
            self.closed = True

    browser = _Browser()

    class _Chromium:
        def connect_over_cdp(self, endpoint: str):
            assert endpoint == "http://127.0.0.1:9222"
            return browser

    class _Playwright:
        chromium = _Chromium()

    class _Manager:
        def __enter__(self):
            return _Playwright()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_ensure_debuggable_chrome",
        lambda self, start_url=None: None,
    )
    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_wait_for_manual_resolution",
        lambda self, context, initial_page, expected_url, page_strategy=None: (
            "<html>ok</html>"
        ),
    )
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _Manager())

    html = fetcher.fetch_html("https://www.ikyu.com/zh-tw/00082173/")

    assert html == "<html>ok</html>"
    assert browser.closed is False


def test_ensure_debuggable_chrome_raises_when_chrome_is_missing(monkeypatch) -> None:
    """找不到 Chrome 時，應回清楚訊息而不是靜默失敗。"""
    fetcher = ChromeCdpHtmlFetcher()

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_is_cdp_ready",
        lambda self: False,
    )
    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_find_chrome_path",
        lambda self: None,
    )

    with pytest.raises(ValueError, match="找不到可用的 Chrome"):
        fetcher._ensure_debuggable_chrome()


def test_build_chrome_launch_command_contains_hardening_flags(tmp_path) -> None:
    """啟動命令應包含降低第一次啟動雜訊的核心參數。"""
    command = _build_chrome_launch_command(
        chrome_path=r"C:\Chrome\chrome.exe",
        user_data_dir=tmp_path / "profile",
        url="https://www.ikyu.com/",
    )

    assert "--remote-debugging-port=9222" in command
    assert "--no-default-browser-check" in command
    assert "--no-first-run" in command
    assert "--disable-background-networking" in command
    assert "--disable-sync" in command
    assert "--lang=zh-TW" in command


def test_prepare_chrome_profile_writes_preferences_files(tmp_path) -> None:
    """建立 profile 時應先寫出 Preferences 與 Local State。"""
    profile_dir = tmp_path / "profile"

    _prepare_chrome_profile(profile_dir)

    assert (profile_dir / "Default" / "Preferences").exists()
    assert (profile_dir / "Local State").exists()


def test_prepare_chrome_profile_preserves_existing_preferences(tmp_path) -> None:
    """已存在的專用 profile 設定不應在每次啟動時被覆寫。"""
    profile_dir = tmp_path / "profile"
    default_dir = profile_dir / "Default"
    default_dir.mkdir(parents=True)
    preferences_path = default_dir / "Preferences"
    local_state_path = profile_dir / "Local State"
    preferences_path.write_text(
        json.dumps({"profile": {"name": "custom-profile"}}),
        encoding="utf-8",
    )
    local_state_path.write_text(
        json.dumps({"browser": {"enabled_labs_experiments": ["custom@1"]}}),
        encoding="utf-8",
    )

    _prepare_chrome_profile(profile_dir)

    assert json.loads(preferences_path.read_text(encoding="utf-8")) == {
        "profile": {"name": "custom-profile"}
    }
    assert json.loads(local_state_path.read_text(encoding="utf-8")) == {
        "browser": {"enabled_labs_experiments": ["custom@1"]}
    }


def test_open_profile_window_uses_bootstrap_homepage(monkeypatch, tmp_path) -> None:
    """手動建立 session 時，應先從 `ikyu` 首頁啟動專用 Chrome。"""
    fetcher = _build_ikyu_fetcher(
        user_data_dir=tmp_path / "profile",
        launch_timeout_seconds=0.0,
    )
    launched: list[list[str]] = []

    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_is_cdp_ready",
        lambda self: False,
    )
    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_find_chrome_path",
        lambda self: r"C:\Chrome\chrome.exe",
    )
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda command, stdout=None, stderr=None: launched.append(command),
    )

    with pytest.raises(ValueError, match="CDP 端點仍未就緒"):
        fetcher.open_profile_window()

    assert launched
    assert launched[0][-1] == "https://www.ikyu.com/"


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
