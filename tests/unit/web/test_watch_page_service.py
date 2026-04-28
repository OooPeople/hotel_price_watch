from __future__ import annotations

from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_FRAGMENT_SECTIONS,
    WATCH_DETAIL_PAYLOAD_KEYS,
    WATCH_LIST_PAYLOAD_KEYS,
)
from app.web.watch_fragment_payloads import (
    build_watch_detail_fragment_payload,
    build_watch_list_fragment_payload,
)
from app.web.watch_page_service import WatchPageService

from .helpers import (
    _build_check_event,
    _build_debug_artifact,
    _build_latest_snapshot,
    _build_test_container,
    _build_watch_item,
    _FakeMonitorRuntime,
)


def test_watch_fragment_payload_builder_builds_watch_list_payload(tmp_path) -> None:
    """首頁 fragment payload builder 應用 page context 組出 runtime 摘要。"""
    container = _build_test_container(tmp_path)
    container.watch_item_repository.save(_build_watch_item())
    container.runtime_write_repository.save_latest_check_snapshot(_build_latest_snapshot())
    container.monitor_runtime = _FakeMonitorRuntime()
    service = WatchPageService(container)

    payload = build_watch_list_fragment_payload(
        context=service.build_watch_list_context(),
        version=service.build_watch_list_revision(),
        flash_message="已暫停監視",
    ).to_dict()

    keys = WATCH_LIST_PAYLOAD_KEYS
    assert set(payload) == {
        keys.version,
        keys.flash_html,
        keys.summary_html,
        keys.runtime_html,
        keys.table_body_html,
    }
    assert "已暫停監視" in payload[keys.flash_html]
    assert "啟用中的監視" in payload[keys.summary_html]
    assert "系統狀態" in payload[keys.runtime_html]
    assert "Ocean Hotel" in payload[keys.table_body_html]


def test_watch_fragment_payload_builder_builds_detail_payload(tmp_path) -> None:
    """詳細頁 fragment payload builder 應用 page context 組出 section HTML。"""
    container = _build_test_container(tmp_path)
    watch_item = _build_watch_item()
    container.watch_item_repository.save(watch_item)
    container.runtime_write_repository.save_latest_check_snapshot(_build_latest_snapshot())
    container.runtime_write_repository.append_check_event(_build_check_event())
    container.runtime_write_repository.append_debug_artifact(
        _build_debug_artifact(),
        retention_limit=10,
    )
    service = WatchPageService(container)

    payload = build_watch_detail_fragment_payload(
        context=service.build_watch_detail_context(watch_item),
        version=service.build_watch_detail_revision(watch_item),
    ).to_dict()

    keys = WATCH_DETAIL_PAYLOAD_KEYS
    assert set(payload) == {
        keys.version,
        *(section.payload_key for section in WATCH_DETAIL_FRAGMENT_SECTIONS),
    }
    assert "Ocean Hotel" in payload[keys.hero_section_html]
    assert "目前價格" in payload[keys.price_summary_section_html]
    assert "價格趨勢" in payload[keys.price_trend_section_html]
    assert "檢查歷史" in payload[keys.check_events_section_html]
    assert "診斷檔案" in payload[keys.debug_artifacts_section_html]
