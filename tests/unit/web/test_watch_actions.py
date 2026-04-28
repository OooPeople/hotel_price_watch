from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.watch_lifecycle import WatchLifecycleCoordinator
from app.domain.entities import LatestCheckSnapshot
from app.domain.enums import Availability, RuntimeStateEventKind, WatchRuntimeState
from app.main import create_app

from .helpers import (
    _build_test_container,
    _build_watch_item,
    _FakeMonitorRuntime,
    _local_request_headers,
)


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


def test_post_watch_pause_from_watch_list_returns_fragments(tmp_path) -> None:
    """首頁列表 quick action 應回傳 fragments，而不是 redirect 到詳細頁。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    client = TestClient(create_app(container))
    headers = {
        **_local_request_headers(),
        "X-Requested-With": "fetch",
        "Accept": "application/json",
    }

    response = client.post(
        "/watches/watch-list-1/pause",
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "location" not in response.headers
    payload = response.json()
    assert "已暫停監視" in payload["flash_html"]
    assert "恢復" in payload["table_body_html"]
    assert "Ocean Hotel" in payload["table_body_html"]
    paused_watch = container.watch_item_repository.get("watch-list-1")
    assert paused_watch is not None
    assert paused_watch.paused_reason == "manually_paused"


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
