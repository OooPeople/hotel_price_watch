"""設定頁專用的 client-side script renderer。"""

from __future__ import annotations

from app.domain.enums import NotificationLeafKind
from app.web.ui_behaviors import (
    render_checkbox_visibility_script,
    render_exclusive_checkbox_pair_script,
    render_select_visibility_script,
)


def render_notification_rule_toggle_script(*, select_id: str, wrapper_id: str) -> str:
    """渲染單一 watch 通知規則切換腳本，控制目標價欄位顯示。"""
    return render_select_visibility_script(
        select_id=select_id,
        wrapper_id=wrapper_id,
        hidden_value=NotificationLeafKind.ANY_DROP.value,
    )


def render_notification_channel_toggle_script(
    *,
    checkbox_id: str,
    wrapper_id: str,
) -> str:
    """渲染全域通知通道設定區塊顯示 / 隱藏腳本。"""
    return render_checkbox_visibility_script(
        checkbox_id=checkbox_id,
        wrapper_id=wrapper_id,
    )


def render_time_format_exclusive_script(
    *,
    first_checkbox_id: str,
    second_checkbox_id: str,
) -> str:
    """渲染 12 / 24 小時制互斥選擇腳本。"""
    return render_exclusive_checkbox_pair_script(
        first_checkbox_id=first_checkbox_id,
        second_checkbox_id=second_checkbox_id,
    )
