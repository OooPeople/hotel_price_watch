"""設定頁 page-level client script entrypoint。"""

from __future__ import annotations

from app.web.client_contracts import SETTINGS_DOM_IDS
from app.web.settings_client_scripts import (
    render_notification_channel_toggle_script,
    render_notification_rule_toggle_script,
    render_time_format_exclusive_script,
)
from app.web.ui_components import unsaved_changes_script


def render_global_settings_page_scripts() -> str:
    """渲染全域設定頁所有 client behavior。"""
    return (
        render_notification_channel_toggle_script(
            checkbox_id=SETTINGS_DOM_IDS.global_ntfy_enabled,
            wrapper_id=SETTINGS_DOM_IDS.global_ntfy_settings,
        )
        + render_notification_channel_toggle_script(
            checkbox_id=SETTINGS_DOM_IDS.global_discord_enabled,
            wrapper_id=SETTINGS_DOM_IDS.global_discord_settings,
        )
        + render_time_format_exclusive_script(
            first_checkbox_id=SETTINGS_DOM_IDS.time_format_12h,
            second_checkbox_id=SETTINGS_DOM_IDS.time_format_24h,
        )
        + unsaved_changes_script(form_id=SETTINGS_DOM_IDS.global_settings_form)
    )


def render_watch_notification_rule_page_scripts() -> str:
    """渲染單一 watch 通知規則頁所有 client behavior。"""
    return render_notification_rule_toggle_script(
        select_id=SETTINGS_DOM_IDS.notification_rule_kind,
        wrapper_id=SETTINGS_DOM_IDS.notification_target_price_wrapper,
    )
