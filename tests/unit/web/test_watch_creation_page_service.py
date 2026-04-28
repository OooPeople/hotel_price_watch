from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser import ChromeTabSummary
from app.web.watch_creation_page_service import WatchCreationPageService

from .helpers import (
    _build_test_container,
    _build_watch_item,
)


def test_watch_creation_page_service_marks_existing_tabs_and_site_labels(tmp_path) -> None:
    """WatchCreationPageService 應集中標示既有 watch 分頁與站點名稱。"""
    container = _build_test_container(tmp_path)
    watch_item = replace(
        _build_watch_item(),
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
    )
    container.watch_item_repository.save(watch_item)
    container.watch_item_repository.save_draft(
        watch_item.id,
        SearchDraft(
            seed_url=watch_item.canonical_url,
            hotel_id=watch_item.target.hotel_id,
            room_id=watch_item.target.room_id,
            plan_id=watch_item.target.plan_id,
            check_in_date=watch_item.target.check_in_date,
            check_out_date=watch_item.target.check_out_date,
            people_count=watch_item.target.people_count,
            room_count=watch_item.target.room_count,
            browser_page_url=watch_item.canonical_url,
        ),
    )
    tabs = (
        ChromeTabSummary(
            tab_id="tab-a",
            title="Ocean Hotel",
            url=watch_item.canonical_url,
            visibility_state="visible",
            has_focus=True,
        ),
    )
    service = WatchCreationPageService(container)

    context = service.chrome_tab_selection_context(tabs=tabs)

    assert context.existing_watch_ids_by_tab_id == {"tab-a": watch_item.id}
    assert context.site_labels_by_tab_id == {"tab-a": "IKYU"}
    assert service.site_name_for_selected_tab(
        chrome_tabs=tabs,
        selected_tab_id="tab-a",
    ) == "ikyu"
