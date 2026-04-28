"""新增監視流程使用的 page-level presentation model。"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.watch_editor import WatchCreationPreview
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic, SiteDescriptor


@dataclass(frozen=True, slots=True)
class NewWatchPageViewModel:
    """集中新增監視入口 / preview 頁的顯示狀態。"""

    preview: WatchCreationPreview | None
    preview_cache_key: str | None
    error_message: str | None
    diagnostics: tuple[LookupDiagnostic, ...]
    site_label_list: str
    has_preview: bool
    current_step: int
    page_subtitle: str


@dataclass(frozen=True, slots=True)
class ChromeTabSelectionPageViewModel:
    """集中 Chrome 分頁選擇頁 renderer 所需資料。"""

    tabs: tuple[ChromeTabSummary, ...]
    error_message: str | None
    diagnostics: tuple[LookupDiagnostic, ...]
    selected_tab_id: str | None
    existing_watch_ids_by_tab_id: dict[str, str]
    site_labels_by_tab_id: dict[str, str]
    site_label_list: str
    site_hint_list: str
    has_throttling_signal: bool


def build_new_watch_page_view_model(
    *,
    preview: WatchCreationPreview | None = None,
    preview_cache_key: str | None = None,
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    site_descriptors: tuple[SiteDescriptor, ...] = (),
) -> NewWatchPageViewModel:
    """把新增監視頁 context 轉成頁面級 view model。"""
    site_label_list = format_site_label_list(site_descriptors)
    has_preview = preview is not None
    return NewWatchPageViewModel(
        preview=preview,
        preview_cache_key=preview_cache_key,
        error_message=error_message,
        diagnostics=diagnostics,
        site_label_list=site_label_list,
        has_preview=has_preview,
        current_step=2 if has_preview else 1,
        page_subtitle=(
            "確認來源、房型與通知條件後開始監視。"
            if has_preview
            else f"從專用 Chrome 中已開啟的 {site_label_list} 頁面建立價格監視。"
        ),
    )


def build_chrome_tab_selection_page_view_model(
    *,
    tabs: tuple[ChromeTabSummary, ...],
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    selected_tab_id: str | None = None,
    existing_watch_ids_by_tab_id: dict[str, str] | None = None,
    site_descriptors: tuple[SiteDescriptor, ...] = (),
    site_labels_by_tab_id: dict[str, str] | None = None,
) -> ChromeTabSelectionPageViewModel:
    """把 Chrome 分頁選擇 context 轉成頁面級 view model。"""
    return ChromeTabSelectionPageViewModel(
        tabs=tabs,
        error_message=error_message,
        diagnostics=diagnostics,
        selected_tab_id=selected_tab_id,
        existing_watch_ids_by_tab_id=existing_watch_ids_by_tab_id or {},
        site_labels_by_tab_id=site_labels_by_tab_id or {},
        site_label_list=format_site_label_list(site_descriptors),
        site_hint_list=format_site_hint_list(site_descriptors),
        has_throttling_signal=any(tab.possible_throttling for tab in tabs),
    )


def format_site_label_list(site_descriptors: tuple[SiteDescriptor, ...]) -> str:
    """把站點顯示名稱整理成適合 GUI 句子使用的文字。"""
    labels = tuple(
        descriptor.display_name
        for descriptor in site_descriptors
        if descriptor.supports_browser_preview
    )
    return "、".join(labels) if labels else "支援站點"


def format_site_hint_list(site_descriptors: tuple[SiteDescriptor, ...]) -> str:
    """把站點瀏覽器開頁提示整理成適合 GUI 句子使用的文字。"""
    hints = tuple(
        descriptor.browser_tab_hint
        for descriptor in site_descriptors
        if descriptor.supports_browser_preview
    )
    return "、".join(hints) if hints else "支援站點"
