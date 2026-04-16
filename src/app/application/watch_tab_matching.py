"""提供 Chrome 分頁與既有 watch 的對應判斷。"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities import WatchItem
from app.domain.value_objects import SearchDraft
from app.sites.ikyu.browser_matching import (
    extract_ikyu_browser_page_signature,
    ikyu_signature_matches_watch_target,
    ikyu_urls_match_confidently,
)


class BrowserTabLike(Protocol):
    """描述分頁比對只需要的最小欄位，避免 application 依賴具體 fetcher 類別。"""

    tab_id: str
    url: str


def find_existing_watch_ids_by_tab_id(
    *,
    chrome_tabs: tuple[BrowserTabLike, ...],
    watch_items: tuple[WatchItem, ...],
    drafts_by_watch_id: dict[str, SearchDraft | None],
) -> dict[str, str]:
    """依既有 watch target 與已保存頁面資訊，標記哪些分頁已對應 watch。"""
    linked: dict[str, str] = {}
    for tab in chrome_tabs:
        matched_watch = find_existing_watch_for_tab(
            tab_url=tab.url,
            watch_items=watch_items,
            drafts_by_watch_id=drafts_by_watch_id,
        )
        if matched_watch is not None:
            linked[tab.tab_id] = matched_watch.id
    return linked


def find_existing_watch_for_tab(
    *,
    tab_url: str,
    watch_items: tuple[WatchItem, ...],
    drafts_by_watch_id: dict[str, SearchDraft | None],
) -> WatchItem | None:
    """依頁面 URL 與 watch target identity 判斷某個分頁是否已對應既有 watch。"""
    for watch_item in watch_items:
        if watch_item.target.site == "ikyu" and _ikyu_tab_matches_watch(
            tab_url=tab_url,
            watch_item=watch_item,
            draft=drafts_by_watch_id.get(watch_item.id),
        ):
            return watch_item
    return None


def _ikyu_tab_matches_watch(
    *,
    tab_url: str,
    watch_item: WatchItem,
    draft: SearchDraft | None,
) -> bool:
    """判斷單一 `ikyu` 分頁是否對應指定 watch。"""
    if draft is not None and draft.browser_page_url is not None and (
        draft.browser_page_url == tab_url
        or ikyu_urls_match_confidently(
            left_url=draft.browser_page_url,
            right_url=tab_url,
        )
    ):
        return True

    if ikyu_urls_match_confidently(
        left_url=watch_item.canonical_url,
        right_url=tab_url,
    ):
        return True

    return ikyu_signature_matches_watch_target(
        signature=extract_ikyu_browser_page_signature(tab_url),
        target=watch_item.target,
    )
