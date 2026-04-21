"""本機 GUI 共用的 HTML component helper。"""

from __future__ import annotations

from html import escape

from app.web.ui_styles import (
    ACTION_ROW_STYLE,
    BODY_STYLE,
    CARD_STYLE,
    ERROR_STYLE,
    NOTICE_BOX_STYLE,
    PAGE_MAIN_STYLE,
    SUCCESS_STYLE,
    TABLE_STYLE,
    cell_style,
    danger_button_style,
    disabled_button_style,
    primary_button_style,
    secondary_button_style,
)


def page_layout(*, title: str, body: str) -> str:
    """輸出 GUI 共用頁面框架。"""
    return f"""
    <!doctype html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
      </head>
      <body style="{BODY_STYLE}">
        <main style="{PAGE_MAIN_STYLE}">
          {body}
        </main>
      </body>
    </html>
    """


def button_style(kind: str) -> str:
    """依語意回傳按鈕樣式，讓 UI 重排時可集中替換。"""
    if kind == "primary":
        return primary_button_style()
    if kind == "danger":
        return danger_button_style()
    if kind == "disabled":
        return disabled_button_style()
    return secondary_button_style()


def link_button(*, href: str, label: str, kind: str = "secondary") -> str:
    """渲染按鈕樣式連結，避免各頁重複組 anchor HTML。"""
    return f'<a href="{escape(href)}" style="{button_style(kind)}">{escape(label)}</a>'


def submit_button(*, label: str, kind: str = "primary", disabled: bool = False) -> str:
    """渲染表單送出按鈕，集中保留 disabled 狀態樣式。"""
    if disabled:
        return (
            f'<button type="button" style="{button_style("disabled")}" disabled>'
            f"{escape(label)}</button>"
        )
    return f'<button type="submit" style="{button_style(kind)}">{escape(label)}</button>'


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
    <table style="{TABLE_STYLE}{extra_style}">
      <thead>{header_row}</thead>
      <tbody{tbody_attrs}>{rows_html}</tbody>
    </table>
    """


def card(*, body: str, title: str | None = None, extra_style: str = "") -> str:
    """渲染標準卡片區塊，作為後續 UI 風格替換的主要邊界。"""
    title_html = f"<h2>{escape(title)}</h2>" if title is not None else ""
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
        f'<a href="{escape(href)}" style="color:#0f766e;text-decoration:none;">'
        f"{escape(label)}</a>"
    )


def action_row(*, body: str, extra_style: str = "") -> str:
    """渲染操作按鈕列，讓頁面不用重複手刻 flex 佈局。"""
    return f'<div style="{ACTION_ROW_STYLE}{extra_style}">{body}</div>'


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
    """渲染表單異動追蹤腳本，提供提示與離頁前防呆。"""
    return f"""
    <script>
      (() => {{
        const form = document.getElementById("{escape(form_id)}");
        const indicator = document.getElementById("{escape(indicator_id)}");
        if (!form || !indicator) {{
          return;
        }}

        let hasUnsavedChanges = false;

        const markUnsaved = () => {{
          hasUnsavedChanges = true;
          indicator.style.display = "inline-block";
        }};

        form.addEventListener("input", markUnsaved);
        form.addEventListener("change", markUnsaved);
        form.addEventListener("submit", () => {{
          hasUnsavedChanges = false;
        }});

        window.addEventListener("beforeunload", (event) => {{
          if (!hasUnsavedChanges) {{
            return;
          }}
          event.preventDefault();
          event.returnValue = "";
        }});
      }})();
    </script>
    """
