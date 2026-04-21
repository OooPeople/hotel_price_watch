import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.application.app_settings import AppSettingsService
from app.application.debug_captures import (
    DebugCaptureClearResult,
    clear_debug_captures,
    list_debug_captures,
    load_debug_capture,
    load_latest_debug_capture,
)
from app.application.preview_guard import PreviewAttemptGuard
from app.application.watch_editor import WatchCreationPreview, WatchEditorService
from app.application.watch_lifecycle import WatchLifecycleCoordinator
from app.bootstrap.container import AppContainer
from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.entities import LatestCheckSnapshot, NotificationDispatchResult, WatchItem
from app.domain.enums import (
    Availability,
    NotificationLeafKind,
    RuntimeStateEventKind,
    WatchRuntimeState,
)
from app.domain.notification_rules import RuleLeaf
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser import ChromeCdpHtmlFetcher, ChromeTabSummary
from app.infrastructure.db import (
    SqliteAppSettingsRepository,
    SqliteDatabase,
    SqliteRuntimeRepository,
    SqliteWatchItemRepository,
)
from app.main import create_app
from app.monitor.runtime import MonitorRuntimeStatus
from app.sites.base import CandidateBundle, LookupDiagnostic, OfferCandidate, SiteDescriptor
from app.sites.ikyu import IkyuAdapter
from app.sites.registry import SiteRegistry
from app.web.routes import debug_routes as debug_routes_module
from app.web.views import (
    render_chrome_tab_selection_page,
    render_debug_capture_detail_page,
    render_debug_capture_list_page,
    render_new_watch_page,
    render_notification_channel_settings_page,
    render_notification_settings_page,
    render_watch_detail_page,
    render_watch_list_page,
)


class _FakeMonitorRuntime:
    """模擬 app lifespan 用的最小 monitor runtime。"""

    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.check_now_calls: list[str] = []

    async def start(self) -> None:
        """記錄 runtime 已啟動。"""
        self.started += 1

    async def stop(self) -> None:
        """記錄 runtime 已停止。"""
        self.stopped += 1

    def get_status(self) -> MonitorRuntimeStatus:
        """提供首頁與 health endpoint 使用的 runtime 狀態摘要。"""
        return MonitorRuntimeStatus(
            is_running=self.started > self.stopped,
            enabled_watch_count=1,
            registered_watch_count=1,
            inflight_watch_count=0,
            chrome_debuggable=True,
            last_tick_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
            last_watch_sync_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        )

    async def request_check_now(self, watch_item_id: str) -> None:
        """記錄 GUI 是否要求立刻檢查指定 watch。"""
        self.check_now_calls.append(watch_item_id)


def _local_request_headers() -> dict[str, str]:
    """建立通過本機管理介面來源驗證所需的測試 header。"""
    return {
        "origin": "http://127.0.0.1",
        "referer": "http://127.0.0.1/",
    }


def test_create_app_registers_gui_routes(tmp_path) -> None:
    """驗證 app factory 會註冊 GUI 需要的主要 route。"""
    container = _build_test_container(tmp_path)

    app = create_app(container)
    paths = {route.path for route in app.routes}

    assert "/" in paths
    assert "/watches/new" in paths
    assert "/watches/chrome-tabs" in paths
    assert "/watches/preview" in paths
    assert "/watches/chrome-tabs/preview" in paths
    assert "/watches" in paths
    assert "/watches/{watch_item_id}" in paths
    assert "/watches/{watch_item_id}/delete" in paths
    assert "/watches/{watch_item_id}/enable" in paths
    assert "/watches/{watch_item_id}/disable" in paths
    assert "/watches/{watch_item_id}/pause" in paths
    assert "/watches/{watch_item_id}/resume" in paths
    assert "/watches/{watch_item_id}/check-now" in paths
    assert "/debug/captures" in paths
    assert "/debug/captures/latest" in paths
    assert "/debug/captures/{capture_id}" in paths
    assert "/debug/captures/{capture_id}/html" in paths
    assert "/debug/captures/clear" in paths
    assert "/watches/{watch_item_id}/notification-settings" in paths
    assert "/settings" in paths
    assert "/settings/test-notification" in paths
    assert "/settings/notifications" in paths
    assert "/settings/notifications/test" in paths


