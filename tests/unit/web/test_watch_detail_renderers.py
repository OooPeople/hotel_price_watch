from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.web.views import (
    render_watch_detail_page,
)
from app.web.watch_detail_presenters import build_watch_detail_presentation
from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_DOM_IDS,
)

from .helpers import (
    _build_check_event,
    _build_debug_artifact,
    _build_discarded_debug_artifact,
    _build_latest_snapshot,
    _build_notification_state,
    _build_watch_item,
    _build_watch_item_with_below_target_rule,
)


def test_render_watch_detail_page_shows_runtime_sections() -> None:
    """watch 詳細頁應顯示歷史與 debug artifact 區塊。"""
    previous_event = replace(
        _build_check_event(),
        checked_at=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        normalized_price_amount=Decimal("24000"),
    )
    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        check_events=(previous_event, _build_check_event()),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(
            _build_debug_artifact(),
            _build_discarded_debug_artifact(),
        ),
        flash_message="已觸發 立即檢查",
    )

    assert "最近摘要" not in html
    assert "監視詳情" in html
    assert "目前價格" in html
    assert "價格趨勢" in html
    assert "價格趨勢圖" in html
    assert "text-anchor=\"end\"" in html
    assert "· JPY 24000</title>" in html
    assert "下降 JPY 1010" in html
    assert "Room Only" not in html
    assert "通知條件" in html
    assert "連續失敗次數" not in html
    assert "目前是否 degraded" not in html
    assert "最近通知價格" not in html
    assert "display:block;white-space:nowrap;" in html
    assert "進階診斷" in html
    assert "檢查歷史" in html
    assert "診斷檔案" in html
    assert "背景監視期間保存的診斷紀錄" in html
    assert "進階診斷查看" in html
    assert "站方阻擋" in html
    assert "分頁被瀏覽器暫停" in html
    assert "通知設定" in html
    assert "最近 runtime 訊號" not in html
    assert "Debug Artifacts" not in html
    assert "background runtime" not in html
    assert "blocked page" not in html
    assert "tab discard" not in html
    assert "立即檢查" in html
    assert "已觸發 立即檢查" in html
    assert 'action="/watches/watch-list-1/pause"' in html
    assert not re.search(
        r'<form[^>]+action="/watches/watch-list-1/pause"[^>]+data-watch-list-action="true"',
        html,
        re.S,
    )


def test_render_watch_detail_page_uses_single_axis_label_for_flat_price_trend() -> None:
    """價格都相同時，趨勢圖 Y 軸只應顯示單一價格標籤。"""
    first_event = replace(
        _build_check_event(),
        checked_at=datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc),
        normalized_price_amount=Decimal("18434"),
    )
    second_event = replace(
        _build_check_event(),
        checked_at=datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
        normalized_price_amount=Decimal("18434"),
    )

    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=replace(
            _build_latest_snapshot(),
            normalized_price_amount=Decimal("18434"),
        ),
        check_events=(first_event, second_event),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(),
    )

    assert html.count(">JPY 18434</text>") == 1
    assert "價格：JPY 18434" in html
    assert "區間：JPY 18434 - JPY 18434" not in html


def test_watch_detail_presentation_centralizes_summary_values() -> None:
    """詳情頁 presenter 應集中 hero、價格摘要與通知摘要所需資料。"""
    presentation = build_watch_detail_presentation(
        watch_item=_build_watch_item_with_below_target_rule(),
        latest_snapshot=_build_latest_snapshot(),
        notification_state=_build_notification_state(),
    )

    assert presentation.hotel_name == "Ocean Hotel"
    assert presentation.room_name == "Standard Twin"
    assert presentation.date_range_text == "2026-09-18 - 2026-09-19"
    assert presentation.occupancy_text == "2 人 / 1 房"
    assert presentation.current_price_text == "JPY 22990"
    assert presentation.availability_text == "有空房"
    assert presentation.notification_rule_text == "低於目標價 20000 時通知"
    assert presentation.last_checked_at == _build_latest_snapshot().checked_at
    assert presentation.last_notified_at == _build_notification_state().last_notified_at


def test_render_watch_detail_page_shows_check_now_during_backoff() -> None:
    """退避中仍應顯示立即檢查，讓使用者排除狀況後可手動更新。"""
    latest_snapshot = replace(
        _build_latest_snapshot(),
        backoff_until=datetime.now(timezone.utc) + timedelta(hours=1),
        last_error_code="target_missing",
    )

    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=latest_snapshot,
        check_events=(_build_check_event(),),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(),
    )

    assert "退避中" in html
    assert "立即檢查" in html
    assert "暫停" in html


def test_render_watch_detail_page_includes_polling_script() -> None:
    """watch 詳細頁應帶局部更新 polling script，而不是依賴整頁刷新。"""
    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        check_events=(_build_check_event(),),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(_build_debug_artifact(),),
        initial_fragment_version="detail-version-1",
    )

    assert "/watches/watch-list-1/fragments" in html
    assert "/watches/watch-list-1/fragments/version" in html
    assert WATCH_DETAIL_DOM_IDS.hero in html
    assert WATCH_DETAIL_DOM_IDS.price_summary in html
    assert WATCH_DETAIL_DOM_IDS.price_trend in html
    assert WATCH_DETAIL_DOM_IDS.check_events in html
    assert WATCH_DETAIL_DOM_IDS.debug_artifacts in html
    assert "payload[payloadKeys.heroHtml]" in html
    assert "payload[payloadKeys.priceSummaryHtml]" in html
    assert "payload[payloadKeys.priceTrendHtml]" in html
    assert "payload[payloadKeys.checkEventsHtml]" in html
    assert "payload[payloadKeys.debugArtifactsHtml]" in html
    assert "currentVersion = \"detail-version-1\"" in html
    assert "setInterval(checkVersion, 1000)" in html
    assert "setInterval(updateClientTimeText, 30000)" in html
    assert "setInterval(refresh, 10000)" not in html


def test_page_layout_includes_responsive_layout_rules() -> None:
    """頁面框架應包含窄版 layout 與表格捲動規則，避免手機寬度溢出。"""
    html = render_watch_detail_page(
        watch_item=_build_watch_item(),
        latest_snapshot=_build_latest_snapshot(),
        check_events=(_build_check_event(),),
        notification_state=_build_notification_state(),
        runtime_state_events=(),
        debug_artifacts=(_build_debug_artifact(),),
    )

    assert '@media (max-width: 640px)' in html
    assert 'class="page-header"' in html
    assert 'class="table-scroll"' in html
    assert 'class="watch-detail-hero"' in html
    assert 'class="action-row"' in html
