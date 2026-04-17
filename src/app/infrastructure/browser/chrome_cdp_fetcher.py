"""以 Chrome CDP 連線既有真人瀏覽器 session 的 HTML 抓取器。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from app.infrastructure.browser.page_strategy import (
    BasicBrowserPageStrategy,
    BrowserPageStrategy,
)


@dataclass(frozen=True, slots=True)
class ChromeTabSummary:
    """表示目前可附著的 Chrome 分頁摘要。"""

    tab_id: str
    title: str
    url: str
    visibility_state: str | None
    has_focus: bool | None
    was_discarded: bool | None = None

    @property
    def possible_throttling(self) -> bool:
        """以頁面可見性與焦點狀態推估背景節流風險。"""
        return (
            self.visibility_state == "hidden"
            or self.has_focus is False
            or self.was_discarded is True
        )


@dataclass(frozen=True, slots=True)
class ChromeTabCapture:
    """表示從特定 Chrome 分頁抓回的內容與分頁摘要。"""

    tab: ChromeTabSummary
    html: str


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

    def fetch_html(self, url: str) -> str:
        """附著既有 Chrome；若尚未啟動則開一個可附著的 instance，並等待人工導頁。"""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError(
                "browser fallback 需要安裝 Playwright 套件；"
                "請先完成專案依賴同步。"
            ) from exc

        self._ensure_debuggable_chrome()
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
                page = self._get_or_create_page(context, expected_url=url)
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
                )
            finally:
                # connect_over_cdp 只應解除附著，不應關掉使用者正在操作的 Chrome。
                pass

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """列出目前專用 Chrome session 中所有可附著分頁摘要。"""
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

    def fetch_tab_capture(self, tab_id: str) -> ChromeTabCapture:
        """依選定的 tab id 抓取該 Chrome 分頁的目前 HTML。"""
        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = self._get_page_by_tab_id(context, tab_id)
            if page is None:
                raise ValueError("找不到指定的 Chrome 分頁；請重新整理分頁清單後再試一次。")
            return self._capture_page(page=page)
        finally:
            playwright.stop()

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
    ) -> ChromeTabCapture:
        """找出最接近目標的頁面，刷新後抓回目前 HTML。"""
        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = None
            if preferred_tab_id is not None and preferred_tab_id not in excluded_tab_ids:
                page = self._get_page_by_tab_id(context, preferred_tab_id)
            page = page or self._find_best_page(
                context,
                expected_url=expected_url,
                excluded_tab_ids=excluded_tab_ids,
            )
            if page is None:
                page = context.new_page()
                page.goto(
                    fallback_url or expected_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            else:
                self._ensure_page_is_on_target(
                    page=page,
                    expected_url=expected_url,
                    fallback_url=fallback_url,
                )

            page.reload(wait_until="domcontentloaded", timeout=30000)
            return self._capture_page(page=page)
        finally:
            playwright.stop()

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
    ) -> ChromeTabSummary:
        """確保指定 watch 至少有一個可沿用的 Chrome 分頁，必要時才建立新分頁。"""
        browser, playwright = self._connect_playwright_browser()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = None
            if preferred_tab_id is not None and preferred_tab_id not in excluded_tab_ids:
                page = self._get_page_by_tab_id(context, preferred_tab_id)
            page = page or self._find_best_page(
                context,
                expected_url=expected_url,
                excluded_tab_ids=excluded_tab_ids,
            )
            if page is None:
                page = context.new_page()
                page.goto(
                    fallback_url or expected_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            else:
                self._ensure_page_is_on_target(
                    page=page,
                    expected_url=expected_url,
                    fallback_url=fallback_url,
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
        if self._is_cdp_ready():
            return

        chrome_path = self._find_chrome_path()
        if chrome_path is None:
            raise ValueError(
                "找不到可用的 Chrome 可執行檔；"
                "請安裝 Chrome，或手動以 remote debugging 模式啟動後再重試。"
            )

        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        _prepare_chrome_profile(self.user_data_dir)
        subprocess.Popen(
            _build_chrome_launch_command(
                chrome_path=chrome_path,
                user_data_dir=self.user_data_dir,
                url=start_url or self.profile_start_url,
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + self.launch_timeout_seconds
        while time.monotonic() < deadline:
            if self._is_cdp_ready():
                return
            time.sleep(0.5)

        raise ValueError(
            "已嘗試啟動可附著的 Chrome 視窗，但 CDP 端點仍未就緒；"
            "請確認 Chrome 未被安全軟體或系統政策攔下。"
        )

    def _connect_playwright_browser(self):
        """附著到既有 CDP Chrome session，並回傳 browser 與 playwright 控制器。"""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError(
                "browser fallback 需要安裝 Playwright 套件；"
                "請先完成專案依賴同步。"
            ) from exc

        self._ensure_debuggable_chrome()
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.connect_over_cdp(self.cdp_endpoint)
        except PlaywrightError as exc:
            playwright.stop()
            raise ValueError(
                "無法附著到手動 Chrome session；"
                "請確認已啟動支援 remote debugging 的 Chrome 視窗。"
            ) from exc
        return browser, playwright

    def _is_cdp_ready(self) -> bool:
        """檢查本機 CDP 端點是否已可連線。"""
        try:
            with urllib.request.urlopen(
                f"{self.cdp_endpoint}/json/version",
                timeout=2.0,
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _find_chrome_path(self) -> str | None:
        """找出本機可用的 Chrome 可執行檔。"""
        for path in self.chrome_candidates:
            if Path(path).exists():
                return path
        return None

    def _get_or_create_page(self, context, *, expected_url: str):
        """取得現有頁面；若沒有頁面則建立一頁並導到 profile 起始頁。"""
        preferred_page = self._find_best_page(context, expected_url=expected_url)
        if preferred_page is not None:
            return preferred_page

        page = context.new_page()
        page.goto(
            self.profile_start_url,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        return page

    def _wait_for_manual_resolution(self, *, context, initial_page, expected_url: str) -> str:
        """等待使用者把目前分頁導到 strategy 判定可讀取的目標頁面。"""
        deadline = time.monotonic() + self.manual_wait_timeout_seconds
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            page = self._find_best_page(context, expected_url=expected_url) or initial_page
            if page.is_closed():
                time.sleep(1.0)
                continue

            html = page.content()
            try:
                self.page_strategy.raise_if_blocked_page(html)
            except Exception as exc:
                last_error = exc
                page.wait_for_timeout(1000)
                continue
            if self.page_strategy.is_ready_page(
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
    ):
        """在目前所有分頁中挑出最接近目標 URL 的頁面。"""
        best_page = None
        best_score = -1
        best_signature = None
        expected_signature = self.page_strategy.page_signature(expected_url)
        excluded_ids = set(excluded_tab_ids)
        for page in context.pages:
            if page.is_closed():
                continue
            if excluded_ids and self._get_page_stable_id(page) in excluded_ids:
                continue
            score = self._score_page(page.url, expected_url=expected_url)
            if score > best_score:
                best_page = page
                best_score = score
                best_signature = self.page_strategy.page_signature(page.url)
        if (
            best_score <= 0
            or best_signature is None
            or not self._is_confident_page_match(
                current_signature=best_signature,
                expected_signature=expected_signature,
                score=best_score,
            )
        ):
            return None
        return best_page

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

    def _build_tab_summary(self, *, page) -> ChromeTabSummary:
        """讀出單一 Chrome 分頁的摘要與背景節流訊號。"""
        title = ""
        try:
            title = page.title()
        except Exception:
            title = ""

        visibility_state = None
        has_focus = None
        was_discarded = None
        try:
            visibility_state = page.evaluate("() => document.visibilityState")
        except Exception:
            visibility_state = None
        try:
            has_focus = page.evaluate("() => document.hasFocus()")
        except Exception:
            has_focus = None
        try:
            was_discarded = page.evaluate("() => Boolean(document.wasDiscarded)")
        except Exception:
            was_discarded = None

        return ChromeTabSummary(
            tab_id=self._get_page_stable_id(page),
            title=title,
            url=page.url,
            visibility_state=visibility_state,
            has_focus=has_focus,
            was_discarded=was_discarded,
        )

    def _capture_page(self, *, page) -> ChromeTabCapture:
        """把 page 內容與其摘要封裝成統一抓取結果。"""
        html = page.content()
        self.page_strategy.raise_if_blocked_page(html)
        summary = self._build_tab_summary(page=page)
        return ChromeTabCapture(
            tab=summary,
            html=html,
        )

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
    ) -> None:
        """確保要刷新的分頁已在目標飯店頁上下文中。"""
        if self.page_strategy.is_ready_page(
            current_url=page.url,
            expected_url=expected_url,
        ):
            return
        page.goto(
            fallback_url or expected_url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

    def _score_page(self, current_url: str, *, expected_url: str) -> int:
        """依 URL 相似度為目前分頁評分，優先使用更接近目標飯店頁的分頁。"""
        return self.page_strategy.score_page(current_url, expected_url=expected_url)

    def _is_confident_page_match(
        self,
        *,
        current_signature,
        expected_signature,
        score: int,
    ) -> bool:
        """判斷目前分頁是否足夠接近目標條件，值得沿用而不是保守 fallback。"""
        return self.page_strategy.is_confident_page_match(
            current_signature=current_signature,
            expected_signature=expected_signature,
            score=score,
            minimum_score=self.minimum_confident_match_score,
        )


def _build_chrome_launch_command(
    *,
    chrome_path: str,
    user_data_dir: Path,
    url: str,
) -> list[str]:
    """建立啟動可附著 Chrome instance 的命令列參數。"""
    return [
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir.resolve()}",
        "--new-window",
        "--disable-animations",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-domain-reliability",
        "--disable-infobars",
        "--disable-logging",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--disable-translate",
        "--disable-features=TranslateUI",
        "--homepage=about:blank",
        "--lang=zh-TW",
        "--no-default-browser-check",
        "--no-first-run",
        "--no-pings",
        "--no-service-autorun",
        "--password-store=basic",
        url,
    ]


def _prepare_chrome_profile(user_data_dir: Path) -> None:
    """預先寫入偏好設定，減少第一次啟動的多餘干擾。"""
    default_dir = user_data_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    preferences = {
        "credentials_enable_service": False,
        "ack_existing_ntp_extensions": False,
        "translate": {"enabled": False},
        "profile": {
            "default_content_setting_values": {
                "notifications": 2,
                "sound": 2,
            },
            "password_manager_enabled": False,
            "name": "hotel_price_watch",
        },
        "privacy_sandbox": {"first_party_sets_enabled": False},
        "safebrowsing": {"enabled": False, "enhanced": False},
        "sync": {"autofill_wallet_import_enabled_migrated": False},
        "net": {"network_prediction_options": 3},
    }
    preferences_path = default_dir / "Preferences"
    if not preferences_path.exists():
        preferences_path.write_text(
            json.dumps(preferences),
            encoding="utf-8",
        )

    local_state = {
        "performance_tuning": {"high_efficiency_mode": {"state": 1}},
        "browser": {
            "enabled_labs_experiments": [
                "history-journeys@4",
                "memory-saver-multi-state-mode@1",
                "modal-memory-saver@1",
                "read-anything@2",
            ]
        },
        "dns_over_https": {"mode": "off"},
    }
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        local_state_path.write_text(
            json.dumps(local_state),
            encoding="utf-8",
        )
