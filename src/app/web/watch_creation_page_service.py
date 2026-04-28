"""watch creation 頁面的 page context 與站點 scope 組裝服務。"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.watch_editor import WatchCreationPreview
from app.application.watch_tab_matching import find_existing_watch_ids_by_tab_id
from app.bootstrap.container import AppContainer
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic, SiteDescriptor


@dataclass(frozen=True, slots=True)
class ChromeTabSelectionContext:
    """Chrome 分頁選擇頁 renderer 所需的資料集合。"""

    tabs: tuple[ChromeTabSummary, ...]
    error_message: str | None
    diagnostics: tuple[LookupDiagnostic, ...]
    selected_tab_id: str | None
    existing_watch_ids_by_tab_id: dict[str, str]
    site_descriptors: tuple[SiteDescriptor, ...]
    site_labels_by_tab_id: dict[str, str]


class WatchCreationPageService:
    """集中 watch creation route 需要的頁面 context 與站點 scope 判斷。"""

    def __init__(self, container: AppContainer) -> None:
        """保存 route 層提供的依賴容器。"""
        self._container = container

    def chrome_tab_selection_context(
        self,
        *,
        tabs: tuple[ChromeTabSummary, ...],
        error_message: str | None = None,
        diagnostics: tuple[LookupDiagnostic, ...] = (),
        selected_tab_id: str | None = None,
    ) -> ChromeTabSelectionContext:
        """建立 Chrome 分頁選擇頁 renderer 需要的完整 context。"""
        return ChromeTabSelectionContext(
            tabs=tabs,
            error_message=error_message,
            diagnostics=diagnostics,
            selected_tab_id=selected_tab_id,
            existing_watch_ids_by_tab_id=self.existing_watch_ids_by_tab_id(tabs),
            site_descriptors=self._container.site_registry.descriptors(),
            site_labels_by_tab_id=self.site_labels_by_tab_id(tabs),
        )

    def existing_watch_ids_by_tab_id(
        self,
        chrome_tabs: tuple[ChromeTabSummary, ...],
    ) -> dict[str, str]:
        """依既有 watch target 與已保存頁面資訊，標記哪些分頁已對應 watch。"""
        watch_items = tuple(self._container.watch_item_repository.list_all())
        drafts_by_watch_id = {
            watch_item.id: self._container.watch_item_repository.get_draft(watch_item.id)
            for watch_item in watch_items
        }
        return find_existing_watch_ids_by_tab_id(
            chrome_tabs=chrome_tabs,
            watch_items=watch_items,
            drafts_by_watch_id=drafts_by_watch_id,
            site_registry=self._container.site_registry,
        )

    def site_labels_by_tab_id(
        self,
        chrome_tabs: tuple[ChromeTabSummary, ...],
    ) -> dict[str, str]:
        """依 Chrome 分頁 URL 標示對應站點名稱，供分頁選擇頁顯示。"""
        labels_by_tab_id: dict[str, str] = {}
        for tab in chrome_tabs:
            try:
                descriptor = self._container.site_registry.descriptor_for_browser_page_url(
                    tab.url
                )
            except LookupError:
                continue
            labels_by_tab_id[tab.tab_id] = descriptor.display_name
        return labels_by_tab_id

    def site_name_for_seed_url(self, seed_url: str) -> str:
        """依 seed URL 判定 preview guard 應使用的 site scope。"""
        try:
            return self._container.site_registry.for_url(seed_url).site_name
        except LookupError:
            return self.default_site_name()

    def site_name_for_selected_tab(
        self,
        *,
        chrome_tabs: tuple[ChromeTabSummary, ...],
        selected_tab_id: str,
    ) -> str:
        """依使用者選定的 Chrome 分頁判定 preview guard 應使用的 site scope。"""
        for tab in chrome_tabs:
            if tab.tab_id != selected_tab_id:
                continue
            try:
                return self._container.site_registry.for_browser_page_url(tab.url).site_name
            except LookupError:
                return self.default_site_name()
        return self.default_site_name()

    def site_name_for_preview(self, preview: WatchCreationPreview) -> str:
        """依已建立的 preview 判定實際站點，避免成功結果寫入錯誤 scope。"""
        try:
            return self._container.site_registry.for_url(preview.draft.seed_url).site_name
        except LookupError:
            return self.default_site_name()

    def default_site_name(self) -> str:
        """回傳目前 registry 的預設 site name，供錯誤路徑兜底。"""
        return self._container.site_registry.default_descriptor().site_name
