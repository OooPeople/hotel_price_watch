"""本機 GUI 共用的基礎 UI primitive renderer。"""

from __future__ import annotations

from html import escape

from app.web.ui_behaviors import render_unsaved_changes_script
from app.web.ui_styles import (
    ACTION_ROW_STYLE,
    CARD_STYLE,
    ERROR_STYLE,
    NOTICE_BOX_STYLE,
    SUCCESS_STYLE,
    SUMMARY_CARD_STYLE,
    TABLE_STYLE,
    badge_style,
    card_title_style,
    cell_style,
    color_token,
    danger_button_style,
    disabled_button_style,
    muted_text_style,
    page_title_style,
    primary_button_style,
    secondary_button_style,
    section_title_style,
    stack_style,
    summary_value_style,
)


def page_header(
    *,
    title: str,
    subtitle: str | None = None,
    actions_html: str = "",
    back_href: str | None = None,
    back_label: str = "返回",
) -> str:
    """渲染產品頁面標題區，集中管理首屏標題與主要操作。"""
    back_label_text = f"← {back_label}"
    back_html = (
        f'<div style="margin-bottom:10px;">'
        f"{text_link(href=back_href, label=back_label_text)}</div>"
        if back_href is not None
        else ""
    )
    subtitle_html = (
        f'<p style="margin:6px 0 0;{muted_text_style()}">{escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    header_style = (
        "display:flex;justify-content:space-between;gap:20px;"
        "align-items:flex-start;"
    )
    return f"""
    <header class="page-header" style="{header_style}">
      <div>
        {back_html}
        <h1 style="{page_title_style()}">{escape(title)}</h1>
        {subtitle_html}
      </div>
      {actions_html}
    </header>
    """


