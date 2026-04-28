from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.enums import WatchRuntimeState
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_presenters import (
    WatchActionSurface,
    build_watch_action_presentations,
)
from app.web.views import (
    render_watch_list_page,
)
from app.web.watch_fragment_contracts import (
    WATCH_LIST_DOM_IDS,
)

from .helpers import (
    _build_latest_snapshot,
    _build_price_history_entry,
    _build_watch_item,
)


def test_render_watch_list_page_shows_existing_watch_items() -> None:
    """驗證 watch 列表頁會顯示既有 watch item 與 runtime 摘要。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        latest_snapshots_by_watch_id={"watch-list-1": _build_latest_snapshot()},
        runtime_status=MonitorRuntimeStatus(
            is_running=True,
            enabled_watch_count=1,
            registered_watch_count=1,
            inflight_watch_count=0,
            chrome_debuggable=True,
            last_tick_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
            last_watch_sync_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
        ),
        flash_message="已建立監視",
    )

    assert "Ocean Hotel" in html
    assert "Standard Twin" in html
    assert "JPY 22990" in html
    assert "最後檢查" in html
    assert "價格下降時" in html
    assert "更多" not in html
    assert "已建立監視" in html
    assert "刪除" in html
    assert "暫停" in html
    assert 'action="/watches/watch-list-1/pause"' in html
    assert 'action="/watches/watch-list-1/delete"' in html
    assert re.search(
        r'<form[^>]+action="/watches/watch-list-1/pause"[^>]+data-watch-list-action="true"',
        html,
        re.S,
    )
    assert re.search(
        r'<form[^>]+action="/watches/watch-list-1/delete"[^>]+data-watch-list-action="true"',
        html,
        re.S,
    )
    assert "停用" not in html
    assert "/watches/watch-list-1" in html
    assert "/settings" in html
    assert "我的價格監視" in html
    assert "系統狀態" in html
    assert 'id="dashboard-summary-section"' in html
    assert 'data-watch-list-view="cards"' in html
    assert 'data-watch-list-view="list"' in html
    assert 'data-watch-view-mode-button="cards"' in html
    assert "房間資訊" in html
    assert "Standard Twin" in html
    assert "2 人 / 1 房" in html
    assert "9/18 - 9/19，1 晚" in html
    assert "9/18 - 9/19" in html
    assert "1 晚" in html
    assert "white-space:nowrap" in html


def test_watch_action_presentations_separate_list_and_detail_surfaces() -> None:
    """watch action model 應集中定義首頁 quick action 與詳細頁表單差異。"""
    list_actions = build_watch_action_presentations(
        runtime_state=WatchRuntimeState.ACTIVE,
        surface=WatchActionSurface.LIST,
    )
    detail_actions = build_watch_action_presentations(
        runtime_state=WatchRuntimeState.ACTIVE,
        surface=WatchActionSurface.DETAIL,
    )

    assert [action.action for action in list_actions] == ["pause", "delete"]
    assert {action.submit_mode for action in list_actions} == {"fetch"}
    assert [action.action for action in detail_actions] == [
        "check-now",
        "pause",
        "delete",
    ]
    assert {action.submit_mode for action in detail_actions} == {"form"}
    assert list_actions[-1].confirm_message is not None


def test_render_watch_list_page_shows_reference_style_summary_cards() -> None:
    """首頁摘要卡應顯示參考圖方向的四個產品指標。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        latest_snapshots_by_watch_id={"watch-list-1": _build_latest_snapshot()},
        today_notification_count=2,
    )

    assert "啟用中的監視" in html
    assert "需要注意" in html
    assert "最近有變動" in html
    assert "今日通知" in html
    assert "2 封新通知" in html


