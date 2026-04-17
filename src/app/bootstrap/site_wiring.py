"""集中管理 V1 站點 adapter 與 browser strategy 的組裝。"""

from __future__ import annotations

from app.infrastructure.browser.page_strategy import BrowserPageStrategy
from app.sites.ikyu import IkyuAdapter
from app.sites.ikyu.browser_strategy import IkyuBrowserPageStrategy
from app.sites.ikyu.client import BrowserHtmlFetcher, LiveIkyuHtmlClient
from app.sites.registry import SiteRegistry


def build_default_browser_page_strategy() -> BrowserPageStrategy:
    """建立 V1 預設 browser page strategy，目前正式站點為 `ikyu`。"""
    return IkyuBrowserPageStrategy()


def register_default_sites(
    site_registry: SiteRegistry,
    *,
    browser_fallback: BrowserHtmlFetcher,
) -> None:
    """把 V1 預設站點 adapter 註冊進 registry。"""
    site_registry.register(
        IkyuAdapter(
            html_client=LiveIkyuHtmlClient(
                browser_fallback=browser_fallback,
                enable_browser_fallback=True,
                prefer_browser_fallback_for_search=True,
            )
        )
    )