def section_header(*, title: str, subtitle: str | None = None) -> str:
    """渲染頁面區塊標題，讓內容層級在各頁保持一致。"""
    subtitle_html = (
        f'<p style="margin:4px 0 0;{muted_text_style()}">{escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    return f"""
    <div>
      <h2 style="{section_title_style()}">{escape(title)}</h2>
      {subtitle_html}
    </div>
    """


def button_style(kind: str, *, size: str = "md") -> str:
    """依語意回傳按鈕樣式，讓 UI 重排時可集中替換。"""
    if kind == "primary":
        return primary_button_style(size=size)
    if kind == "danger":
        return danger_button_style(size=size)
    if kind == "disabled":
        return disabled_button_style(size=size)
    return secondary_button_style(size=size)


def status_badge(*, label: str, kind: str = "muted") -> str:
    """渲染統一狀態 badge，避免各頁自行決定顏色與樣式。"""
    return f'<span style="{badge_style(kind)}">{escape(label)}</span>'


def summary_card(
    *,
    label: str,
    value: str,
    helper_text: str | None = None,
    value_html: str | None = None,
) -> str:
    """渲染摘要卡片，必要時允許受控 HTML 呈現分行數值。"""
    helper_html = (
        f'<span style="{muted_text_style(font_size="13px")}">{escape(helper_text)}</span>'
        if helper_text
        else ""
    )
    value_content = value_html if value_html is not None else escape(value)
    return f"""
    <section style="{SUMMARY_CARD_STYLE}">
      <span style="{muted_text_style(font_size="13px")}">{escape(label)}</span>
      <strong style="{summary_value_style()}">{value_content}</strong>
      {helper_html}
    </section>
    """


def key_value_grid(rows: tuple[tuple[str, str], ...]) -> str:
    """渲染 key-value 資訊列，供 hero summary 與設定摘要共用。"""
    items = "".join(
        "<div>"
        f'<span style="display:block;{muted_text_style(font_size="13px")}">'
        f"{escape(label)}</span>"
        f'<strong style="font-size:15px;">{value}</strong>'
        "</div>"
        for label, value in rows
    )
    return (
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));'
        f'gap:14px;">{items}</div>'
    )


def collapsible_section(
    *,
    title: str,
    body: str,
    open_by_default: bool = False,
) -> str:
    """渲染收合區塊，讓 debug 與進階資訊預設降權。"""
    open_attr = " open" if open_by_default else ""
    return f"""
    <details{open_attr} style="{CARD_STYLE}">
      <summary style="cursor:pointer;font-weight:700;">{escape(title)}</summary>
      <div style="{stack_style(gap="md")}margin-top:12px;">
        {body}
      </div>
    </details>
    """


def link_button(
    *,
    href: str,
    label: str,
    kind: str = "secondary",
    size: str = "md",
) -> str:
    """渲染按鈕樣式連結，避免各頁重複組 anchor HTML。"""
    return (
        f'<a href="{escape(href)}" style="{button_style(kind, size=size)}">'
        f"{escape(label)}</a>"
    )


def submit_button(
    *,
    label: str,
    kind: str = "primary",
    disabled: bool = False,
    size: str = "md",
) -> str:
    """渲染表單送出按鈕，集中保留 disabled 狀態樣式。"""
    if disabled:
        return (
            f'<button type="button" style="{button_style("disabled", size=size)}" disabled>'
            f"{escape(label)}</button>"
        )
    return (
        f'<button type="submit" style="{button_style(kind, size=size)}">'
        f"{escape(label)}</button>"
    )


def table_cell(content: str, *, head: bool = False) -> str:
    """渲染表格儲存格，讓 table 結構不用散落在各 partial。"""
    tag = "th" if head else "td"
    return f'<{tag} style="{cell_style(head=head)}">{content}</{tag}>'


def table_row(cells: tuple[str, ...], *, head: bool = False) -> str:
    """渲染表格列，呼叫端可傳入已 escape 或安全組好的 HTML。"""
    return f"<tr>{''.join(table_cell(cell, head=head) for cell in cells)}</tr>"


def data_table(
    *,
    headers: tuple[str, ...],
    rows_html: str,
    body_id: str | None = None,
    extra_style: str = "",
) -> str:
    """渲染標準資料表格外框，讓欄位與內容可各自維護。"""
    header_row = table_row(tuple(escape(header) for header in headers), head=True)
    tbody_attrs = f' id="{escape(body_id)}"' if body_id is not None else ""
    return f"""
    <div class="table-scroll" style="overflow-x:auto;">
      <table style="{TABLE_STYLE}{extra_style}">
        <thead>{header_row}</thead>
        <tbody{tbody_attrs}>{rows_html}</tbody>
      </table>
    </div>
    """


def card(*, body: str, title: str | None = None, extra_style: str = "") -> str:
    """渲染標準卡片區塊，作為後續 UI 風格替換的主要邊界。"""
    title_html = (
        f'<h2 style="{card_title_style()}">{escape(title)}</h2>'
        if title is not None
        else ""
    )
    return f"""
    <section style="{CARD_STYLE}{extra_style}">
      {title_html}
      {body}
    </section>
    """


def empty_state_card(
    *,
    title: str,
    message: str,
    extra_html: str = "",
) -> str:
    """渲染沒有資料時的標準卡片提示。"""
    return card(
        title=title,
        body=f"<p>{escape(message)}</p>{extra_html}",
    )


def notice_box(*, body: str) -> str:
    """渲染輕量提示區塊，供 runtime 訊號與局部說明共用。"""
    return f"""
    <div style="{NOTICE_BOX_STYLE}">
      {body}
    </div>
    """


def text_link(*, href: str, label: str) -> str:
    """渲染一般文字連結，集中管理基本連結樣式。"""
    return (
        f'<a href="{escape(href)}" style="color:{color_token("primary")};'
        'text-decoration:none;font-weight:600;">'
        f"{escape(label)}</a>"
    )


def action_row(*, body: str, extra_style: str = "") -> str:
    """渲染操作按鈕列，讓頁面不用重複手刻 flex 佈局。"""
    return f'<div class="action-row" style="{ACTION_ROW_STYLE}{extra_style}">{body}</div>'


def flash_message(message: str | None, *, kind: str = "success") -> str:
    """渲染標準 flash / error 訊息。"""
    if not message:
        return ""
    style = ERROR_STYLE if kind == "error" else SUCCESS_STYLE
    return f'<p style="{style}">{escape(message)}</p>'


def form_card(
    *,
    action: str,
    body: str,
    method: str = "post",
    form_id: str | None = None,
) -> str:
    """渲染卡片樣式表單，統一設定頁與建立頁的表單外框。"""
    id_attr = f' id="{escape(form_id)}"' if form_id is not None else ""
    return f"""
    <form{id_attr} action="{escape(action)}" method="{escape(method)}" style="{CARD_STYLE}">
      {body}
    </form>
    """


def unsaved_changes_indicator(
    *,
    indicator_id: str = "unsaved-changes-indicator",
) -> str:
    """渲染設定未儲存提示，預設隱藏並交由共用腳本控制。"""
    return (
        f'<span id="{escape(indicator_id)}" '
        'style="display:none;color:#92400e;font-weight:600;">'
        "尚未儲存"
        "</span>"
    )


def unsaved_changes_script(
    *,
    form_id: str,
    indicator_id: str = "unsaved-changes-indicator",
) -> str:
    """相容舊入口，委派到集中管理的 behavior script renderer。"""
    return render_unsaved_changes_script(
        form_id=form_id,
        indicator_id=indicator_id,
    )
