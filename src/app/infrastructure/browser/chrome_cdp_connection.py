"""Chrome CDP attach 與 Playwright lifecycle helper。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChromeCdpConnector:
    """負責啟動 Playwright 並附著到既有 Chrome CDP session。"""

    cdp_endpoint: str

    def connect_playwright_browser(
        self,
        *,
        ensure_debuggable_chrome: Callable[[], None],
    ):
        """確認 Chrome 可附著後，回傳 browser 與 playwright 控制器。"""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError(
                "browser fallback 需要安裝 Playwright 套件；"
                "請先完成專案依賴同步。"
            ) from exc

        ensure_debuggable_chrome()
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
