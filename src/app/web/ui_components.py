"""本機 GUI 共用的 HTML component helper。"""

from __future__ import annotations

from html import escape

from app.web.ui_styles import (
    ACTION_ROW_STYLE,
    APP_SHELL_STYLE,
    BODY_STYLE,
    CARD_STYLE,
    ERROR_STYLE,
    NOTICE_BOX_STYLE,
    PAGE_MAIN_STYLE,
    SIDEBAR_BRAND_STYLE,
    SIDEBAR_NAV_STYLE,
    SIDEBAR_STYLE,
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
    nav_link_style,
    page_title_style,
    primary_button_style,
    secondary_button_style,
    section_title_style,
    stack_style,
    summary_value_style,
)


def page_layout(*, title: str, body: str) -> str:
    """輸出 GUI 共用頁面框架，集中 AppShell 與主要導覽。"""
    app_shell_html = _render_app_shell(title=title, body=body)
    return f"""
    <!doctype html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
        {_global_style()}
      </head>
      <body style="{BODY_STYLE}">
        {app_shell_html}
      </body>
    </html>
    """


def _render_app_shell(*, title: str, body: str) -> str:
    """渲染全站 AppShell，讓導覽與主內容區寬度保持一致。"""
    return f"""
    <div class="app-shell" style="{APP_SHELL_STYLE}">
      <aside class="app-sidebar" style="{SIDEBAR_STYLE}">
        <button
          id="sidebar-toggle"
          class="sidebar-toggle"
          type="button"
          aria-label="收合側邊選單"
          aria-expanded="true"
        >‹</button>
        <div class="sidebar-content" style="display:grid;gap:18px;">
          <a class="app-brand" href="/" style="{SIDEBAR_BRAND_STYLE}">Hotel Price Watch</a>
          <nav aria-label="主要導覽" style="{SIDEBAR_NAV_STYLE}">
            {_render_nav_link(href="/", label="我的監視", title=title)}
            {_render_nav_link(href="/watches/new", label="新增監視", title=title)}
            {_render_nav_link(href="/settings", label="設定", title=title)}
            {_render_nav_link(href="/debug/captures", label="進階診斷", title=title)}
          </nav>
        </div>
      </aside>
      <main style="{PAGE_MAIN_STYLE}">
        {body}
      </main>
    </div>
    {_app_shell_script()}
    """


def _global_style() -> str:
    """輸出少量全站 CSS，補足 inline style 不易處理的 responsive 規則。"""
    border_color = color_token("border")
    return f"""
    <style>
      * {{ box-sizing: border-box; }}
      .table-scroll table {{
        min-width: 640px;
      }}
      .action-row {{
        align-items: center;
      }}
      svg {{
        max-width: 100%;
      }}
      .watch-list-view-toggle button {{
        padding: 8px 12px;
        border: 1px solid {border_color};
        border-radius: 999px;
        background: #fff;
        color: {color_token("secondary")};
        cursor: pointer;
        font-weight: 700;
      }}
      .watch-list-view-toggle button.is-active {{
        background: {color_token("primary_soft")};
        color: {color_token("primary")};
        border-color: {color_token("border_strong")};
      }}
      .app-shell,
      .app-sidebar {{
        overflow: visible;
      }}
      .app-sidebar {{
        position: relative;
      }}
      .sidebar-toggle {{
        position: absolute;
        top: 28px;
        right: -15px;
        z-index: 20;
        width: 30px;
        height: 30px;
        display: grid;
        place-items: center;
        padding: 0;
        border: 1px solid {color_token("border_strong")};
        border-radius: 999px;
        background: {color_token("surface")};
        color: {color_token("primary")};
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
        cursor: pointer;
        font-size: 20px;
        font-weight: 800;
        line-height: 1;
      }}
      .sidebar-toggle:hover {{
        background: {color_token("primary_soft")};
      }}
      .app-shell.sidebar-collapsed {{
        grid-template-columns: 0 minmax(0, 1fr) !important;
      }}
      .app-shell.sidebar-collapsed .app-sidebar {{
        padding: 0 !important;
        border-right: none !important;
        background: transparent !important;
      }}
      .app-shell.sidebar-collapsed .sidebar-content {{
        display: none !important;
      }}
      @media (max-width: 820px) {{
        .app-shell {{
          display: block !important;
        }}
        .app-sidebar {{
          position: sticky;
          top: 0;
          z-index: 10;
          border-right: none !important;
          border-bottom: 1px solid {border_color};
        }}
        .app-sidebar nav {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .sidebar-toggle {{
          top: 18px;
          right: 14px;
        }}
        .app-shell.sidebar-collapsed .app-sidebar {{
          min-height: 54px;
          border-bottom: 1px solid {border_color} !important;
          background: {color_token("surface")} !important;
        }}
      }}
      @media (max-width: 640px) {{
        main {{
          padding: 20px 14px 48px !important;
        }}
        .page-header {{
          display: grid !important;
          gap: 14px !important;
        }}
        .page-header .action-row {{
          width: 100%;
        }}
        .page-header .action-row > a,
        .page-header .action-row > form,
        .page-header .action-row button {{
          width: 100%;
          text-align: center;
        }}
        .app-sidebar {{
          padding: 18px 14px !important;
        }}
        .app-sidebar nav {{
          grid-template-columns: 1fr !important;
        }}
        .watch-detail-hero {{
          display: grid !important;
        }}
        .watch-detail-hero-price {{
          min-width: 0 !important;
          text-align: left !important;
        }}
        .watch-card-header,
        .watch-card-footer {{
          display: grid !important;
        }}
      }}
    </style>
    """


def _app_shell_script() -> str:
    """渲染 AppShell 側邊選單收合腳本，並記住使用者偏好。"""
    return """
    <script>
      (() => {
        const shell = document.querySelector(".app-shell");
        const toggle = document.getElementById("sidebar-toggle");
        if (!shell || !toggle) {
          return;
        }

        const storageKey = "hotelPriceWatch.sidebarCollapsed";
        const applyCollapsedState = (collapsed) => {
          shell.classList.toggle("sidebar-collapsed", collapsed);
          toggle.textContent = collapsed ? "›" : "‹";
          toggle.setAttribute("aria-label", collapsed ? "展開側邊選單" : "收合側邊選單");
          toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        };

        applyCollapsedState(window.localStorage.getItem(storageKey) === "1");
        toggle.addEventListener("click", () => {
          const nextCollapsed = !shell.classList.contains("sidebar-collapsed");
          window.localStorage.setItem(storageKey, nextCollapsed ? "1" : "0");
          applyCollapsedState(nextCollapsed);
        });
      })();
    </script>
    """


def _render_nav_link(*, href: str, label: str, title: str) -> str:
    """依目前頁面標題渲染 sidebar 導覽連結。"""
    active = _nav_link_is_active(label=label, title=title)
    return (
        f'<a href="{escape(href)}" style="{nav_link_style(active=active)}">'
        f"{escape(label)}</a>"
    )


def _nav_link_is_active(*, label: str, title: str) -> bool:
    """用頁面標題推斷目前導覽位置，避免每個 renderer 額外傳 context。"""
    if label == "我的監視":
        return title.startswith("我的價格監視") or title.startswith("監視詳情")
    if label == "新增監視":
        return "新增監視" in title or "選擇 Chrome 分頁" in title
    if label == "設定":
        return title == "設定" or title == "通知設定"
    if label == "進階診斷":
        return "進階診斷" in title
    return False


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
