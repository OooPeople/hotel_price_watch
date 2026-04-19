"""Chrome 分頁摘要、節流訊號與 HTML capture helper。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.infrastructure.browser.chrome_models import ChromeTabCapture, ChromeTabSummary
from app.infrastructure.browser.page_strategy import BrowserPageStrategy


@dataclass(frozen=True, slots=True)
class ChromePageCaptureHelper:
    """負責從 Playwright page 讀取摘要訊號與 HTML capture。"""

    get_page_stable_id: Callable[[object], str]

    def build_tab_summary(self, *, page) -> ChromeTabSummary:
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
            tab_id=self.get_page_stable_id(page),
            title=title,
            url=page.url,
            visibility_state=visibility_state,
            has_focus=has_focus,
            was_discarded=was_discarded,
        )

    def capture_page(
        self,
        *,
        page,
        page_strategy: BrowserPageStrategy,
    ) -> ChromeTabCapture:
        """把 page 內容與其摘要封裝成統一抓取結果。"""
        html = page.content()
        page_strategy.raise_if_blocked_page(html)
        summary = self.build_tab_summary(page=page)
        return ChromeTabCapture(
            tab=summary,
            html=html,
        )
