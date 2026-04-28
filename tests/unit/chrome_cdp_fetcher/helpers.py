"""Chrome CDP fetcher 測試共用 helper。"""

from __future__ import annotations

from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher
from app.sites.ikyu.browser_strategy import IkyuBrowserPageStrategy


def _build_ikyu_fetcher(**kwargs) -> ChromeCdpHtmlFetcher:
    """建立使用 `ikyu` browser strategy 的 fetcher 測試實例。"""
    return ChromeCdpHtmlFetcher(page_strategy=IkyuBrowserPageStrategy(), **kwargs)
