from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.application.debug_captures import (
    DebugCaptureClearResult,
    clear_debug_captures,
    list_debug_captures,
    load_debug_capture,
    load_latest_debug_capture,
)
from app.main import create_app
from app.web.debug_presenters import (
    build_debug_capture_detail_presentation,
    build_debug_capture_list_presentation,
)
from app.web.routes import debug_routes as debug_routes_module
from app.web.views import (
    render_debug_capture_detail_page,
    render_debug_capture_list_page,
)

from .helpers import (
    _build_test_container,
    _local_request_headers,
    _write_debug_capture,
)


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
    assert "這裡只列出建立監視 / preview 流程保存的 capture" in list_html
    assert "成功解析出 1 筆候選房型方案。" in detail_html
    assert "這裡只顯示 preview capture" in detail_html
    assert "Metadata JSON" in detail_html
    assert "清空紀錄" in list_html


def test_debug_capture_presenters_centralize_list_and_detail_state(tmp_path) -> None:
    """debug capture presenter 應集中列表摘要與詳情診斷列。"""
    capture = _write_debug_capture(tmp_path)
    loaded_capture = load_debug_capture(capture["capture_id"], tmp_path / "debug")
    assert loaded_capture is not None

    list_presentation = build_debug_capture_list_presentation(
        captures=(loaded_capture.summary,),
        flash_message="已清空",
        use_24_hour_time=True,
    )
    detail_presentation = build_debug_capture_detail_presentation(
        capture=loaded_capture,
        use_24_hour_time=True,
    )

    assert list_presentation.total_count == 1
    assert list_presentation.candidate_total == 1
    assert list_presentation.rows[0].latest_status_badge.label == "success"
    assert detail_presentation.latest_status_badge.kind == "success"
    assert detail_presentation.diagnostic_rows[0].detail_text == "成功解析出 1 筆候選房型方案。"


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
