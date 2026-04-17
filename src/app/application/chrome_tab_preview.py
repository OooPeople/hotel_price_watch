"""提供從專用 Chrome 分頁建立 preview 的 application service。"""

from __future__ import annotations

from app.application.watch_editor import WatchCreationPreview
from app.infrastructure.browser.chrome_cdp_fetcher import (
    ChromeCdpHtmlFetcher,
    ChromeTabCapture,
    ChromeTabSummary,
)
from app.sites.base import LookupDiagnostic
from app.sites.registry import SiteRegistry


class ChromeTabPreviewService:
    """從專用 Chrome 的既有分頁建立 watch editor preview。"""

    def __init__(
        self,
        *,
        chrome_fetcher: ChromeCdpHtmlFetcher,
        site_registry: SiteRegistry,
    ) -> None:
        self._chrome_fetcher = chrome_fetcher
        self._site_registry = site_registry

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """列出目前可附著且屬於支援站點的瀏覽器分頁。"""
        tabs = self._chrome_fetcher.list_tabs()
        return tuple(
            tab
            for tab in tabs
            if any(
                adapter.is_browser_page_url(tab.url)
                for adapter in self._site_registry.adapters()
            )
        )

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """從指定的 Chrome 分頁內容建立 watch editor preview。"""
        capture = self._chrome_fetcher.fetch_tab_capture(tab_id)
        adapter = self._site_registry.for_browser_page_url(capture.tab.url)
        diagnostics = _build_tab_diagnostics(capture)
        draft, candidate_bundle = adapter.build_preview_from_browser_page(
            page_url=capture.tab.url,
            html=capture.html,
            diagnostics=diagnostics,
        )
        preselected_still_valid = any(
            candidate.room_id == draft.room_id and candidate.plan_id == draft.plan_id
            for candidate in candidate_bundle.candidates
        )
        return WatchCreationPreview(
            draft=draft,
            candidate_bundle=candidate_bundle,
            preselected_room_id=draft.room_id,
            preselected_plan_id=draft.plan_id,
            preselected_still_valid=preselected_still_valid,
            diagnostics=candidate_bundle.diagnostics,
            browser_tab_id=capture.tab.tab_id,
            browser_tab_title=capture.tab.title,
            browser_page_url=capture.tab.url,
        )


def _build_tab_diagnostics(capture: ChromeTabCapture) -> tuple[LookupDiagnostic, ...]:
    """把 Chrome 分頁訊號轉成可顯示在 GUI 的 diagnostics。"""
    diagnostics = [
        LookupDiagnostic(
            stage="chrome_tab_selected",
            status="success",
            detail=f"使用 Chrome 分頁：{capture.tab.title or capture.tab.url}",
        )
    ]
    if capture.tab.possible_throttling:
        visibility_state = capture.tab.visibility_state or "unknown"
        has_focus_text = (
            "focused"
            if capture.tab.has_focus is True
            else "not_focused"
            if capture.tab.has_focus is False
            else "unknown_focus"
        )
        diagnostics.append(
            LookupDiagnostic(
                stage="chrome_tab_signal",
                status="possible_throttling",
                detail=(
                    "目前選取的 Chrome 分頁不是前景活動頁，瀏覽器可能對背景分頁節流。"
                    f" visibility={visibility_state}, focus={has_focus_text}"
                ),
            )
        )
    if capture.tab.was_discarded is True:
        diagnostics.append(
            LookupDiagnostic(
                stage="chrome_tab_signal",
                status="page_was_discarded",
                detail="此分頁曾被瀏覽器丟棄後重建，內容可能不是你剛剛看到的狀態。",
            )
        )
    return tuple(diagnostics)
