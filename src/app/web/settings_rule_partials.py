"""單一 watch 通知規則設定 partial renderer。"""

from __future__ import annotations

from app.domain.enums import NotificationLeafKind
from app.web.client_contracts import SETTINGS_DOM_IDS
from app.web.settings_page_scripts import render_watch_notification_rule_page_scripts
from app.web.ui_components import submit_button
from app.web.ui_page_sections import field_stack_style
from app.web.ui_styles import input_style, meta_paragraph_style


def render_watch_notification_rule_form_body(
    *,
    selected_kind: NotificationLeafKind,
    target_price_value: str,
) -> str:
    """渲染單一 watch 通知規則設定表單內容。"""
    target_price_wrapper_style = _notification_target_price_wrapper_style(selected_kind)
    return f"""
    <label>通知條件</label>
    <select
      id="{SETTINGS_DOM_IDS.notification_rule_kind}"
      name="notification_rule_kind"
      style="{input_style()}"
    >
      <option
        value="{NotificationLeafKind.ANY_DROP.value}"
        {"selected" if selected_kind == NotificationLeafKind.ANY_DROP else ""}
      >
        價格下降
      </option>
      <option
        value="{NotificationLeafKind.BELOW_TARGET_PRICE.value}"
        {"selected" if selected_kind == NotificationLeafKind.BELOW_TARGET_PRICE else ""}
      >
        低於目標價
      </option>
    </select>
    <div
      id="{SETTINGS_DOM_IDS.notification_target_price_wrapper}"
      style="{target_price_wrapper_style}"
    >
      <label>目標價（僅低於目標價時使用）</label>
      <input
        type="text"
        name="target_price"
        value="{target_price_value}"
        placeholder="例如 20000"
        style="{input_style()}"
      >
      {_render_notification_target_price_hint(selected_kind)}
    </div>
    {submit_button(label="儲存通知設定", kind="primary")}
    """


def render_watch_notification_rule_scripts() -> str:
    """相容舊入口，委派到單一 watch 設定頁 script entrypoint。"""
    return render_watch_notification_rule_page_scripts()


def _render_notification_target_price_hint(kind: NotificationLeafKind) -> str:
    """依目前選定的通知規則顯示目標價欄位提示。"""
    if kind is NotificationLeafKind.ANY_DROP:
        return (
            f'<p style="{meta_paragraph_style()}">'
            "目前為「價格下降」，目標價欄位會被忽略。"
            "</p>"
        )
    return (
        f'<p style="{meta_paragraph_style()}">'
        "只有當價格低於此門檻時才會通知。"
        "</p>"
    )


def _notification_target_price_wrapper_style(kind: NotificationLeafKind) -> str:
    """依通知規則回傳目標價欄位容器的顯示樣式。"""
    return field_stack_style(visible=kind is not NotificationLeafKind.ANY_DROP)
