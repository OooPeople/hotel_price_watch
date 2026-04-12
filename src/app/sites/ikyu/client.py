"""`ikyu` 頁面抓取介面與實際 HTTP client。"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.domain.value_objects import SearchDraft, WatchTarget
from app.sites.base import LookupDiagnostic


class IkyuHtmlClient(Protocol):
    """定義 `ikyu` adapter 需要的最小 HTML 抓取能力。"""

    def fetch_search_page(self, draft: SearchDraft) -> "HtmlFetchResult":
        """依據查詢草稿抓回對應的搜尋結果 HTML。"""

    def fetch_target_page(self, target: WatchTarget) -> "HtmlFetchResult":
        """依據正式 target 抓回對應方案頁面的 HTML。"""


class BrowserHtmlFetcher(Protocol):
    """定義 browser fallback 需要的最小抓取能力。"""

    def fetch_html(self, url: str) -> str:
        """用真實瀏覽器抓回動態載入後的 HTML。"""


class BrowserFallbackRequiredError(RuntimeError):
    """表示 HTTP-first 已被站方阻擋，需要改走瀏覽器補救。"""


class HtmlFetchError(ValueError):
    """表示單次 HTML 抓取失敗，並攜帶診斷資訊。"""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: tuple[LookupDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass(frozen=True, slots=True)
class HtmlFetchResult:
    """表示單次頁面抓取結果與對應診斷資訊。"""

    html: str
    diagnostics: tuple[LookupDiagnostic, ...] = ()


@dataclass(slots=True)
class LiveIkyuHtmlClient:
    """透過標準 HTTP request 抓取 `ikyu` 頁面 HTML。"""

    timeout_seconds: float = 20.0
    browser_fallback: BrowserHtmlFetcher | None = None
    enable_browser_fallback: bool = False
    browser_cooldown_seconds: float = 15.0
    prefer_browser_fallback_for_search: bool = False

    def fetch_search_page(self, draft: SearchDraft) -> HtmlFetchResult:
        """依草稿組出候選查詢頁 URL，並抓回 HTML。"""
        return self._fetch_html(
            _build_search_page_url(draft),
            prefer_browser_fallback=self.prefer_browser_fallback_for_search,
        )

    def fetch_target_page(self, target: WatchTarget) -> HtmlFetchResult:
        """依正式 target 組出方案頁 URL，並抓回 HTML。"""
        return self._fetch_html(_build_target_page_url(target))

    def _fetch_html(
        self,
        url: str,
        *,
        prefer_browser_fallback: bool = False,
    ) -> HtmlFetchResult:
        """先走 HTTP-first；若被 403 阻擋，再視設定決定是否改走 browser fallback。"""
        diagnostics: list[LookupDiagnostic] = []
        if prefer_browser_fallback:
            return self._fetch_html_via_browser_fallback(
                url=url,
                diagnostics=diagnostics,
                stage_name="browser_fallback_direct",
            )

        try:
            html = self._fetch_html_via_http(url)
            diagnostics.append(
                LookupDiagnostic(
                    stage="http_first",
                    status="success",
                    detail="HTTP-first 成功取得頁面內容。",
                )
            )
            return HtmlFetchResult(
                html=html,
                diagnostics=tuple(diagnostics),
            )
        except BrowserFallbackRequiredError as exc:
            diagnostics.append(
                LookupDiagnostic(
                    stage="http_first",
                    status="http_403",
                    detail=str(exc),
                )
            )
            if not self.enable_browser_fallback or self.browser_fallback is None:
                raise HtmlFetchError(
                    str(exc),
                    diagnostics=tuple(diagnostics),
                ) from exc

            if self.browser_cooldown_seconds > 0:
                diagnostics.append(
                    LookupDiagnostic(
                        stage="cooldown_before_browser",
                        status="waiting",
                        detail="偵測到 403 後進入冷卻，避免立刻再次觸發站方風控。",
                        cooldown_seconds=self.browser_cooldown_seconds,
                    )
                )
                time.sleep(self.browser_cooldown_seconds)

            return self._fetch_html_via_browser_fallback(
                url=url,
                diagnostics=diagnostics,
                stage_name="browser_fallback",
            )

    def _fetch_html_via_browser_fallback(
        self,
        *,
        url: str,
        diagnostics: list[LookupDiagnostic],
        stage_name: str,
    ) -> HtmlFetchResult:
        """直接走 browser fallback，避免先做額外的 HTTP-first 探測。"""
        if not self.enable_browser_fallback or self.browser_fallback is None:
            raise HtmlFetchError(
                "browser fallback 尚未啟用，無法直接以瀏覽器 session 取得頁面。",
                diagnostics=tuple(diagnostics),
            )

        try:
            html = self.browser_fallback.fetch_html(url)
        except ValueError as exc:
            diagnostics.append(
                LookupDiagnostic(
                    stage=stage_name,
                    status="failed",
                    detail=str(exc),
                )
            )
            raise HtmlFetchError(
                str(exc),
                diagnostics=tuple(diagnostics),
            ) from exc

        diagnostics.append(
            LookupDiagnostic(
                stage=stage_name,
                status="success",
                detail="直接以瀏覽器 session 取得頁面內容。",
            )
        )
        return HtmlFetchResult(
            html=html,
            diagnostics=tuple(diagnostics),
        )

    def _fetch_html_via_http(self, url: str) -> str:
        """送出 HTTP request 並以 UTF-8 文字回傳頁面內容。"""
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        referer_url = _build_referer_url(url)
        if referer_url != url:
            self._open_request(
                opener=opener,
                url=referer_url,
                referer=None,
                swallow_http_error=True,
            )

        response = self._open_request(
            opener=opener,
            url=url,
            referer=referer_url,
            swallow_http_error=False,
        )
        return response.read().decode("utf-8", errors="replace")

    def _open_request(
        self,
        *,
        opener: urllib.request.OpenerDirector,
        url: str,
        referer: str | None,
        swallow_http_error: bool,
    ):
        """用接近瀏覽器的 headers 開啟單次 HTTP request。"""
        request = urllib.request.Request(
            url=url,
            headers=_build_request_headers(referer=referer),
        )
        try:
            return opener.open(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as exc:
            if swallow_http_error:
                return exc
            if exc.code == 403:
                raise BrowserFallbackRequiredError(
                    "ikyu 拒絕目前的直接 HTTP 請求（403）；"
                    "這通常代表需要更像瀏覽器的抓取方式或後續 browser fallback。"
                ) from exc
            raise


def _build_search_page_url(draft: SearchDraft) -> str:
    """依查詢草稿建立 `ikyu` 候選列表頁 URL。"""
    parsed = urlparse(draft.seed_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))

    if draft.check_in_date is not None:
        query["cid"] = draft.check_in_date.strftime("%Y%m%d")
    if draft.nights is not None:
        query["si"] = str(draft.nights)
    if draft.people_count is not None:
        query["ppc"] = str(draft.people_count)
    if draft.room_count is not None:
        query["rc"] = str(draft.room_count)
    if draft.room_id is not None:
        query["rm"] = draft.room_id
    if draft.plan_id is not None:
        query["pln"] = draft.plan_id

    query["top"] = "rooms"
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc or "www.ikyu.com",
            normalized_path,
            "",
            urlencode(sorted(query.items())),
            "",
        )
    )


def _build_target_page_url(target: WatchTarget) -> str:
    """依正式 watch target 建立可抓單一方案快照的 URL。"""
    query = {
        "cid": target.check_in_date.strftime("%Y%m%d"),
        "rm": target.room_id,
        "pln": target.plan_id,
        "ppc": str(target.people_count),
        "rc": str(target.room_count),
        "si": str(target.nights),
        "top": "rooms",
    }
    return urlunparse(
        (
            "https",
            "www.ikyu.com",
            f"/zh-tw/{target.hotel_id}/",
            "",
            urlencode(sorted(query.items())),
            "",
        )
    )


def _build_referer_url(url: str) -> str:
    """由目標 URL 建立較接近真實瀏覽流程的 referer。"""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    query.pop("rm", None)
    query.pop("pln", None)
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path,
            "",
            urlencode(sorted(query.items())),
            "",
        )
    )


def _build_request_headers(*, referer: str | None) -> dict[str, str]:
    """建立模擬一般瀏覽器頁面載入的 request headers。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if referer is not None else "none",
        "Sec-Fetch-User": "?1",
    }
    if referer is not None:
        headers["Referer"] = referer
    return headers
