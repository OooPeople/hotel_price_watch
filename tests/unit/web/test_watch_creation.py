from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.application.chrome_tab_preview import ChromeTabPreviewService
from app.application.watch_editor import WatchCreationPreview
from app.domain.enums import Availability, NotificationLeafKind
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser import ChromeTabSummary
from app.main import create_app
from app.sites.base import CandidateBundle, LookupDiagnostic, SiteDescriptor
from app.web.routes import watch_creation_routes as watch_creation_routes_module
from app.web.views import (
    render_chrome_tab_selection_page,
    render_new_watch_page,
)
from app.web.watch_creation_presenters import (
    build_chrome_tab_selection_page_view_model,
    build_new_watch_page_view_model,
)

from .helpers import (
    _build_preview,
    _build_test_container,
    _build_watch_item,
    _FailingChromeTabPreviewService,
    _local_request_headers,
    _SlowChromeTabPreviewService,
    _StaticChromeTabPreviewService,
    _StaticListTabsFetcher,
)


def test_render_new_watch_page_shows_candidate_preview() -> None:
    """驗證新增 watch 頁會顯示 preview 候選方案與建立表單。"""
    html = render_new_watch_page(
        seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        preview=_build_preview(
            "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            browser_tab_id="0",
            browser_tab_title="Dormy Tab",
        ),
    )

    assert "Ocean Hotel" in html
    assert "Room Only" in html
    assert "開始監視價格" in html
    assert "總價：JPY 24000" in html
    assert "每人每晚：約 JPY 12000" in html
    assert "重新抓取此分頁" in html
    assert "Dormy Tab" not in html
    assert "tab id:" not in html
    assert "Step 2 選擇方案" in html
    assert (
        f'<option value="{NotificationLeafKind.ANY_DROP.value}" selected>'
        in html
    )
    assert f'value="{NotificationLeafKind.BELOW_TARGET_PRICE.value}"' in html
    assert "目標價欄位會被忽略" in html
    assert "display:none" in html
    assert 'aria-label="新增監視流程"' in html
    assert "設定通知與確認" in html
    assert "1　選擇來源" not in html
    assert "Step 4 確認建立" not in html
    assert "本次監視摘要" in html
    assert "設定完成後，我們將立即開始監視價格" in html
    assert "每 10 分鐘檢查一次" in html


def test_watch_creation_view_models_centralize_page_state() -> None:
    """新增監視 view model 應集中 step、站點文案與節流提示狀態。"""
    descriptor = SiteDescriptor(
        site_name="ikyu",
        display_name="IKYU",
        browser_page_label="IKYU",
        browser_tab_hint="IKYU.com",
    )
    preview = _build_preview("https://www.ikyu.com/zh-tw/00082173/?top=rooms")
    new_watch_view_model = build_new_watch_page_view_model(
        preview=preview,
        site_descriptors=(descriptor,),
    )
    tab_view_model = build_chrome_tab_selection_page_view_model(
        tabs=(
            ChromeTabSummary(
                tab_id="tab-a",
                title="Dormy Inn",
                url="https://www.ikyu.com/zh-tw/00082173/",
                visibility_state="hidden",
                has_focus=False,
            ),
        ),
        site_descriptors=(descriptor,),
    )

    assert new_watch_view_model.has_preview is True
    assert new_watch_view_model.current_step == 2
    assert new_watch_view_model.site_label_list == "IKYU"
    assert tab_view_model.site_hint_list == "IKYU.com"
    assert tab_view_model.has_throttling_signal is True


def test_render_new_watch_page_disables_create_when_target_already_exists() -> None:
    """若 preview 對應的 target 已有 watch，應顯示既有 watch 並禁用建立。"""
    html = render_new_watch_page(
        preview=replace(
            _build_preview(
                "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
                browser_tab_id="0",
                browser_tab_title="Dormy Tab",
            ),
            existing_watch_id="watch-list-1",
        )
    )

    assert "目前選定目標已建立監視" in html
    assert "/watches/watch-list-1" in html
    assert "已建立監視" in html
    assert "建立 Watch Item" not in html


