"""前端 behavior 與 server-rendered HTML 共用的 DOM contract。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SettingsDomIds:
    """設定頁 client behavior 會使用的 DOM id。"""

    notification_rule_kind: str
    notification_target_price_wrapper: str
    global_settings_form: str
    global_ntfy_enabled: str
    global_ntfy_settings: str
    global_discord_enabled: str
    global_discord_settings: str
    time_format_12h: str
    time_format_24h: str


@dataclass(frozen=True, slots=True)
class WatchCreationDomIds:
    """新增監視流程 client behavior 會使用的 DOM id。"""

    notification_rule_kind: str
    notification_target_price_wrapper: str


SETTINGS_DOM_IDS = SettingsDomIds(
    notification_rule_kind="notification-rule-kind",
    notification_target_price_wrapper="notification-target-price-wrapper",
    global_settings_form="global-settings-form",
    global_ntfy_enabled="global-ntfy-enabled",
    global_ntfy_settings="global-ntfy-settings",
    global_discord_enabled="global-discord-enabled",
    global_discord_settings="global-discord-settings",
    time_format_12h="time-format-12h",
    time_format_24h="time-format-24h",
)
"""設定頁 DOM id contract。"""


WATCH_CREATION_DOM_IDS = WatchCreationDomIds(
    notification_rule_kind="create-watch-notification-rule-kind",
    notification_target_price_wrapper="create-watch-target-price-wrapper",
)
"""新增監視流程 DOM id contract。"""
