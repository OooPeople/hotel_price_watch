"""watch creation Chrome 分頁選擇 partial renderer。"""

from __future__ import annotations

from html import escape

from app.infrastructure.browser import ChromeTabSummary
from app.web.ui_components import (
    card,
    empty_state_card,
    link_button,
    status_badge,
    submit_button,
)
from app.web.ui_page_sections import cluster_style, stack_block_style, zero_margin_style
from app.web.ui_styles import (
    card_title_style,
    color_token,
    meta_paragraph_style,
)


def render_chrome_tab_cards(
    *,
    tabs: tuple[ChromeTabSummary, ...],
    selected_tab_id: str | None,
    existing_watch_ids_by_tab_id: dict[str, str],
    site_labels_by_tab_id: dict[str, str],
    site_label_list: str,
    site_hint_list: str,
) -> str:
    """渲染 Chrome 分頁選擇頁中的分頁卡片清單。"""
    rows = []
    for tab in tabs:
        rows.append(
            _render_chrome_tab_card(
                tab=tab,
                selected_tab_id=selected_tab_id,
                existing_watch_ids_by_tab_id=existing_watch_ids_by_tab_id,
                site_labels_by_tab_id=site_labels_by_tab_id,
            )
        )

    return "".join(rows) or empty_state_card(
        title=f"目前找不到可用的 {site_label_list} Chrome 分頁",
        message=(
            f"請在目前的專用 Chrome 中打開 {site_hint_list} 頁面，"
            "確認頁面完整載入後再回來重新整理。"
        ),
    )


def _render_chrome_tab_card(
    *,
    tab: ChromeTabSummary,
    selected_tab_id: str | None,
    existing_watch_ids_by_tab_id: dict[str, str],
    site_labels_by_tab_id: dict[str, str],
) -> str:
    """渲染單一 Chrome 分頁卡片與抓取操作。"""
    row_style = ""
    if tab.tab_id == selected_tab_id:
        row_style += f"border-color:{color_token('primary')};"
    throttling_text = "可能節流" if tab.possible_throttling else "正常"
    discarded_text = "；曾被丟棄" if tab.was_discarded else ""
    linked_watch_id = existing_watch_ids_by_tab_id.get(tab.tab_id)
    site_label = site_labels_by_tab_id.get(tab.tab_id)
    site_label_html = (
        f'<p style="{zero_margin_style()}">站點：{escape(site_label)}</p>'
        if site_label is not None
        else ""
    )
    action_html = (
        f"""
        <div style="{cluster_style()}">
          {status_badge(label="已建立監視", kind="warning")}
          {link_button(
              href=f"/watches/{linked_watch_id}",
              label="查看既有監視",
              size="sm",
          )}
        </div>
        """
        if linked_watch_id is not None
        else (
            f'<div style="{cluster_style()}">'
            f'{submit_button(label="抓取此分頁", kind="primary", size="sm")}'
            "</div>"
        )
    )
    status_kind = "warning" if linked_watch_id is not None else "success"
    status_label = "已建立監視" if linked_watch_id is not None else "可抓取"
    return card(
        extra_style=row_style,
        body=f"""
        <form
          action="/watches/chrome-tabs/preview"
          method="post"
          class="chrome-tab-card"
          style="
            display:grid;grid-template-columns:minmax(0,1fr) auto;
            gap:18px;align-items:center;
          "
        >
          <input type="hidden" name="tab_id" value="{escape(tab.tab_id)}">
          <div style="{stack_block_style(gap="sm")}min-width:0;">
            <div style="{cluster_style()}">
              <strong style="{card_title_style()}">{escape(tab.title or "untitled tab")}</strong>
              {status_badge(label=status_label, kind=status_kind)}
            </div>
            <p style="{meta_paragraph_style()}">
              可見性：{escape(tab.visibility_state or "unknown")} /
              焦點：{escape(_format_focus_text(tab.has_focus))} /
              訊號：{escape(throttling_text + discarded_text)}
            </p>
            {site_label_html}
            <code style="
              display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;
              white-space:nowrap;color:{color_token("muted")};
            ">{escape(tab.url)}</code>
          </div>
          {action_html}
        </form>
        """,
    )


def _format_focus_text(has_focus: bool | None) -> str:
    """把分頁焦點狀態整理成較易讀的文字。"""
    if has_focus is True:
        return "focused"
    if has_focus is False:
        return "not_focused"
    return "unknown"