def test_post_create_watch_defaults_to_any_drop_notification_rule(tmp_path) -> None:
    """建立監視表單缺少通知條件時，後端預設應使用價格下降。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/watches",
        data={
            "seed_url": "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            "candidate_key": "room-1::plan-1",
            "scheduler_interval_seconds": "600",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    saved_items = container.watch_item_repository.list_all()
    assert len(saved_items) == 1
    assert saved_items[0].notification_rule == RuleLeaf(
        kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )
    latest_snapshot = container.runtime_history_repository.get_latest_check_snapshot(
        saved_items[0].id
    )
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("24000")
    assert latest_snapshot.availability == Availability.AVAILABLE
    check_events = container.runtime_history_repository.list_check_events(saved_items[0].id)
    assert check_events[0].event_kinds == ("initial_snapshot",)
    price_history = container.runtime_history_repository.list_price_history(saved_items[0].id)
    assert price_history[0].display_price_text == "JPY 24000"


def test_post_create_watch_uses_cached_chrome_tab_preview(tmp_path) -> None:
    """Chrome 分頁 preview 成功後，建立 watch 不應再次抓取同一個分頁。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    preview_response = client.post(
        "/watches/chrome-tabs/preview",
        data={"tab_id": "0"},
        headers=_local_request_headers(),
    )

    assert preview_response.status_code == 200
    cache_key_match = re.search(
        r'name="preview_cache_key" value="([^"]+)"',
        preview_response.text,
    )
    assert cache_key_match is not None
    container.chrome_tab_preview_service = _FailingChromeTabPreviewService()

    create_response = client.post(
        "/watches",
        data={
            "seed_url": "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            "browser_tab_id": "0",
            "preview_cache_key": cache_key_match.group(1),
            "candidate_key": "room-1::plan-1",
            "scheduler_interval_seconds": "600",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert create_response.status_code == 303
    saved_items = container.watch_item_repository.list_all()
    assert len(saved_items) == 1
    latest_snapshot = container.runtime_history_repository.get_latest_check_snapshot(
        saved_items[0].id
    )
    assert latest_snapshot is not None
    assert latest_snapshot.normalized_price_amount == Decimal("24000")


def test_render_new_watch_page_hides_preview_debug_capture_paths() -> None:
    """建立頁不直接顯示 preview debug capture，避免干擾使用者流程。"""
    preview = WatchCreationPreview(
        draft=SearchDraft(
            seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        candidate_bundle=CandidateBundle(
            hotel_id="00082173",
            hotel_name="Debug Hotel",
            canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            candidates=(),
            debug_artifact_paths=(
                "debug/ikyu_preview_last.html",
                "debug/ikyu_preview_last_meta.json",
            ),
        ),
        preselected_room_id=None,
        preselected_plan_id=None,
        preselected_still_valid=False,
    )

    html = render_new_watch_page(
        seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        preview=preview,
    )

    assert "ikyu_preview_last.html" not in html
    assert "ikyu_preview_last_meta.json" not in html
    assert "診斷檔案" not in html


def test_render_new_watch_page_shows_diagnostics() -> None:
    """驗證新增 watch 頁會顯示 preview 診斷資訊。"""
    html = render_new_watch_page(
        seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        diagnostics=(
            LookupDiagnostic(
                stage="http_first",
                status="http_403",
                detail="ikyu 拒絕目前的直接 HTTP 請求（403）。",
            ),
        ),
    )

    assert "診斷資訊" in html
    assert "http_first" in html
    assert "http_403" in html


def test_render_new_watch_page_shows_dedicated_profile_hint() -> None:
    """新增頁應維持 Chrome-driven 入口，但不再顯示冗長啟動說明。"""
    html = render_new_watch_page(
        seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
    )

    assert "app.tools.dev_start" not in html
    assert "專用 Chrome profile" not in html
    assert "選擇 Chrome 分頁" in html
    assert "請從專用 Chrome 選擇" in html
    assert "開始前的小提醒" in html
    assert "我們只會讀取頁面內容" in html
    assert "請先執行 .\\scripts\\uv.ps1 run python -m app.tools.dev_start" not in html
    assert 'name="seed_url"' not in html
    assert 'name="check_in_date"' not in html
    assert 'name="people_count"' not in html


def test_render_new_watch_page_shows_incomplete_seed_url_guidance() -> None:
    """seed URL 不完整時，頁面應顯示改用精確 URL 或 Chrome 分頁的指引。"""
    html = render_new_watch_page(
        seed_url="https://www.ikyu.com/zh-tw/00082173/",
        error_message=(
            "目前網址尚未帶齊查候選所需條件；"
            "請改用已帶日期與人數的精確 URL，或改由專用 Chrome 分頁抓取。"
        ),
    )

    assert "請改用已帶日期與人數的精確 URL" in html
    assert "專用 Chrome 分頁抓取" in html


def test_render_chrome_tab_selection_page_shows_tabs_and_throttling_signal() -> None:
    """Chrome 分頁選擇頁應顯示每個分頁與可能節流訊號。"""
    html = render_chrome_tab_selection_page(
        tabs=(
            ChromeTabSummary(
                tab_id="0",
                title="Dormy Inn",
                url="https://www.ikyu.com/zh-tw/00082173/?rm=1&pln=2",
                visibility_state="hidden",
                has_focus=False,
                was_discarded=True,
            ),
        ),
        selected_tab_id="0",
    )

    assert "選擇 Chrome 分頁" in html
    assert "Dormy Inn" in html
    assert "可能節流" in html
    assert "曾被丟棄" in html
    assert "抓取此分頁" in html
    assert 'aria-label="新增監視流程"' in html
    assert "選擇說明" in html
    assert "URL 僅作辨識" in html


def test_render_chrome_tab_selection_empty_state_uses_current_profile_hint() -> None:
    """沒有可用分頁時，提示應沿用已啟動的專用 Chrome，而不是要求重啟。"""
    html = render_chrome_tab_selection_page(tabs=())

    assert "目前找不到可用的" in html
    assert "請在目前的專用 Chrome 中打開" in html
    assert "app.tools.dev_start" not in html


def test_render_chrome_tab_selection_page_uses_site_descriptor_labels() -> None:
    """Chrome 分頁選擇頁應使用 site descriptor 顯示站點名稱。"""
    html = render_chrome_tab_selection_page(
        tabs=(
            ChromeTabSummary(
                tab_id="0",
                title="Dormy Inn",
                url="https://www.ikyu.com/zh-tw/00082173/?rm=1&pln=2",
                visibility_state="visible",
                has_focus=True,
            ),
        ),
        site_descriptors=(
            SiteDescriptor(
                site_name="ikyu",
                display_name="IKYU",
                browser_page_label="IKYU",
                browser_tab_hint="IKYU.com",
            ),
        ),
        site_labels_by_tab_id={"0": "IKYU"},
    )

    assert "IKYU.com" in html
    assert "站點：IKYU" in html


def test_render_chrome_tab_selection_page_marks_existing_watch_tabs() -> None:
    """若某個 Chrome 分頁已綁定既有 watch，應改顯示既有 watch 狀態。"""
    html = render_chrome_tab_selection_page(
        tabs=(
            ChromeTabSummary(
                tab_id="0",
                title="Dormy Inn",
                url="https://www.ikyu.com/zh-tw/00082173/?rm=1&pln=2",
                visibility_state="visible",
                has_focus=True,
            ),
        ),
        existing_watch_ids_by_tab_id={"0": "watch-list-1"},
    )

    assert "已建立監視" in html
    assert "/watches/watch-list-1" in html
    assert "抓取此分頁" not in html


def test_chrome_tab_list_page_marks_existing_watch_tabs_by_target_identity(tmp_path) -> None:
    """Chrome 分頁清單頁應在進入 preview 前就標示已建立的精確 watch。"""
    container = _build_test_container(tmp_path)
    container.chrome_tab_preview_service = _StaticChromeTabPreviewService(
        tabs=(
            ChromeTabSummary(
                tab_id="tab-a",
                title="Dormy Inn A",
                url=(
                    "https://www.ikyu.com/zh-tw/00082173/"
                    "?pln=11035620&rm=10191605&cid=20260918"
                ),
                visibility_state="visible",
                has_focus=True,
            ),
            ChromeTabSummary(
                tab_id="tab-b",
                title="Dormy Inn B",
                url=(
                    "https://www.ikyu.com/zh-tw/00082173/"
                    "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035621"
                    "&ppc=2&rc=1&rm=10191606&si=1&st=1"
                ),
                visibility_state="visible",
                has_focus=True,
            ),
        )
    )
    first_watch = _build_watch_item()
    second_watch = replace(
        _build_watch_item(),
        id="watch-list-2",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="10191606",
            plan_id="11035621",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        canonical_url=(
            "https://www.ikyu.com/zh-tw/00082173/"
            "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035621"
            "&ppc=2&rc=1&rm=10191606&si=1&st=1"
        ),
    )
    for watch_item, browser_page_url, browser_tab_id in (
        (
            first_watch,
            "https://www.ikyu.com/zh-tw/00082173/?rm=10191605&pln=11035620&cid=20260918",
            "stale-tab-a",
        ),
        (
            second_watch,
            second_watch.canonical_url,
            "stale-tab-b",
        ),
    ):
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
                browser_page_url=browser_page_url,
                browser_tab_id=browser_tab_id,
            ),
        )

    with TestClient(create_app(container)) as client:
        response = client.get("/watches/chrome-tabs")

    assert response.status_code == 200
    assert response.text.count("已建立監視") >= 2
    assert "抓取此分頁" not in response.text


def test_chrome_tab_list_page_filters_ikyu_homepage(tmp_path) -> None:
    """IKYU 首頁不應出現在可抓取清單，避免使用者選到無價格資訊頁。"""
    container = _build_test_container(tmp_path)
    container.chrome_tab_preview_service = ChromeTabPreviewService(
        chrome_fetcher=_StaticListTabsFetcher(
            tabs=(
                ChromeTabSummary(
                    tab_id="home",
                    title="IKYU",
                    url="https://www.ikyu.com/",
                    visibility_state="visible",
                    has_focus=True,
                ),
                ChromeTabSummary(
                    tab_id="hotel",
                    title="Dormy Inn",
                    url=(
                        "https://www.ikyu.com/zh-tw/00082173/"
                        "?adc=1&cid=20260918&discsort=1&lc=1"
                        "&ppc=2&rc=1&si=1&st=1"
                    ),
                    visibility_state="visible",
                    has_focus=True,
                ),
            ),
        ),
        site_registry=container.site_registry,
    )

    with TestClient(create_app(container)) as client:
        response = client.get("/watches/chrome-tabs")

    assert response.status_code == 200
    assert "Dormy Inn" in response.text
    assert "IKYU</strong>" not in response.text
    assert 'value="home"' not in response.text
    assert 'value="hotel"' in response.text


def test_chrome_tab_list_page_times_out_when_tab_listing_hangs(
    tmp_path,
    monkeypatch,
) -> None:
    """Chrome 分頁清單卡住時，GUI 應回逾時提示而不是讓頁面一直等待。"""
    container = _build_test_container(tmp_path)
    container.chrome_tab_preview_service = _SlowChromeTabPreviewService()
    monkeypatch.setattr(
        watch_creation_routes_module,
        "CHROME_TAB_LIST_TIMEOUT_SECONDS",
        0.01,
    )

    with TestClient(create_app(container)) as client:
        response = client.get("/watches/chrome-tabs")

    assert response.status_code == 504
    assert "列出專用 Chrome 分頁逾時" in response.text


def test_chrome_tab_list_page_shows_error_when_tab_listing_fails(tmp_path) -> None:
    """列分頁失敗時錯誤頁不應再次呼叫 list_tabs 導致 500。"""
    container = _build_test_container(tmp_path)
    container.chrome_tab_preview_service = _FailingChromeTabPreviewService()

    with TestClient(create_app(container)) as client:
        response = client.get("/watches/chrome-tabs")

    assert response.status_code == 400
    assert "Chrome 分頁清單失敗" in response.text
    assert "選擇 Chrome 分頁" in response.text