def test_create_app_lifespan_starts_and_stops_monitor_runtime(tmp_path) -> None:
    """FastAPI lifespan 應在啟停時呼叫 monitor runtime。"""
    container = _build_test_container(tmp_path)
    fake_runtime = _FakeMonitorRuntime()
    container.monitor_runtime = fake_runtime

    with TestClient(create_app(container)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert fake_runtime.started == 1
    assert fake_runtime.stopped == 1


def test_health_includes_runtime_status(tmp_path) -> None:
    """health endpoint 會回傳 background monitor runtime 的狀態摘要。"""
    container = _build_test_container(tmp_path)
    fake_runtime = _FakeMonitorRuntime()
    container.monitor_runtime = fake_runtime

    with TestClient(create_app(container)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["instance_id"] == "test-instance"
    assert payload["runtime"]["is_running"] is True
    assert payload["runtime"]["enabled_watch_count"] == 1
    assert payload["runtime"]["chrome_debuggable"] is True


def test_watch_list_fragments_endpoint_returns_runtime_and_rows(tmp_path) -> None:
    """首頁 fragments endpoint 應回傳局部更新所需的 HTML 片段。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    fake_runtime = _FakeMonitorRuntime()
    container.monitor_runtime = fake_runtime

    with TestClient(create_app(container)) as client:
        response = client.get("/fragments/watch-list")

    assert response.status_code == 200
    payload = response.json()
    assert "Background Monitor" in payload["runtime_html"]
    assert "Ocean Hotel" in payload["table_body_html"]


def test_watch_detail_fragments_endpoint_returns_partial_sections(tmp_path) -> None:
    """watch 詳細頁 fragments endpoint 應回傳三個主要局部區塊。"""
    container = _build_test_container(tmp_path)
    watch_item = _build_watch_item()
    container.watch_item_repository.save(watch_item)
    container.runtime_repository.save_latest_check_snapshot(_build_latest_snapshot())
    container.runtime_repository.append_check_event(_build_check_event())
    container.runtime_repository.save_notification_state(_build_notification_state())
    container.runtime_repository.append_debug_artifact(
        _build_debug_artifact(),
        retention_limit=10,
    )

    with TestClient(create_app(container)) as client:
        response = client.get(f"/watches/{watch_item.id}/fragments")

    assert response.status_code == 200
    payload = response.json()
    assert "最近摘要" in payload["latest_section_html"]
    assert "檢查歷史" in payload["check_events_section_html"]
    assert "Debug Artifacts" in payload["debug_artifacts_section_html"]


def test_render_watch_list_page_shows_existing_watch_items() -> None:
    """驗證 watch 列表頁會顯示既有 watch item 與 runtime 摘要。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        runtime_status=MonitorRuntimeStatus(
            is_running=True,
            enabled_watch_count=1,
            registered_watch_count=1,
            inflight_watch_count=0,
            chrome_debuggable=True,
            last_tick_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
            last_watch_sync_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        ),
        flash_message="已建立 watch",
    )

    assert "Ocean Hotel" in html
    assert "Standard Twin" in html
    assert "已建立 watch" in html
    assert "刪除" in html
    assert "暫停" in html
    assert "停用" in html
    assert "/watches/watch-list-1" in html
    assert "/settings" in html
    assert "Background Monitor" in html


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
    assert "建立 Watch Item" in html
    assert "總價：JPY 24000" in html
    assert "每人每晚：約 JPY 12000" in html
    assert "從同一個 Chrome 分頁重新抓取" in html
    assert "Dormy Tab" in html
    assert "tab id:" not in html
    assert "從專用 Chrome 建立 Watch" in html
    assert (
        f'value="{NotificationLeafKind.BELOW_TARGET_PRICE.value}"'
        in html
    )
    assert "selected" in html


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

    assert "目前選定目標已建立 watch" in html
    assert "/watches/watch-list-1" in html
    assert "已建立 watch" in html
    assert "建立 Watch Item" not in html


def test_render_new_watch_page_shows_debug_capture_paths() -> None:
    """候選為空時若已保存 debug capture，頁面應顯示檔案路徑。"""
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

    assert "ikyu_preview_last.html" in html
    assert "ikyu_preview_last_meta.json" in html


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
    """新增頁應提示一鍵啟動命令，並保留專用 Chrome 的使用脈絡。"""
    html = render_new_watch_page(
        seed_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
    )

    assert "app.tools.dev_start" in html
    assert "專用 Chrome profile" in html
    assert "從目前專用 Chrome 頁面抓取" in html
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

    assert "從目前專用 Chrome 頁面抓取" in html
    assert "Dormy Inn" in html
    assert "可能節流" in html
    assert "曾被丟棄" in html
    assert "抓取此分頁" in html


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

    assert "已建立 watch" in html
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
    assert response.text.count("已建立 watch") >= 2
    assert "抓取此分頁" not in response.text


def test_render_notification_settings_page_shows_current_rule() -> None:
    """通知設定頁應顯示目前已保存的通知條件。"""
    html = render_notification_settings_page(
        watch_item=_build_watch_item_with_below_target_rule(),
        flash_message="已更新 通知設定",
    )

    assert "通知設定" in html
    assert "低於目標價" in html
    assert 'value="20000"' in html
    assert "已更新 通知設定" in html


def test_render_notification_channel_settings_page_shows_saved_values() -> None:
    """設定頁應顯示目前已保存的通道與顯示設定。"""
    html = render_notification_channel_settings_page(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=True,
            ntfy_server_url="https://ntfy.example.com",
            ntfy_topic="hotel-watch",
            discord_enabled=True,
            discord_webhook_url="https://discord.example.com/webhook",
        ),
        flash_message="已更新 通知通道設定",
    )

    assert "設定" in html
    assert "hotel-watch" in html
    assert "https://discord.example.com/webhook" in html
    assert "已更新 通知通道設定" in html
    assert "發送測試通知" in html
    assert "12 小時制" in html
    assert "24 小時制" in html
    assert 'name="time_format_24h"' in html
    assert 'id="global-settings-form"' in html
    assert "尚未儲存" in html
    assert "beforeunload" in html


def test_render_notification_channel_settings_page_shows_structured_test_result() -> None:
    """測試通知結果應以結構化區塊呈現各通道狀態與失敗原因。"""
    html = render_notification_channel_settings_page(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=True,
            ntfy_server_url="https://ntfy.example.com",
            ntfy_topic="hotel-watch",
            discord_enabled=True,
            discord_webhook_url="https://discord.example.com/webhook",
        ),
        test_result_message=(
            "測試通知結果：sent=desktop；"
            "throttled=none；"
            "failed=ntfy, discord；"
            "details=ntfy: timed out | discord: HTTP Error 400"
        ),
    )

    assert "測試通知結果" in html
    assert "成功通道：desktop" in html
    assert "失敗通道：ntfy, discord" in html
    assert "失敗原因：ntfy: timed out | discord: HTTP Error 400" in html


