from __future__ import annotations

from app.web.client_contracts import SETTINGS_DOM_IDS, WATCH_CREATION_DOM_IDS
from app.web.settings_client_scripts import (
    render_notification_channel_toggle_script,
    render_time_format_exclusive_script,
)
from app.web.settings_client_scripts import (
    render_notification_rule_toggle_script as render_settings_rule_toggle_script,
)
from app.web.ui_behaviors import (
    render_app_shell_script,
    render_unsaved_changes_script,
)
from app.web.watch_creation_client_scripts import (
    render_notification_rule_toggle_script as render_create_rule_toggle_script,
)


def test_ui_behavior_scripts_use_safe_json_constants() -> None:
    """共用 behavior script 應集中注入 DOM id，避免 page partial 手刻腳本。"""
    html = render_unsaved_changes_script(
        form_id='settings"form',
        indicator_id="unsaved-indicator",
    )

    assert 'document.getElementById("settings\\"form")' in html
    assert 'document.getElementById("unsaved-indicator")' in html
    assert "beforeunload" in html


def test_app_shell_script_still_exposes_sidebar_behavior() -> None:
    """AppShell 收合行為應由集中 behavior renderer 輸出。"""
    html = render_app_shell_script()

    assert "hotelPriceWatch.sidebarCollapsed" in html
    assert "sidebar-collapsed" in html
    assert "aria-expanded" in html


def test_settings_client_scripts_wrap_shared_behaviors() -> None:
    """設定頁 script wrapper 應保留通知條件、通道與時間格式行為。"""
    rule_html = render_settings_rule_toggle_script(
        select_id=SETTINGS_DOM_IDS.notification_rule_kind,
        wrapper_id=SETTINGS_DOM_IDS.notification_target_price_wrapper,
    )
    channel_html = render_notification_channel_toggle_script(
        checkbox_id=SETTINGS_DOM_IDS.global_ntfy_enabled,
        wrapper_id=SETTINGS_DOM_IDS.global_ntfy_settings,
    )
    time_html = render_time_format_exclusive_script(
        first_checkbox_id=SETTINGS_DOM_IDS.time_format_12h,
        second_checkbox_id=SETTINGS_DOM_IDS.time_format_24h,
    )

    assert '"any_drop"' in rule_html
    assert SETTINGS_DOM_IDS.notification_target_price_wrapper in rule_html
    assert SETTINGS_DOM_IDS.global_ntfy_settings in channel_html
    assert "checkbox.checked" in channel_html
    assert SETTINGS_DOM_IDS.time_format_12h in time_html
    assert SETTINGS_DOM_IDS.time_format_24h in time_html


def test_watch_creation_client_script_wraps_notification_rule_behavior() -> None:
    """新增監視頁應使用專用 wrapper 輸出通知條件切換腳本。"""
    html = render_create_rule_toggle_script(
        select_id=WATCH_CREATION_DOM_IDS.notification_rule_kind,
        wrapper_id=WATCH_CREATION_DOM_IDS.notification_target_price_wrapper,
    )

    assert WATCH_CREATION_DOM_IDS.notification_rule_kind in html
    assert WATCH_CREATION_DOM_IDS.notification_target_price_wrapper in html
    assert '"any_drop"' in html
