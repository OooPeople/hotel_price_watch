"""以 Chrome CDP 連線既有真人瀏覽器 session 的 HTML 抓取器。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from app.infrastructure.browser.chrome_cdp_connection import ChromeCdpConnector
from app.infrastructure.browser.chrome_models import ChromeTabCapture, ChromeTabSummary
from app.infrastructure.browser.chrome_page_capture import ChromePageCaptureHelper
from app.infrastructure.browser.chrome_page_matcher import ChromePageMatcher
from app.infrastructure.browser.chrome_profile_launcher import (
    ChromeProfileLauncher,
)
from app.infrastructure.browser.chrome_profile_launcher import (
    build_chrome_launch_command as _build_chrome_launch_command,
)
from app.infrastructure.browser.chrome_profile_launcher import (
    prepare_chrome_profile as _prepare_chrome_profile,
)
from app.infrastructure.browser.page_strategy import (
    BasicBrowserPageStrategy,
    BrowserPageStrategy,
)

__all__ = [
    "ChromeCdpHtmlFetcher",
    "ChromeTabCapture",
    "ChromeTabSummary",
    "_build_chrome_launch_command",
    "_prepare_chrome_profile",
]


@dataclass(slots=True)
class ChromeCdpHtmlFetcher:
    """附著到手動開啟的 Chrome instance，等待使用者導到正確頁面後抓取 HTML。"""

    cdp_endpoint: str = "http://127.0.0.1:9222"
    launch_timeout_seconds: float = 10.0
    manual_wait_timeout_seconds: float = 180.0
    profile_start_url: str | None = None
    page_strategy: BrowserPageStrategy = field(default_factory=BasicBrowserPageStrategy)
    minimum_confident_match_score: int = 35
    chrome_candidates: tuple[str, ...] = (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Chromium\Application\chrome.exe",
    )
    user_data_dir: Path = field(
        default_factory=lambda: Path("data") / "chrome_cdp_profile"
    )

    def __post_init__(self) -> None:
        """若未指定起始頁，使用目前 browser strategy 的 profile start URL。"""
        if self.profile_start_url is None:
            self.profile_start_url = self.page_strategy.profile_start_url

    def fetch_html(
        self,
        url: str,
        *,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> str:
        """附著既有 Chrome；若尚未啟動則開一個可附著的 instance，並等待人工導頁。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError(
                "browser fallback 需要安裝 Playwright 套件；"
                "請先完成專案依賴同步。"
            ) from exc

        self._ensure_debuggable_chrome(start_url=resolved_strategy.profile_start_url)
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.connect_over_cdp(self.cdp_endpoint)
            except PlaywrightError as exc:
                raise ValueError(
                    "無法附著到手動 Chrome session；"
                    "請確認已啟動支援 remote debugging 的 Chrome 視窗。"
                ) from exc

            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = self._get_or_create_page(
                    context,
                    expected_url=url,
                    page_strategy=resolved_strategy,
                )
                print(
                    "已附著到手動 Chrome session。"
                    " 請在該視窗內手動導到可看到房型/價格的頁面，"
                    " 系統會在同一個 session 中自動偵測並繼續。"
                )
                print(f"目標 URL: {url}")
                return self._wait_for_manual_resolution(
                    context=context,
                    initial_page=page,
                    expected_url=url,
                    page_strategy=resolved_strategy,
                )
            finally:
                # connect_over_cdp 只應解除附著，不應關掉使用者正在操作的 Chrome。
                pass

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """列出目前專用 Chrome session 中所有可附著分頁摘要。"""
        quick_tabs = self._list_tabs_from_cdp_targets()
        if quick_tabs is not None:
            return quick_tabs

        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            tabs: list[ChromeTabSummary] = []
            for page in context.pages:
                if page.is_closed():
                    continue
                summary = self._build_tab_summary(page=page)
                tabs.append(summary)
            return tuple(tabs)
        finally:
            playwright.stop()

    def _list_tabs_from_cdp_targets(self) -> tuple[ChromeTabSummary, ...] | None:
        """用 CDP HTTP targets 快速列出分頁，避免摘要頁因 Playwright attach 卡住。"""
        try:
            with urlopen(f"{self.cdp_endpoint}/json/list", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return None
        if not isinstance(payload, list):
            return None

        tabs: list[ChromeTabSummary] = []
        for item in payload:
            if not isinstance(item, dict) or item.get("type") != "page":
                continue
            tab_id = item.get("id")
            url = item.get("url")
            title = item.get("title", "")
            if not isinstance(tab_id, str) or not isinstance(url, str):
                continue
            tabs.append(
                ChromeTabSummary(
                    tab_id=tab_id,
                    title=title if isinstance(title, str) else "",
                    url=url,
                    visibility_state=None,
                    has_focus=None,
                    was_discarded=None,
                )
            )
        return tuple(tabs)

    def fetch_tab_capture(
        self,
        tab_id: str,
        *,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> ChromeTabCapture:
        """依選定的 tab id 抓取該 Chrome 分頁的目前 HTML。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = self._get_page_by_tab_id(context, tab_id)
            if page is None:
                raise ValueError("找不到指定的 Chrome 分頁；請重新整理分頁清單後再試一次。")
            return self._capture_page(page=page, page_strategy=resolved_strategy)
        finally:
            playwright.stop()

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy: BrowserPageStrategy | None = None,
    ) -> ChromeTabCapture:
        """找出最接近目標的頁面，刷新後抓回目前 HTML。"""
        return self.capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
            excluded_tab_ids=excluded_tab_ids,
            page_strategy=page_strategy,
            reload=True,
        )

    def capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy: BrowserPageStrategy | None = None,
        reload: bool = False,
    ) -> ChromeTabCapture:
        """找出最接近目標的頁面，必要時導頁後擷取目前 HTML。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = self._resolve_page_for_url(
                context=context,
                expected_url=expected_url,
                fallback_url=fallback_url,
                preferred_tab_id=preferred_tab_id,
                excluded_tab_ids=excluded_tab_ids,
                page_strategy=resolved_strategy,
            )
            if reload:
                page.reload(wait_until="domcontentloaded", timeout=30000)
            return self._capture_page(page=page, page_strategy=resolved_strategy)
        finally:
            playwright.stop()

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy: BrowserPageStrategy | None = None,
    ) -> ChromeTabSummary:
        """確保指定 watch 至少有一個可沿用的 Chrome 分頁，必要時才建立新分頁。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = self._resolve_page_for_url(
                context=context,
                expected_url=expected_url,
                fallback_url=fallback_url,
                preferred_tab_id=preferred_tab_id,
                excluded_tab_ids=excluded_tab_ids,
                page_strategy=resolved_strategy,
            )
            return self._build_tab_summary(page=page)
        finally:
            playwright.stop()

    def open_profile_window(self, start_url: str | None = None) -> None:
        """啟動或喚醒專用 Chrome profile，供使用者先手動建立真人 session。"""
        self._ensure_debuggable_chrome(start_url=start_url)

    def is_debuggable_chrome_running(self) -> bool:
        """判斷目前是否已有可附著的 Chrome CDP session。"""
        return self._is_cdp_ready()

    def _ensure_debuggable_chrome(self, start_url: str | None = None) -> None:
        """若 CDP 尚未可用，則啟動一個可附著的 Chrome 視窗。"""
        self._build_profile_launcher().ensure_debuggable_chrome(start_url=start_url)

    def _build_profile_launcher(self) -> ChromeProfileLauncher:
        """依目前 fetcher 設定建立 profile launcher。"""
        return ChromeProfileLauncher(
            cdp_endpoint=self.cdp_endpoint,
            launch_timeout_seconds=self.launch_timeout_seconds,
            chrome_candidates=self.chrome_candidates,
            user_data_dir=self.user_data_dir,
            profile_start_url=self.profile_start_url,
        )

    def _connect_playwright_browser(self):
        """附著到既有 CDP Chrome session，並回傳 browser 與 playwright 控制器。"""
        return ChromeCdpConnector(self.cdp_endpoint).connect_playwright_browser(
            ensure_debuggable_chrome=self._ensure_debuggable_chrome,
        )

    def _is_cdp_ready(self) -> bool:
        """檢查本機 CDP 端點是否已可連線。"""
        return self._build_profile_launcher().is_cdp_ready()

    def _find_chrome_path(self) -> str | None:
        """找出本機可用的 Chrome 可執行檔。"""
        return self._build_profile_launcher().find_chrome_path()

    def _get_or_create_page(
        self,
        context,
        *,
        expected_url: str,
        page_strategy: BrowserPageStrategy | None = None,
    ):
        """取得現有頁面；若沒有頁面則建立一頁並導到 profile 起始頁。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        preferred_page = self._find_best_page(
            context,
            expected_url=expected_url,
            page_strategy=resolved_strategy,
        )
        if preferred_page is not None:
            return preferred_page

        page = context.new_page()
        page.goto(
            resolved_strategy.profile_start_url,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        return page

    def _wait_for_manual_resolution(
        self,
        *,
        context,
        initial_page,
        expected_url: str,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> str:
        """等待使用者把目前分頁導到 strategy 判定可讀取的目標頁面。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        deadline = time.monotonic() + self.manual_wait_timeout_seconds
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            page = self._find_best_page(
                context,
                expected_url=expected_url,
                page_strategy=resolved_strategy,
            ) or initial_page
            if page.is_closed():
                time.sleep(1.0)
                continue

            html = page.content()
            try:
                resolved_strategy.raise_if_blocked_page(html)
            except Exception as exc:
                last_error = exc
                page.wait_for_timeout(1000)
                continue
            if resolved_strategy.is_ready_page(
                current_url=page.url,
                expected_url=expected_url,
            ):
                return html
            page.wait_for_timeout(1000)

        if last_error is not None:
            raise ValueError(
                "手動 Chrome preview 已逾時；請重新嘗試，並在可附著的 Chrome 視窗中"
                " 手動導到可看到房型與價格的頁面。"
            ) from last_error
        raise ValueError("手動 Chrome preview 已逾時。")

    def _find_best_page(
        self,
        context,
        *,
        expected_url: str,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy: BrowserPageStrategy | None = None,
    ):
        """在目前所有分頁中挑出最接近目標 URL 的頁面。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        return self._build_page_matcher().find_best_page(
            context,
            expected_url=expected_url,
            excluded_tab_ids=excluded_tab_ids,
            page_strategy=resolved_strategy,
        )

    def _build_page_matcher(self) -> ChromePageMatcher:
        """建立目前 fetcher 使用的 Chrome 分頁 matcher。"""
        return ChromePageMatcher(
            minimum_confident_match_score=self.minimum_confident_match_score,
            get_page_stable_id=self._get_page_stable_id,
        )

    def _get_page_by_tab_id(self, context, tab_id: str):
        """依 tab id 取回目前 context 中對應的分頁。"""
        if not tab_id.strip():
            raise ValueError("Chrome 分頁識別碼格式不正確。")
        for page in context.pages:
            if page.is_closed():
                continue
            if self._get_page_stable_id(page) == tab_id:
                return page
        return None

    def _get_confident_page_by_tab_id(
        self,
        context,
        tab_id: str,
        *,
        expected_url: str,
        page_strategy: BrowserPageStrategy | None = None,
    ):
        """依 tab id 找頁面，但僅在 URL 與目標足夠吻合時才沿用。"""
        page = self._get_page_by_tab_id(context, tab_id)
        if page is None:
            return None
        if self._is_page_confident_match(
            current_url=page.url,
            expected_url=expected_url,
            page_strategy=page_strategy,
        ):
            return page
        return None

    def _build_tab_summary(self, *, page) -> ChromeTabSummary:
        """讀出單一 Chrome 分頁的摘要與背景節流訊號。"""
        return self._build_page_capture_helper().build_tab_summary(page=page)

    def _resolve_page_for_url(
        self,
        *,
        context,
        expected_url: str,
        fallback_url: str | None,
        preferred_tab_id: str | None,
        excluded_tab_ids: tuple[str, ...],
        page_strategy: BrowserPageStrategy | None = None,
    ):
        """依目標 URL、既有 hint 與排除清單，解析本次操作應使用的分頁。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        page = None
        preferred_page = None
        if preferred_tab_id is not None and preferred_tab_id not in excluded_tab_ids:
            preferred_page = self._get_page_by_tab_id(context, preferred_tab_id)
            if preferred_page is not None and self._is_page_confident_match(
                current_url=preferred_page.url,
                expected_url=expected_url,
                page_strategy=resolved_strategy,
            ):
                page = preferred_page
        page = page or self._find_best_page(
            context,
            expected_url=expected_url,
            excluded_tab_ids=excluded_tab_ids,
            page_strategy=resolved_strategy,
        )
        if page is None:
            page = preferred_page or context.new_page()
            self._navigate_page_to_target(
                page=page,
                target_url=fallback_url or expected_url,
            )
        else:
            self._ensure_page_is_on_target(
                page=page,
                expected_url=expected_url,
                fallback_url=fallback_url,
                page_strategy=resolved_strategy,
            )
        return page

    def _capture_page(
        self,
        *,
        page,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> ChromeTabCapture:
        """把 page 內容與其摘要封裝成統一抓取結果。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        return self._build_page_capture_helper().capture_page(
            page=page,
            page_strategy=resolved_strategy,
        )

    def _build_page_capture_helper(self) -> ChromePageCaptureHelper:
        """建立目前 fetcher 使用的 Chrome capture helper。"""
        return ChromePageCaptureHelper(get_page_stable_id=self._get_page_stable_id)

    def _get_page_stable_id(self, page) -> str:
        """為目前 session 中的分頁產生較穩定的識別 key。"""
        cdp_session = None
        try:
            cdp_session = page.context.new_cdp_session(page)
            target_info = cdp_session.send("Target.getTargetInfo")
            target_id = str(target_info["targetInfo"]["targetId"])
            return target_id
        except Exception:
            title = ""
            try:
                title = page.title()
            except Exception:
                title = ""
            fallback_key = f"{page.url}\n{title}"
            return f"fallback-{hashlib.sha1(fallback_key.encode('utf-8')).hexdigest()[:16]}"
        finally:
            try:
                if cdp_session is not None:
                    cdp_session.detach()
            except Exception:
                pass

    def _ensure_page_is_on_target(
        self,
        *,
        page,
        expected_url: str,
        fallback_url: str | None,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> None:
        """確保要刷新的分頁已在目標飯店頁上下文中。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        if self._is_page_confident_match(
            current_url=page.url,
            expected_url=expected_url,
            page_strategy=resolved_strategy,
        ):
            return
        self._navigate_page_to_target(
            page=page,
            target_url=fallback_url or expected_url,
        )

    def _navigate_page_to_target(self, *, page, target_url: str) -> None:
        """把既有或新建分頁導到目標 URL，集中 browser navigation 參數。"""
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

    def _score_page(
        self,
        current_url: str,
        *,
        expected_url: str,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> int:
        """依 URL 相似度為目前分頁評分，優先使用更接近目標飯店頁的分頁。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        return self._build_page_matcher().score_page(
            current_url,
            expected_url=expected_url,
            page_strategy=resolved_strategy,
        )

    def _is_confident_page_match(
        self,
        *,
        current_signature,
        expected_signature,
        score: int,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> bool:
        """判斷目前分頁是否足夠接近目標條件，值得沿用而不是保守 fallback。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        return self._build_page_matcher().is_confident_page_match(
            current_signature=current_signature,
            expected_signature=expected_signature,
            score=score,
            page_strategy=resolved_strategy,
        )

    def _is_page_confident_match(
        self,
        *,
        current_url: str,
        expected_url: str,
        page_strategy: BrowserPageStrategy | None = None,
    ) -> bool:
        """使用 page matcher 判斷目前 URL 是否可安全視為目標頁。"""
        resolved_strategy = self._resolve_page_strategy(page_strategy)
        score = self._score_page(
            current_url,
            expected_url=expected_url,
            page_strategy=resolved_strategy,
        )
        if score <= 0:
            return False
        return self._is_confident_page_match(
            current_signature=resolved_strategy.page_signature(current_url),
            expected_signature=resolved_strategy.page_signature(expected_url),
            score=score,
            page_strategy=resolved_strategy,
        )

    def _resolve_page_strategy(
        self,
        page_strategy: BrowserPageStrategy | None,
    ) -> BrowserPageStrategy:
        """解析單次 request 要使用的 browser page strategy，未指定時沿用預設值。"""
        return page_strategy or self.page_strategy
