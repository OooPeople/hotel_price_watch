"""Chrome CDP attach 與分頁列表測試。"""

from __future__ import annotations

import json

from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher

from .helpers import _build_ikyu_fetcher


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

def test_list_tabs_uses_fast_cdp_target_list(monkeypatch) -> None:
    """列分頁摘要應優先使用 CDP HTTP targets，避免只為列表頁啟動 Playwright。"""
    fetcher = _build_ikyu_fetcher()

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "id": "target-1",
                        "type": "page",
                        "title": "IKYU Hotel",
                        "url": "https://www.ikyu.com/zh-tw/00082173/",
                    },
                    {
                        "id": "worker-1",
                        "type": "service_worker",
                        "title": "ignored",
                        "url": "https://www.ikyu.com/sw.js",
                    },
                ]
            ).encode("utf-8")

    monkeypatch.setattr(
        "app.infrastructure.browser.chrome_cdp_fetcher.urlopen",
        lambda url, timeout: _Response(),
    )
    monkeypatch.setattr(
        ChromeCdpHtmlFetcher,
        "_connect_playwright_browser",
        lambda self: (_ for _ in ()).throw(AssertionError("unexpected Playwright attach")),
    )

    tabs = fetcher.list_tabs()

    assert len(tabs) == 1
    assert tabs[0].tab_id == "target-1"
    assert tabs[0].title == "IKYU Hotel"
    assert tabs[0].url == "https://www.ikyu.com/zh-tw/00082173/"
    assert tabs[0].visibility_state is None