def test_render_watch_list_page_uses_24_hour_price_change_window() -> None:
    """首頁清單與摘要應以 24 小時價格歷史呈現變動。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        latest_snapshots_by_watch_id={"watch-list-1": _build_latest_snapshot()},
        recent_price_history_by_watch_id={
            "watch-list-1": (
                _build_price_history_entry(amount=Decimal("25000"), hour=8),
                _build_price_history_entry(amount=Decimal("22990"), hour=10),
            )
        },
    )

    assert "▼ JPY 2010" in html
    assert "過去 24 小時" in html
    assert "最近有變動" in html


def test_render_watch_list_page_explains_backoff_retry_time() -> None:
    """退避中狀態應顯示分鐘層級的自動重試提示。"""
    latest_snapshot = replace(
        _build_latest_snapshot(),
        backoff_until=datetime.now(timezone.utc) + timedelta(minutes=8),
        last_error_code="target_missing",
    )

    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        latest_snapshots_by_watch_id={"watch-list-1": latest_snapshot},
    )

    assert "退避中" in html
    assert "預計 8 分鐘後自動重試" in html
    assert "data-countdown-time" in html

def test_render_watch_list_page_shows_debug_link() -> None:
    """列表頁應提供進入 debug captures 的入口。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        flash_message=None,
    )

    assert "/debug/captures" in html
    assert "進階診斷" in html


def test_render_watch_list_page_includes_app_shell_navigation() -> None:
    """列表頁應透過 AppShell 顯示主要導覽，避免各頁導覽分歧。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        flash_message=None,
    )

    assert 'class="app-shell"' in html
    assert 'id="sidebar-toggle"' in html
    assert 'class="sidebar-toggle"' in html
    assert "data-sidebar-expanded-icon" in html
    assert "data-sidebar-collapsed-icon" in html
    assert "position:fixed;left:0;top:0;bottom:0" in html
    assert "--sidebar-width: 248px" in html
    assert "padding-left:var(--sidebar-width)" in html
    assert "transition: padding-left 220ms ease" in html
    assert "width 220ms ease" in html
    assert "left 220ms ease" in html
    assert "prefers-reduced-motion: reduce" in html
    assert "--sidebar-width: 40px" in html
    assert "var(--sidebar-width)" in html
    assert "right: 5px" in html
    assert "收合選單" not in html
    assert "hotelPriceWatch.sidebarCollapsed" in html
    assert "Hotel Price Watch" in html
    assert "IKYU 價格監視" in html
    assert "總覽" in html
    assert "通知設定" in html
    assert "狀態見系統狀態" not in html
    assert "user@example.com" not in html
    assert "/watches/new" in html
    assert "/settings" in html
    assert "/debug/captures" in html


def test_render_watch_list_page_includes_polling_script() -> None:
    """首頁應帶局部更新 polling script，而不是依賴整頁刷新。"""
    html = render_watch_list_page(
        watch_items=(_build_watch_item(),),
        latest_snapshots_by_watch_id={"watch-list-1": _build_latest_snapshot()},
        initial_fragment_version="version-1",
    )

    assert "/fragments/watch-list" in html
    assert "/fragments/watch-list/version" in html
    assert WATCH_LIST_DOM_IDS.summary in html
    assert WATCH_LIST_DOM_IDS.flash in html
    assert WATCH_LIST_DOM_IDS.watch_list in html
    assert WATCH_LIST_DOM_IDS.runtime in html
    assert "payload[payloadKeys.summaryHtml]" in html
    assert "payload[payloadKeys.flashHtml]" in html
    assert "payload[payloadKeys.runtimeHtml]" in html
    assert "payload[payloadKeys.tableBodyHtml]" in html
    assert "data-watch-list-action" in html
    assert "data-relative-time" in html
    assert "form.action" in html
    assert "currentVersion = \"version-1\"" in html
    assert "setInterval(checkVersion, 1000)" in html
    assert "setInterval(updateClientTimeText, 30000)" in html
    assert "setInterval(refresh, 15000)" not in html


def test_render_watch_list_page_docks_runtime_status_with_collapse_control() -> None:
    """首頁系統狀態應吸附在底部，並提供可持久化的收合控制。"""
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
    )

    assert 'class="runtime-status-dock"' in html
    assert "position: fixed" in html
    assert "bottom: 18px" in html
    assert "data-runtime-status-toggle" in html
    assert "data-runtime-expanded-icon" in html
    assert "data-runtime-collapsed-icon" in html
    assert "hotelPriceWatch.runtimeStatusCollapsed" in html
    assert "applyRuntimeDockState();" in html