def test_render_notification_settings_page_shows_any_drop_hint() -> None:
    """價格下降規則時，畫面應明示目標價會被忽略。"""
    html = render_notification_settings_page(
        watch_item=_build_watch_item(),
    )

    assert "目標價欄位會被忽略" in html
    assert 'id="notification-target-price-wrapper"' in html
    assert "display:none" in html


def test_post_debug_capture_clear_redirects_partial_failure_message(tmp_path, monkeypatch) -> None:
    """清空 debug captures 若有失敗，應把部分失敗結果回報給 UI。"""
    client = TestClient(create_app(_build_test_container(tmp_path)))

    def fake_clear_debug_captures():
        return DebugCaptureClearResult(
            removed_count=2,
            failed_paths=("debug/ikyu_preview_locked.html",),
        )

    monkeypatch.setattr(
        debug_routes_module,
        "clear_debug_captures",
        fake_clear_debug_captures,
    )

    response = client.post(
        "/debug/captures/clear",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    message = parse_qs(urlparse(response.headers["location"]).query)["message"][0]
    assert "另有 1 個刪除失敗" in message


def test_post_notification_settings_allows_any_drop_with_target_price_input(tmp_path) -> None:
    """通知設定頁在 any_drop 下應忽略 target_price，而不是回 400。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("18000"),
    )
    client = TestClient(create_app(container))

    response = client.post(
        f"/watches/{watch_item.id}/notification-settings",
        data={
            "notification_rule_kind": NotificationLeafKind.ANY_DROP.value,
            "target_price": "20000",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated_watch_item = container.watch_item_repository.get(watch_item.id)
    assert updated_watch_item is not None
    assert updated_watch_item.notification_rule == RuleLeaf(
        kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )


def test_post_notification_settings_preserves_invalid_form_value(tmp_path) -> None:
    """通知設定儲存失敗時應保留使用者剛輸入的表單值。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("18000"),
    )
    client = TestClient(create_app(container))

    response = client.post(
        f"/watches/{watch_item.id}/notification-settings",
        data={
            "notification_rule_kind": NotificationLeafKind.BELOW_TARGET_PRICE.value,
            "target_price": "abc",
        },
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert 'value="abc"' in response.text
    assert "目標價格式不正確" in response.text


def test_post_global_notification_settings_updates_channels(tmp_path) -> None:
    """全域設定頁應可保存通知通道與顯示偏好。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_enabled": "on",
            "ntfy_server_url": "https://ntfy.example.com",
            "ntfy_topic": "hotel-watch",
            "discord_enabled": "on",
            "discord_webhook_url": "https://discord.example.com/webhook",
            "time_format_24h": "on",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = container.app_settings_service.get_notification_channel_settings()
    assert settings == NotificationChannelSettings(
        desktop_enabled=True,
        ntfy_enabled=True,
        ntfy_server_url="https://ntfy.example.com",
        ntfy_topic="hotel-watch",
        discord_enabled=True,
        discord_webhook_url="https://discord.example.com/webhook",
    )
    assert container.app_settings_service.get_display_settings() == DisplaySettings(
        use_24_hour_time=True,
    )


def test_post_global_settings_can_switch_to_12_hour_time(tmp_path) -> None:
    """取消 24 小時制 checkbox 後，應保存為 12 小時制偏好。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_server_url": "https://ntfy.sh",
            "time_format_12h": "on",
        },
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert container.app_settings_service.get_display_settings() == DisplaySettings(
        use_24_hour_time=False,
    )


def test_post_global_settings_rejects_multiple_time_formats(tmp_path) -> None:
    """時間格式設定若同時勾選兩項，後端應拒絕保存。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_server_url": "https://ntfy.sh",
            "time_format_12h": "on",
            "time_format_24h": "on",
        },
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert "請選擇 12 小時制或 24 小時制其中一項" in response.text


def test_post_global_notification_test_uses_saved_dispatch_path(tmp_path) -> None:
    """測試通知應走正式 dispatcher / notifier 路徑，並回報各通道結果。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings/test-notification",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    test_message = parse_qs(urlparse(location).query)["test_message"][0]
    assert "sent=desktop" in test_message
    assert "details=none" in test_message


