"""集中管理 V1 站點 adapter 與 browser strategy 的組裝。"""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.browser import ChromeCdpHtmlFetcher
from app.infrastructure.browser.page_strategy import BrowserPageStrategy
from app.sites.ikyu import IkyuAdapter
from app.sites.ikyu.browser_strategy import IkyuBrowserPageStrategy
from app.sites.ikyu.client import BrowserHtmlFetcher, LiveIkyuHtmlClient
from app.sites.registry import SiteRegistry


@dataclass(frozen=True, slots=True)
class StrategyBoundBrowserHtmlFetcher:
    """把 generic CDP fetcher 綁定到單一站點 strategy，供舊 client protocol 使用。"""

    browser_fallback: ChromeCdpHtmlFetcher
    page_strategy: BrowserPageStrategy

    def fetch_html(self, url: str) -> str:
        """以指定站點 strategy 透過 Chrome CDP 抓取頁面 HTML。"""
        return self.browser_fallback.fetch_html(
            url,
            page_strategy=self.page_strategy,
        )


def build_default_browser_page_strategy() -> BrowserPageStrategy:
    """建立 V1 預設 browser page strategy，目前正式站點為 `ikyu`。"""
    return IkyuBrowserPageStrategy()


def register_default_sites(
    site_registry: SiteRegistry,
    *,
    browser_fallback: BrowserHtmlFetcher,
) -> None:
    """把 V1 預設站點 adapter 註冊進 registry。"""
    browser_page_strategy = IkyuBrowserPageStrategy()
    site_registry.register(
        IkyuAdapter(
            browser_page_strategy=browser_page_strategy,
            html_client=LiveIkyuHtmlClient(
                browser_fallback=StrategyBoundBrowserHtmlFetcher(
                    browser_fallback=browser_fallback,
                    page_strategy=browser_page_strategy,
                ),
                enable_browser_fallback=True,
                prefer_browser_fallback_for_search=True,
            )
        )
    )
