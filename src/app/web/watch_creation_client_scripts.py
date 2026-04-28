"""新增監視流程專用的 client-side script renderer。"""

from __future__ import annotations

from app.domain.enums import NotificationLeafKind
from app.web.ui_behaviors import render_select_visibility_script


def render_notification_rule_toggle_script(*, select_id: str, wrapper_id: str) -> str:
    """渲染新增監視通知條件切換腳本，控制目標價欄位顯示。"""
    return render_select_visibility_script(
        select_id=select_id,
        wrapper_id=wrapper_id,
        hidden_value=NotificationLeafKind.ANY_DROP.value,
    )