def test_post_global_notification_test_requires_enabled_channel(tmp_path) -> None:
    """若沒有任何已啟用通道，測試通知應直接回報錯誤。"""
    container = _build_test_container(tmp_path)
    container.notification_channel_test_service.enabled = False
    client = TestClient(create_app(container))

    response = client.post(
        "/settings/test-notification",
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert "目前沒有任何已啟用的通知通道可供測試" in response.text


def test_post_watch_disable_updates_status(tmp_path) -> None:
    """停用 watch route 應把 watch 標成 disabled。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    client = TestClient(create_app(container))

    response = client.post(
        "/watches/watch-list-1/disable",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated_watch = container.watch_item_repository.get("watch-list-1")
    assert updated_watch is not None
    assert updated_watch.enabled is False
    assert updated_watch.paused_reason == "manually_disabled"


def test_post_watch_pause_and_resume_updates_status(tmp_path) -> None:
    """暫停與恢復 watch route 應正確切換 paused 狀態。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    client = TestClient(create_app(container))

    pause_response = client.post(
        "/watches/watch-list-1/pause",
        headers=_local_request_headers(),
        follow_redirects=False,
    )
    assert pause_response.status_code == 303
    paused_watch = container.watch_item_repository.get("watch-list-1")
    assert paused_watch is not None
    assert paused_watch.enabled is True
    assert paused_watch.paused_reason == "manually_paused"

    resume_response = client.post(
        "/watches/watch-list-1/resume",
        headers=_local_request_headers(),
        follow_redirects=False,
    )
    assert resume_response.status_code == 303
    resumed_watch = container.watch_item_repository.get("watch-list-1")
    assert resumed_watch is not None
    assert resumed_watch.enabled is True
    assert resumed_watch.paused_reason is None


def test_post_watch_resume_records_recover_pending_transition(tmp_path) -> None:
    """從 403 暫停恢復時，手動事件應保留 latest snapshot 的恢復待驗證語意。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(
        replace(_build_watch_item(), paused_reason="http_403")
    )
    container.runtime_repository.save_latest_check_snapshot(
        LatestCheckSnapshot(
            watch_item_id="watch-list-1",
            checked_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            availability=Availability.UNKNOWN,
            normalized_price_amount=None,
            currency=None,
            last_error_code="http_403",
            consecutive_failures=1,
        )
    )
    client = TestClient(create_app(container))

    response = client.post(
        "/watches/watch-list-1/resume",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    runtime_state_events = container.runtime_repository.list_runtime_state_events(
        "watch-list-1"
    )
    assert runtime_state_events[0].event_kind is RuntimeStateEventKind.MANUAL_RESUME
    assert runtime_state_events[0].from_state is WatchRuntimeState.PAUSED_BLOCKED
    assert runtime_state_events[0].to_state is WatchRuntimeState.RECOVER_PENDING


def test_post_watch_enable_reactivates_disabled_watch(tmp_path) -> None:
    """啟用 route 應可把 disabled watch 恢復為 enabled。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    disabled_watch = container.watch_item_repository.get("watch-list-1")
    assert disabled_watch is not None
    container.watch_item_repository.save(
        replace(
            disabled_watch,
            enabled=False,
            paused_reason="manually_disabled",
        )
    )
    client = TestClient(create_app(container))

    response = client.post(
        "/watches/watch-list-1/enable",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    enabled_watch = container.watch_item_repository.get("watch-list-1")
    assert enabled_watch is not None
    assert enabled_watch.enabled is True
    assert enabled_watch.paused_reason is None


def test_post_watch_check_now_calls_monitor_runtime(tmp_path) -> None:
    """立即檢查 route 應呼叫 runtime 的 check-now 入口。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    fake_runtime = _FakeMonitorRuntime()
    container.monitor_runtime = fake_runtime
    container.watch_lifecycle_coordinator = WatchLifecycleCoordinator(
        watch_item_repository=container.watch_item_repository,
        runtime_repository=container.runtime_repository,
        monitor_runtime=fake_runtime,
    )
    client = TestClient(create_app(container))

    response = client.post(
        "/watches/watch-list-1/check-now",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_runtime.check_now_calls == ["watch-list-1"]


def test_post_watch_check_now_rejects_paused_watch(tmp_path) -> None:
    """立即檢查 route 應拒絕已暫停的 watch，避免繞過 lifecycle gate。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(
        replace(_build_watch_item(), paused_reason="manually_paused")
    )
    fake_runtime = _FakeMonitorRuntime()
    container.monitor_runtime = fake_runtime
    container.watch_lifecycle_coordinator = WatchLifecycleCoordinator(
        watch_item_repository=container.watch_item_repository,
        runtime_repository=container.runtime_repository,
        monitor_runtime=fake_runtime,
    )
    client = TestClient(create_app(container))

    response = client.post(
        "/watches/watch-list-1/check-now",
        headers=_local_request_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert fake_runtime.check_now_calls == []


def test_state_changing_post_rejects_missing_origin_headers(tmp_path) -> None:
    """缺少 Origin 與 Referer 時，state-changing POST 應被拒絕。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    client = TestClient(create_app(container))

    response = client.post("/watches/watch-list-1/disable", follow_redirects=False)

    assert response.status_code == 403
    assert "missing request origin" in response.text


def test_state_changing_post_rejects_non_local_origin(tmp_path) -> None:
    """來自非本機來源的 POST 應被拒絕。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    client = TestClient(create_app(container))

    response = client.post(
        "/watches/watch-list-1/disable",
        headers={
            "origin": "https://evil.example.com",
            "referer": "https://evil.example.com/pwn",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert "invalid request origin" in response.text


def test_post_global_notification_settings_preserves_invalid_form_value(tmp_path) -> None:
    """設定儲存失敗時應保留使用者剛輸入的值。"""
    container = _build_test_container(tmp_path)
    client = TestClient(create_app(container))

    response = client.post(
        "/settings",
        data={
            "desktop_enabled": "on",
            "ntfy_enabled": "on",
            "ntfy_server_url": "https://ntfy.example.com",
            "ntfy_topic": "",
            "discord_enabled": "on",
            "discord_webhook_url": "https://discord.example.com/webhook",
            "time_format_24h": "on",
        },
        headers=_local_request_headers(),
    )

    assert response.status_code == 400
    assert "必須填寫 topic" in response.text
    assert 'value="https://ntfy.example.com"' in response.text
    assert 'value="https://discord.example.com/webhook"' in response.text


def test_render_watch_list_page_shows_debug_link() -> None:
    """列表頁應提供進入 debug captures 的入口。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        flash_message=None,
    )

    assert "/debug/captures" in html
    assert "Debug 區" in html


def test_render_watch_list_page_includes_polling_script() -> None:
    """首頁應帶局部更新 polling script，而不是依賴整頁刷新。"""
    html = render_watch_list_page(watch_items=(_build_watch_item(),))

    assert "/fragments/watch-list" in html
    assert "watch-list-table-body" in html
    assert "runtime-status-section" in html
    assert "setInterval(refresh, 15000)" in html


def test_render_watch_detail_page_shows_runtime_sections() -> None:
    """watch 詳細頁應顯示歷史與 debug artifact 區塊。"""
    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        check_events=(_build_check_event(),),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(
            _build_debug_artifact(),
            _build_discarded_debug_artifact(),
        ),
        flash_message="已觸發 立即檢查",
    )

    assert "最近摘要" in html
    assert "檢查歷史" in html
    assert "Debug Artifacts" in html
    assert "background runtime 寫入的 debug artifact" in html
    assert "preview captures" in html
    assert "http_403" in html
    assert "分頁曾被瀏覽器丟棄" in html
    assert "通知設定" in html
    assert "最近 runtime 訊號" in html
    assert "解析失敗 1 次" in html
    assert "分頁曾被瀏覽器丟棄 1 次" in html
    assert "立即檢查" in html
    assert "已觸發 立即檢查" in html


def test_render_watch_detail_page_includes_polling_script() -> None:
    """watch 詳細頁應帶局部更新 polling script，而不是依賴整頁刷新。"""
    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        check_events=(_build_check_event(),),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(_build_debug_artifact(),),
    )

    assert "/watches/watch-list-1/fragments" in html
    assert "watch-detail-latest-section" in html
    assert "watch-detail-check-events-section" in html
    assert "watch-detail-debug-artifacts-section" in html
    assert "setInterval(refresh, 10000)" in html


def test_render_debug_capture_pages_show_capture_content(tmp_path) -> None:
    """debug capture 頁面應能顯示 capture 列表與內容。"""
    capture = _write_debug_capture(tmp_path)
    loaded_capture = load_debug_capture(capture["capture_id"], tmp_path / "debug")
    assert loaded_capture is not None

    list_html = render_debug_capture_list_page(
        captures=(loaded_capture.summary,),
    )
    detail_html = render_debug_capture_detail_page(capture=loaded_capture)

    assert capture["capture_id"] in list_html
    assert "這裡只列出建立 watch / preview 流程保存的 capture" in list_html
    assert "成功解析出 1 筆候選房型方案。" in detail_html
    assert "這裡只顯示 preview capture" in detail_html
    assert "Metadata JSON" in detail_html
    assert "清空紀錄" in list_html


def test_render_debug_capture_detail_page_handles_summary_only_capture(tmp_path) -> None:
    """成功摘要模式即使沒有 HTML，也應能在 debug 頁正常顯示。"""
    capture = _write_debug_capture(
        tmp_path,
        capture_id="ikyu_preview_20260412T040000Z",
        include_html=False,
    )
    loaded_capture = load_debug_capture(capture["capture_id"], tmp_path / "debug")

    assert loaded_capture is not None
    detail_html = render_debug_capture_detail_page(capture=loaded_capture)

    assert "未保存完整 HTML" in detail_html
    assert "成功摘要紀錄" in detail_html


def test_load_latest_debug_capture_reads_latest_timestamped_capture(tmp_path) -> None:
    """debug capture reader 應能讀出最新一筆時間序列檔案。"""
    first_capture = _write_debug_capture(
        tmp_path,
        capture_id="ikyu_preview_20260412T020000Z",
        captured_at=datetime(2026, 4, 12, 2, 0, tzinfo=timezone.utc),
    )
    second_capture = _write_debug_capture(
        tmp_path,
        capture_id="ikyu_preview_20260412T030000Z",
        captured_at=datetime(2026, 4, 12, 3, 0, tzinfo=timezone.utc),
    )

    latest_capture = load_latest_debug_capture(tmp_path / "debug")

    assert latest_capture is not None
    assert latest_capture.summary.capture_id == second_capture["capture_id"]
    assert latest_capture.summary.capture_id != first_capture["capture_id"]


def test_list_debug_captures_can_filter_by_site(tmp_path) -> None:
    """debug capture reader 應能用 site name 過濾不同站點的紀錄。"""
    _write_debug_capture(
        tmp_path,
        capture_id="ikyu_preview_20260412T020000Z",
        site_name="ikyu",
    )
    _write_debug_capture(
        tmp_path,
        capture_id="second_site_preview_20260412T030000Z",
        site_name="second_site",
    )

    captures = list_debug_captures(tmp_path / "debug", site_name="ikyu")

    assert len(captures) == 1
    assert captures[0].site_name == "ikyu"
    assert captures[0].capture_id == "ikyu_preview_20260412T020000Z"


def test_clear_debug_captures_removes_saved_files(tmp_path) -> None:
    """debug capture 清空功能應刪除既有的 capture 檔案。"""
    _write_debug_capture(tmp_path)

    clear_result = clear_debug_captures(tmp_path / "debug")

    assert clear_result.removed_count >= 1
    assert clear_result.failed_paths == ()
    assert list((tmp_path / "debug").glob("ikyu_preview_*")) == []


def test_watch_editor_service_creates_watch_item_and_saves_it(tmp_path) -> None:
    """驗證 watch editor service 可由 preview 建立並保存 watch item。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )

    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )

    saved_items = container.watch_item_repository.list_all()
    assert len(saved_items) == 1
    assert saved_items[0].id == watch_item.id
    assert saved_items[0].notification_rule == RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )
    assert saved_items[0].target.check_in_date == date(2026, 9, 18)


def test_watch_editor_service_can_delete_saved_watch_item(tmp_path) -> None:
    """watch editor service 應能刪除既有 watch item。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )

    container.watch_editor_service.delete_watch_item(watch_item.id)

    assert container.watch_item_repository.list_all() == []


def test_watch_editor_service_can_update_notification_rule(tmp_path) -> None:
    """watch editor service 應能更新既有 watch item 的通知條件。"""
    container = _build_test_container(tmp_path)
    preview = container.watch_editor_service.preview_from_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/?top=rooms"
    )
    watch_item = container.watch_editor_service.create_watch_item_from_preview(
        preview=preview,
        room_id="room-1",
        plan_id="plan-1",
        scheduler_interval_seconds=600,
        notification_rule_kind=NotificationLeafKind.ANY_DROP,
        target_price=None,
    )

    updated_watch_item = container.watch_editor_service.update_notification_rule(
        watch_item_id=watch_item.id,
        notification_rule_kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )

    assert updated_watch_item.notification_rule == RuleLeaf(
        kind=NotificationLeafKind.BELOW_TARGET_PRICE,
        target_price=Decimal("20000"),
    )
    assert container.watch_item_repository.get(watch_item.id) == updated_watch_item


def test_preview_guard_blocks_immediate_retry_after_blocked_page() -> None:
    """命中阻擋頁後，下一次 preview 應直接被 guard 擋下。"""
    guard = PreviewAttemptGuard(
        min_interval_seconds=20.0,
        blocked_page_cooldown_seconds=1800.0,
    )

    guard.register_result(
        site_name="ikyu",
        diagnostics=(
            LookupDiagnostic(
                stage="browser_fallback_direct",
                status="failed",
                detail="ikyu 已回傳阻擋頁面；目前連 browser fallback 都被站方防護攔下。",
            ),
        )
    )

    try:
        guard.ensure_allowed(site_name="ikyu")
    except ValueError as exc:
        assert "冷卻中" in str(exc)
        assert exc.diagnostics[0].stage == "preview_rate_guard"
    else:
        raise AssertionError("expected preview guard to block immediate retry")


def test_preview_guard_cooldown_is_scoped_by_site() -> None:
    """不同站點的 preview 冷卻不應互相阻擋。"""
    guard = PreviewAttemptGuard(
        min_interval_seconds=20.0,
        blocked_page_cooldown_seconds=1800.0,
    )

    guard.register_result(
        site_name="ikyu",
        diagnostics=(
            LookupDiagnostic(
                stage="browser_fallback_direct",
                status="failed",
                detail="ikyu 已回傳阻擋頁面；目前連 browser fallback 都被站方防護攔下。",
            ),
        ),
    )

    guard.ensure_allowed(site_name="second_site")
    try:
        guard.ensure_allowed(site_name="ikyu")
    except ValueError:
        return
    raise AssertionError("expected ikyu cooldown to remain active")


class FakeWatchEditorService(WatchEditorService):
    """用固定資料模擬 watch editor 流程。"""

    def __init__(
        self,
        watch_item_repository: SqliteWatchItemRepository,
    ) -> None:
        super().__init__(
            site_registry=SiteRegistry(),
            watch_item_repository=watch_item_repository,
        )
        self._watch_item_repository = watch_item_repository

    def preview_from_seed_url(self, seed_url: str) -> WatchCreationPreview:
        """回傳固定的預覽結果，避免在 web 測試中依賴真站抓取。"""
        return _build_preview(seed_url)

    def mark_existing_watch_for_preview(
        self,
        preview: WatchCreationPreview,
    ) -> WatchCreationPreview:
        """web route 測試不依賴真實 target 比對，直接回傳原 preview。"""
        return preview

    def create_watch_item_from_preview(
        self,
        *,
        preview: WatchCreationPreview,
        room_id: str,
        plan_id: str,
        scheduler_interval_seconds: int,
        notification_rule_kind: NotificationLeafKind,
        target_price: Decimal | None,
    ) -> WatchItem:
        """回傳並保存固定的 watch item。"""
        watch_item = WatchItem(
            id="watch-test-1",
            target=WatchTarget(
                site="ikyu",
                hotel_id=preview.draft.hotel_id or "00082173",
                room_id=room_id,
                plan_id=plan_id,
                check_in_date=preview.draft.check_in_date or date(2026, 9, 18),
                check_out_date=preview.draft.check_out_date or date(2026, 9, 19),
                people_count=preview.draft.people_count or 2,
                room_count=preview.draft.room_count or 1,
            ),
            hotel_name="Ocean Hotel",
            room_name="Standard Twin",
            plan_name="Room Only",
            canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            notification_rule=RuleLeaf(
                kind=notification_rule_kind,
                target_price=target_price,
            ),
            scheduler_interval_seconds=scheduler_interval_seconds,
        )
        self._watch_item_repository.save(watch_item)
        return watch_item


class FakeChromeTabPreviewService:
    """提供固定 Chrome 分頁與 preview 的測試替身。"""

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """回傳固定的 `ikyu` Chrome 分頁清單。"""
        return (
            ChromeTabSummary(
                tab_id="0",
                title="Dormy Inn",
                url="https://www.ikyu.com/zh-tw/00082173/?pln=11035620&rm=10191605",
                visibility_state="visible",
                has_focus=True,
            ),
        )

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """依指定分頁回傳固定 preview。"""
        assert tab_id == "0"
        return _build_preview(
            "https://www.ikyu.com/zh-tw/00082173/?pln=11035620&rm=10191605",
            browser_tab_id="0",
            browser_tab_title="Dormy Inn",
        )


class _StaticChromeTabPreviewService:
    """提供固定分頁清單的假 Chrome preview service。"""

    def __init__(self, *, tabs: tuple[ChromeTabSummary, ...]) -> None:
        """保存測試用固定分頁，讓 route-level 測試可精準控制輸入。"""
        self._tabs = tabs

    def list_tabs(self) -> tuple[ChromeTabSummary, ...]:
        """回傳預先配置的 Chrome 分頁清單。"""
        return self._tabs

    def preview_from_tab_id(self, tab_id: str) -> WatchCreationPreview:
        """依 tab id 回傳對應分頁的最小 preview。"""
        tab = next(tab for tab in self._tabs if tab.tab_id == tab_id)
        return _build_preview(
            tab.url,
            browser_tab_id=tab.tab_id,
            browser_tab_title=tab.title,
        )


class _PreviewTestAdapter:
    """提供真實 preview service 測試用的最小 adapter。"""

    site_name = "ikyu"

    def match_url(self, url: str) -> bool:
        return "ikyu.com" in url

    def parse_seed_url(self, url: str) -> SearchDraft:
        return SearchDraft(
            seed_url=url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )

    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        return draft

    def fetch_candidates(self, draft: SearchDraft) -> CandidateBundle:
        return _build_preview(draft.seed_url).candidate_bundle

    def build_preview_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        diagnostics=(),
    ) -> tuple[SearchDraft, CandidateBundle]:
        preview = _build_preview(page_url, browser_tab_id="0", browser_tab_title="Dormy Inn")
        return preview.draft, preview.candidate_bundle

    def resolve_watch_target(self, draft: SearchDraft, selection) -> WatchTarget:
        return WatchTarget(
            site="ikyu",
            hotel_id=draft.hotel_id or "00082173",
            room_id=selection.room_id,
            plan_id=selection.plan_id,
            check_in_date=draft.check_in_date or date(2026, 9, 18),
            check_out_date=draft.check_out_date or date(2026, 9, 19),
            people_count=draft.people_count or 2,
            room_count=draft.room_count or 1,
        )


def _build_real_preview_registry() -> SiteRegistry:
    """建立測試 real watch editor service 時使用的 registry。"""
    registry = SiteRegistry()
    registry.register(_PreviewTestAdapter())
    return registry


def _build_test_container(tmp_path) -> AppContainer:
    """建立 web 測試用的依賴容器。"""
    database = SqliteDatabase(tmp_path / "watcher.db")
    database.initialize()
    app_settings_repository = SqliteAppSettingsRepository(database)
    watch_repository = SqliteWatchItemRepository(database)
    runtime_repository = SqliteRuntimeRepository(database)
    site_registry = SiteRegistry()
    site_registry.register(IkyuAdapter())
    watch_editor_service = FakeWatchEditorService(watch_repository)
    return AppContainer(
        instance_id="test-instance",
        database=database,
        app_settings_repository=app_settings_repository,
        watch_item_repository=watch_repository,
        runtime_repository=runtime_repository,
        site_registry=site_registry,
        app_settings_service=AppSettingsService(app_settings_repository),
        notification_channel_test_service=_FakeNotificationChannelTestService(),
        watch_editor_service=watch_editor_service,
        watch_lifecycle_coordinator=WatchLifecycleCoordinator(
            watch_item_repository=watch_repository,
            runtime_repository=runtime_repository,
            monitor_runtime=None,
        ),
        chrome_tab_preview_service=FakeChromeTabPreviewService(),
        chrome_cdp_fetcher=ChromeCdpHtmlFetcher(),
        preview_attempt_guard=PreviewAttemptGuard(),
        monitor_runtime=None,
    )


class _FakeNotificationChannelTestService:
    """提供全域通知測試 route 所需的最小替身。"""

    def __init__(self) -> None:
        self.enabled = True

    def send_test_notification(self) -> NotificationDispatchResult:
        """回傳固定的測試通知結果，模擬正式 dispatcher 路徑。"""
        if not self.enabled:
            raise ValueError("目前沒有任何已啟用的通知通道可供測試。")
        return NotificationDispatchResult(
            sent_channels=("desktop",),
            throttled_channels=(),
            failed_channels=(),
            attempted_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        )


def _write_debug_capture(
    tmp_path,
    *,
    capture_id: str = "ikyu_preview_20260412T022211Z",
    site_name: str = "ikyu",
    captured_at: datetime | None = None,
    include_html: bool = True,
) -> dict[str, str]:
    """建立 debug capture 測試資料。"""
    debug_dir = tmp_path / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    html_path = debug_dir / f"{capture_id}.html"
    meta_path = debug_dir / f"{capture_id}_meta.json"
    if include_html:
        html_path.write_text("<html><body>candidate page</body></html>", encoding="utf-8")

    payload = {
        "site_name": site_name,
        "captured_at_utc": (
            captured_at or datetime(2026, 4, 12, 2, 22, 11, tzinfo=timezone.utc)
        ).isoformat(),
        "seed_url": "https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        "parsed_hotel_name": "Ocean Hotel",
        "html_path": str(html_path) if include_html else None,
        "metadata_path": str(meta_path),
        "candidate_count": 1,
        "diagnostics": [
            {
                "stage": "candidate_parse",
                "status": "success",
                "detail": "成功解析出 1 筆候選房型方案。",
                "cooldown_seconds": None,
            }
        ],
    }
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "capture_id": capture_id,
        "html_path": str(html_path),
        "meta_path": str(meta_path),
    }


def _build_preview(
    seed_url: str,
    *,
    browser_tab_id: str | None = None,
    browser_tab_title: str | None = None,
) -> WatchCreationPreview:
    """建立新增頁測試共用的 preview。"""
    return WatchCreationPreview(
        draft=SearchDraft(
            seed_url=seed_url,
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
            room_id="room-1",
            plan_id="plan-1",
        ),
        candidate_bundle=CandidateBundle(
            hotel_id="00082173",
            hotel_name="Ocean Hotel",
            canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
            candidates=(
                OfferCandidate(
                    room_id="room-1",
                    room_name="Standard Twin",
                    plan_id="plan-1",
                    plan_name="Room Only",
                    display_price_text="JPY 24000",
                    normalized_price_amount=Decimal("24000"),
                    currency="JPY",
                ),
            ),
        ),
        preselected_room_id="room-1",
        preselected_plan_id="plan-1",
        preselected_still_valid=True,
        browser_tab_id=browser_tab_id,
        browser_tab_title=browser_tab_title,
    )


def _build_watch_item() -> WatchItem:
    """建立列表頁測試共用的 watch item。"""
    return WatchItem(
        id="watch-list-1",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="room-1",
            plan_id="plan-1",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Ocean Hotel",
        room_name="Standard Twin",
        plan_name="Room Only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        notification_rule=RuleLeaf(kind=NotificationLeafKind.ANY_DROP),
        scheduler_interval_seconds=600,
    )


def _build_watch_item_with_below_target_rule() -> WatchItem:
    """建立通知設定頁測試用的低於目標價 watch item。"""
    return WatchItem(
        id="watch-list-2",
        target=WatchTarget(
            site="ikyu",
            hotel_id="00082173",
            room_id="room-2",
            plan_id="plan-2",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        ),
        hotel_name="Ocean Hotel",
        room_name="Standard Twin",
        plan_name="Room Only",
        canonical_url="https://www.ikyu.com/zh-tw/00082173/?top=rooms",
        notification_rule=RuleLeaf(
            kind=NotificationLeafKind.BELOW_TARGET_PRICE,
            target_price=Decimal("20000"),
        ),
        scheduler_interval_seconds=600,
    )


def _build_latest_snapshot():
    """建立 watch 詳細頁測試用的最新摘要。"""
    from app.domain.entities import LatestCheckSnapshot
    from app.domain.enums import Availability

    return LatestCheckSnapshot(
        watch_item_id="watch-list-1",
        checked_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        availability=Availability.AVAILABLE,
        normalized_price_amount=Decimal("22990"),
        currency="JPY",
        is_degraded=False,
        consecutive_failures=1,
        last_error_code="http_403",
    )


def _build_check_event():
    """建立 watch 詳細頁測試用的檢查事件。"""
    from app.domain.entities import CheckEvent
    from app.domain.enums import Availability, NotificationDeliveryStatus

    return CheckEvent(
        watch_item_id="watch-list-1",
        checked_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        availability=Availability.AVAILABLE,
        event_kinds=("price_drop",),
        normalized_price_amount=Decimal("22990"),
        currency="JPY",
        error_code="http_403",
        notification_status=NotificationDeliveryStatus.SENT,
        sent_channels=("desktop",),
    )


def _build_notification_state():
    """建立 watch 詳細頁測試用的通知狀態。"""
    from app.domain.entities import NotificationState
    from app.domain.enums import Availability

    return NotificationState(
        watch_item_id="watch-list-1",
        last_notified_price=Decimal("22990"),
        last_notified_availability=Availability.AVAILABLE,
        last_notified_at=datetime(2026, 4, 12, 10, 5, tzinfo=timezone.utc),
        consecutive_failures=1,
        consecutive_parse_failures=0,
    )


def _build_debug_artifact():
    """建立 watch 詳細頁測試用的 debug artifact。"""
    from app.domain.entities import DebugArtifact

    return DebugArtifact(
        watch_item_id="watch-list-1",
        captured_at=datetime(2026, 4, 12, 10, 1, tzinfo=timezone.utc),
        reason="parse_failed",
        payload_text="<html>blocked</html>",
        source_url="https://www.ikyu.com/zh-tw/00082173/",
        http_status=403,
    )


def _build_discarded_debug_artifact():
    """建立 watch 詳細頁測試用的 page discarded debug artifact。"""
    from app.domain.entities import DebugArtifact

    return DebugArtifact(
        watch_item_id="watch-list-1",
        captured_at=datetime(2026, 4, 12, 10, 2, tzinfo=timezone.utc),
        reason="page_was_discarded",
        payload_text="<html>discarded</html>",
        source_url="https://www.ikyu.com/zh-tw/00082173/",
        http_status=None,
    )
