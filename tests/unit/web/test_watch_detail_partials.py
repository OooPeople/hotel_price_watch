from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.web.watch_detail_history_partials import (
    render_check_events_section_with_time_format,
    render_debug_artifacts_section_with_time_format,
)
from app.web.watch_detail_presenters import (
    build_watch_detail_page_view_model,
    build_watch_detail_presentation,
)
from app.web.watch_detail_summary_partials import (
    render_watch_detail_hero_section,
    render_watch_price_summary_cards,
)
from app.web.watch_detail_trend_partials import render_price_trend_section_with_time_format

from .helpers import (
    _build_check_event,
    _build_debug_artifact,
    _build_latest_snapshot,
    _build_notification_state,
    _build_watch_item,
)


def test_watch_detail_summary_partials_render_hero_and_cards() -> None:
    """詳情摘要 partial 應集中 hero 與價格摘要卡片輸出。"""
    presentation = build_watch_detail_presentation(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        notification_state=_build_notification_state(),
    )

    hero_html = render_watch_detail_hero_section(
        presentation=presentation,
        use_24_hour_time=False,
    )
    cards_html = render_watch_price_summary_cards(
        presentation=presentation,
        use_24_hour_time=False,
    )

    assert "Ocean Hotel" in hero_html
    assert "Standard Twin" in hero_html
    assert "目前價格" in cards_html
    assert "最近通知" in cards_html


def test_watch_detail_trend_partial_renders_chart_for_priced_events() -> None:
    """價格趨勢 partial 應集中 SVG 趨勢圖輸出。"""
    first_event = replace(
        _build_check_event(),
        checked_at=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        normalized_price_amount=Decimal("24000"),
    )
    second_event = replace(
        _build_check_event(),
        checked_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        normalized_price_amount=Decimal("22990"),
    )

    html = render_price_trend_section_with_time_format(
        (first_event, second_event),
        use_24_hour_time=True,
    )

    assert "價格趨勢圖" in html
    assert "下降 JPY 1010" in html
    assert "<polyline" in html


def test_watch_detail_history_partials_render_events_and_debug() -> None:
    """歷史 partial 應集中檢查歷史與診斷檔案輸出。"""
    events_html = render_check_events_section_with_time_format(
        (_build_check_event(),),
        use_24_hour_time=True,
    )
    debug_html = render_debug_artifacts_section_with_time_format(
        (_build_debug_artifact(),),
        use_24_hour_time=True,
    )

    assert "檢查歷史" in events_html
    assert "通知結果" in events_html
    assert "診斷檔案" in debug_html
    assert "站方阻擋" in debug_html


def test_watch_detail_page_view_model_centralizes_runtime_rows() -> None:
    """詳情頁 view model 應集中趨勢、歷史與診斷列的顯示語意。"""
    previous_event = replace(
        _build_check_event(),
        checked_at=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        normalized_price_amount=Decimal("24000"),
    )

    view_model = build_watch_detail_page_view_model(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        check_events=(previous_event, _build_check_event()),
        notification_state=_build_notification_state(),
        debug_artifacts=(_build_debug_artifact(),),
        runtime_state_events=(),
        use_24_hour_time=True,
    )

    assert view_model.summary.hotel_name == "Ocean Hotel"
    assert view_model.price_trend.delta_text == "下降 JPY 1010"
    assert view_model.check_event_rows[0].notification_badge.label == "已通知"
    assert view_model.debug_artifact_rows[0].reason_text == "解析失敗"
