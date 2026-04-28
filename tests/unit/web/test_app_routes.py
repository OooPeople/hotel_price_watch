from __future__ import annotations

from fastapi.testclient import TestClient

from app.bootstrap.container import build_app_container
from app.main import create_app
from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_FRAGMENT_SECTIONS,
    WATCH_DETAIL_PAYLOAD_KEYS,
    WATCH_LIST_PAYLOAD_KEYS,
)

from .helpers import (
    _build_check_event,
    _build_debug_artifact,
    _build_latest_snapshot,
    _build_notification_state,
    _build_test_container,
    _build_watch_item,
    _FakeMonitorRuntime,
)


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
    assert "/fragments/watch-list/version" in paths
    assert "/watches/{watch_item_id}/fragments/version" in paths
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


def test_create_app_can_disable_monitor_runtime_auto_start(tmp_path) -> None:
    """安全測試模式應保留 runtime 狀態讀取，但不自動啟動背景監看。"""
    container = _build_test_container(tmp_path)
    fake_runtime = _FakeMonitorRuntime()
    container.monitor_runtime = fake_runtime
    container.monitor_runtime_auto_start_enabled = False

    with TestClient(create_app(container)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["runtime_auto_start_enabled"] is False
    assert payload["runtime"]["is_running"] is False
    assert payload["runtime"]["chrome_debuggable"] is True
    assert fake_runtime.started == 0
    assert fake_runtime.stopped == 0


def test_build_app_container_reads_runtime_enabled_env(tmp_path, monkeypatch) -> None:
    """容器應可透過環境變數關閉背景 runtime 自動啟動。"""
    monkeypatch.setenv("HOTEL_PRICE_WATCH_RUNTIME_ENABLED", "0")

    container = build_app_container(tmp_path / "watcher.db")

    assert container.monitor_runtime is not None
    assert container.monitor_runtime_auto_start_enabled is False


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
    keys = WATCH_LIST_PAYLOAD_KEYS
    assert set(payload) == {
        keys.version,
        keys.flash_html,
        keys.summary_html,
        keys.runtime_html,
        keys.table_body_html,
    }
    assert payload[keys.version]
    assert "啟用中的監視" in payload[keys.summary_html]
    assert "系統狀態" in payload[keys.runtime_html]
    assert "Ocean Hotel" in payload[keys.table_body_html]


def test_watch_list_fragment_version_changes_after_runtime_update(tmp_path) -> None:
    """首頁版本 endpoint 應在可見 runtime 資料改變後變更。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())

    with TestClient(create_app(container)) as client:
        before = client.get("/fragments/watch-list/version").json()["version"]
        container.runtime_write_repository.save_latest_check_snapshot(
            _build_latest_snapshot()
        )
        after = client.get("/fragments/watch-list/version").json()["version"]

    assert before != after


def test_watch_detail_fragments_endpoint_returns_partial_sections(tmp_path) -> None:
    """watch 詳細頁 fragments endpoint 應回傳三個主要局部區塊。"""
    container = _build_test_container(tmp_path)
    watch_item = _build_watch_item()
    container.watch_item_repository.save(watch_item)
    container.runtime_write_repository.save_latest_check_snapshot(_build_latest_snapshot())
    container.runtime_write_repository.append_check_event(_build_check_event())
    container.runtime_write_repository.save_notification_state(_build_notification_state())
    container.runtime_write_repository.append_debug_artifact(
        _build_debug_artifact(),
        retention_limit=10,
    )

    with TestClient(create_app(container)) as client:
        response = client.get(f"/watches/{watch_item.id}/fragments")

    assert response.status_code == 200
    payload = response.json()
    keys = WATCH_DETAIL_PAYLOAD_KEYS
    assert set(payload) == {
        keys.version,
        *(section.payload_key for section in WATCH_DETAIL_FRAGMENT_SECTIONS),
    }
    assert payload[keys.version]
    assert "latest_section_html" not in payload
    assert "Ocean Hotel" in payload[keys.hero_section_html]
    assert "目前價格" in payload[keys.price_summary_section_html]
    assert "價格趨勢" in payload[keys.price_trend_section_html]
    assert "檢查歷史" in payload[keys.check_events_section_html]
    assert "診斷檔案" in payload[keys.debug_artifacts_section_html]


def test_watch_detail_fragment_version_changes_after_debug_artifact(tmp_path) -> None:
    """詳細頁版本 endpoint 應在可見診斷資料改變後變更。"""
    container = _build_test_container(tmp_path)
    watch_item = _build_watch_item()
    container.watch_item_repository.save(watch_item)

    with TestClient(create_app(container)) as client:
        before = client.get(f"/watches/{watch_item.id}/fragments/version").json()[
            "version"
        ]
        container.runtime_write_repository.append_debug_artifact(
            _build_debug_artifact(),
            retention_limit=10,
        )
        after = client.get(f"/watches/{watch_item.id}/fragments/version").json()[
            "version"
        ]

    assert before != after
