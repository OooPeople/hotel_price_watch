from datetime import date

from app.domain.value_objects import SearchDraft, WatchTarget
from app.sites.ikyu.client import (
    BrowserFallbackRequiredError,
    LiveIkyuHtmlClient,
    _build_search_page_url,
    _build_target_page_url,
)


def test_build_search_page_url_updates_query_from_draft() -> None:
    url = _build_search_page_url(
        SearchDraft(
            seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )
    )

    assert "cid=20260918" in url
    assert "si=1" in url
    assert "ppc=2" in url
    assert "rc=1" in url
    assert "top=rooms" in url


def test_build_target_page_url_includes_room_and_plan_ids() -> None:
    url = _build_target_page_url(
        WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )
    )

    assert url.startswith("https://www.ikyu.com/zh-tw/00082173/")
    assert "cid=20260918" in url
    assert "rm=10191605" in url
    assert "pln=11035620" in url
    assert "si=1" in url


class _StubBrowserFetcher:
    """測試用的瀏覽器 fallback 替身。"""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch_html(self, url: str) -> str:
        """記錄抓取 URL，並回傳固定 HTML。"""
        self.urls.append(url)
        return "<html>browser-fallback</html>"


def test_live_client_uses_browser_fallback_on_http_403(monkeypatch) -> None:
    """HTTP-first 被 403 擋下時，若已啟用 fallback 應改走瀏覽器抓取。"""
    fallback = _StubBrowserFetcher()
    client = LiveIkyuHtmlClient(
        browser_fallback=fallback,
        enable_browser_fallback=True,
    )

    def raise_403(self: LiveIkyuHtmlClient, url: str) -> str:
        raise BrowserFallbackRequiredError("ikyu 403")

    monkeypatch.setattr(
        LiveIkyuHtmlClient,
        "_fetch_html_via_http",
        raise_403,
    )

    result = client.fetch_search_page(
        SearchDraft(
            seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )
    )

    assert result.html == "<html>browser-fallback</html>"
    assert tuple(diagnostic.stage for diagnostic in result.diagnostics) == (
        "http_first",
        "cooldown_before_browser",
        "browser_fallback",
    )
    assert len(fallback.urls) == 1
    assert "cid=20260918" in fallback.urls[0]


def test_live_client_keeps_original_error_when_fallback_is_disabled(monkeypatch) -> None:
    """未啟用 fallback 時，403 應維持明確錯誤而不是吞掉。"""
    client = LiveIkyuHtmlClient(enable_browser_fallback=False)

    def raise_403(self: LiveIkyuHtmlClient, url: str) -> str:
        raise BrowserFallbackRequiredError("ikyu 403")

    monkeypatch.setattr(
        LiveIkyuHtmlClient,
        "_fetch_html_via_http",
        raise_403,
    )

    try:
        client.fetch_search_page(
            SearchDraft(
                seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
                hotel_id="00082173",
                check_in_date=date(2026, 9, 18),
                check_out_date=date(2026, 9, 19),
                people_count=2,
                room_count=1,
            )
        )
    except ValueError as exc:
        assert str(exc) == "ikyu 403"
    else:
        raise AssertionError("expected ValueError when browser fallback is disabled")


def test_live_client_can_skip_http_first_for_search_preview(monkeypatch) -> None:
    """GUI preview 若設定直接走瀏覽器，應完全跳過 HTTP-first。"""
    fallback = _StubBrowserFetcher()
    client = LiveIkyuHtmlClient(
        browser_fallback=fallback,
        enable_browser_fallback=True,
        prefer_browser_fallback_for_search=True,
    )

    def fail_if_http_is_called(self: LiveIkyuHtmlClient, url: str) -> str:
        raise AssertionError("HTTP-first should be skipped for search preview")

    monkeypatch.setattr(
        LiveIkyuHtmlClient,
        "_fetch_html_via_http",
        fail_if_http_is_called,
    )

    result = client.fetch_search_page(
        SearchDraft(
            seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )
    )

    assert result.html == "<html>browser-fallback</html>"
    assert tuple(diagnostic.stage for diagnostic in result.diagnostics) == (
        "browser_fallback_direct",
    )


def test_live_client_target_snapshot_still_uses_http_first(monkeypatch) -> None:
    """即使 search preview 直走瀏覽器，target snapshot 仍保留原本 HTTP-first 行為。"""
    client = LiveIkyuHtmlClient(prefer_browser_fallback_for_search=True)

    def fake_http(self: LiveIkyuHtmlClient, url: str) -> str:
        return "<html>http</html>"

    monkeypatch.setattr(
        LiveIkyuHtmlClient,
        "_fetch_html_via_http",
        fake_http,
    )

    result = client.fetch_target_page(
        WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )
    )

    assert result.html == "<html>http</html>"
    assert tuple(diagnostic.stage for diagnostic in result.diagnostics) == ("http_first",)
