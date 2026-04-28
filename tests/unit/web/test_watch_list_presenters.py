"""Dashboard page-level presenter 測試。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.monitor.runtime import MonitorRuntimeStatus
from app.web.watch_list_presenters import (
    build_dashboard_page_view_model,
    build_runtime_status_presentation,
)

from .builders import (
    _build_latest_snapshot,
    _build_price_history_entry,
    _build_watch_item,
)


def test_dashboard_page_view_model_centralizes_summary_and_rows() -> None:
    """Dashboard view model 應集中摘要卡計數、row 排序與 runtime 狀態。"""
    watch_item = _build_watch_item()
    runtime_status = MonitorRuntimeStatus(
        is_running=True,
        enabled_watch_count=3,
        registered_watch_count=3,
        inflight_watch_count=1,
        chrome_debuggable=True,
        last_tick_at=datetime(2026, 4, 12, 10, 10, tzinfo=timezone.utc),
        last_watch_sync_at=datetime(2026, 4, 12, 10, 5, tzinfo=timezone.utc),
    )

    view_model = build_dashboard_page_view_model(
        watch_items=(watch_item,),
        latest_snapshots_by_watch_id={watch_item.id: _build_latest_snapshot()},
        recent_price_history_by_watch_id={
            watch_item.id: (
                _build_price_history_entry(amount=Decimal("20000"), hour=8),
                _build_price_history_entry(amount=Decimal("21000"), hour=9),
            )
        },
        today_notification_count=2,
        runtime_status=runtime_status,
        use_24_hour_time=True,
    )

    assert view_model.summary_cards[0].value == "3"
    assert view_model.summary_cards[1].value == "1"
    assert view_model.summary_cards[2].value == "1"
    assert view_model.summary_cards[3].helper_text == "2 封新通知"
    assert view_model.watch_rows[0].watch_id == watch_item.id
    assert view_model.runtime_status is not None
    assert view_model.runtime_status.items[0].value == "運作正常"


def test_runtime_status_presentation_returns_none_without_runtime() -> None:
    """沒有 background runtime 時，不應讓 renderer 自行推導空狀態。"""
    assert build_runtime_status_presentation(None, use_24_hour_time=True) is None
