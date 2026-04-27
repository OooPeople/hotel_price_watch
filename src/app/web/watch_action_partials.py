"""watch 操作按鈕 partial renderer。"""

from __future__ import annotations

from html import escape

from app.domain.entities import WatchItem
from app.domain.enums import WatchRuntimeState
from app.web.ui_components import action_row, submit_button
from app.web.ui_presenters import (
    WatchActionPresentation,
    WatchActionSurface,
    build_watch_action_presentations,
)


def render_watch_action_controls(
    *,
    watch_item: WatchItem,
    runtime_state: WatchRuntimeState,
    surface: WatchActionSurface,
) -> str:
    """依頁面情境渲染 watch 操作按鈕。"""
    actions = build_watch_action_presentations(
        runtime_state=runtime_state,
        surface=surface,
    )
    return action_row(
        body="".join(
            _render_watch_action_form(watch_item_id=watch_item.id, action=action)
            for action in actions
        ),
        extra_style="flex-wrap:nowrap;",
    )


def _render_watch_action_form(
    *,
    watch_item_id: str,
    action: WatchActionPresentation,
) -> str:
    """渲染單一 watch 操作按鈕表單。"""
    confirm_attr = (
        f' onsubmit="return confirm(\'{escape(action.confirm_message)}\')"'
        if action.confirm_message is not None
        else ""
    )
    quick_action_attr = (
        ' data-watch-list-action="true"' if action.submit_mode == "fetch" else ""
    )
    return f"""
    <form
      action="/watches/{escape(watch_item_id)}/{escape(action.action)}"
      method="post"
      style="margin:0;"
      {confirm_attr}
      {quick_action_attr}
    >
      {submit_button(label=action.label, kind=action.button_kind)}
    </form>
    """

