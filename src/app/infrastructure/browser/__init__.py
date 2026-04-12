"""瀏覽器抓取實作的匯出入口。"""

from app.infrastructure.browser.chrome_cdp_fetcher import (
    ChromeCdpHtmlFetcher,
    ChromeTabSummary,
)

__all__ = ["ChromeCdpHtmlFetcher", "ChromeTabSummary"]
