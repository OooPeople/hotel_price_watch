"""新增 watch 與 Chrome 分頁選擇頁面的頁面級 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.application.watch_editor import WatchCreationPreview
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic, SiteDescriptor
from app.web.ui_components import (
    action_row,
    card,
    flash_message,
    link_button,
    page_layout,
    text_link,
)
from app.web.ui_styles import SUCCESS_STYLE
from app.web.watch_creation_partials import (
    format_site_hint_list,
    format_site_label_list,
    render_chrome_tab_cards,
    render_diagnostics_section,
    render_preview_section,
)


def render_new_watch_page(
    *,
    preview: WatchCreationPreview | None = None,
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    seed_url: str = "",
    site_descriptors: tuple[SiteDescriptor, ...] = (),
) -> str:
    """渲染新增 watch item 的 editor 頁。"""
    del seed_url
    site_label_list = format_site_label_list(site_descriptors)
    site_hint_list = format_site_hint_list(site_descriptors)
    preview_html = render_preview_section(preview) if preview is not None else ""
    error_html = flash_message(error_message, kind="error")
    diagnostics_html = render_diagnostics_section(
        preview.diagnostics if preview is not None else diagnostics
    )

    return page_layout(
        title="新增 Watch",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            {text_link(href="/", label="← 回列表")}
            <h1>新增 Watch</h1>
            <p>請先在專用 Chrome 開好 {escape(site_hint_list)} 頁面，再從目前頁面抓取候選。</p>
            <p style="{SUCCESS_STYLE}">
              建議直接執行
              <code>uv run python -m app.tools.dev_start</code>
              作為單一啟動命令；系統會先檢查可附著的專用 Chrome，
              若尚未啟動則會先喚醒專用 Chrome profile，再接著啟動 GUI。
            </p>
            <p>
              若需檢查最近一次 parser / browser 行為，可直接進入
              {text_link(href="/debug/captures/latest", label="最新 debug capture")}。
            </p>
          </div>
          {error_html}
          {preview_html}
          {card(
              title="從專用 Chrome 建立 Watch",
              body=f'''
              <p style="margin:0;">
                不需要再手動貼上 Seed URL。請直接從目前專用 Chrome 頁面抓取，
                再選擇要建立 watch 的 {escape(site_label_list)} 分頁。
              </p>
              {action_row(
                  body=link_button(
                      href="/watches/chrome-tabs",
                      label="從目前專用 Chrome 頁面抓取",
                      kind="primary",
                  ),
                  extra_style="align-items:center;",
              )}
              ''',
          )}
          {diagnostics_html}
        </section>
        """,
    )


def render_chrome_tab_selection_page(
    *,
    tabs: tuple[ChromeTabSummary, ...],
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    selected_tab_id: str | None = None,
    existing_watch_ids_by_tab_id: dict[str, str] | None = None,
    site_descriptors: tuple[SiteDescriptor, ...] = (),
    site_labels_by_tab_id: dict[str, str] | None = None,
) -> str:
    """渲染專用 Chrome 分頁選擇頁。"""
    existing_watch_ids_by_tab_id = existing_watch_ids_by_tab_id or {}
    site_labels_by_tab_id = site_labels_by_tab_id or {}
    site_label_list = format_site_label_list(site_descriptors)
    site_hint_list = format_site_hint_list(site_descriptors)
    error_html = flash_message(error_message, kind="error")
    diagnostics_html = render_diagnostics_section(diagnostics)
    rows_html = render_chrome_tab_cards(
        tabs=tabs,
        selected_tab_id=selected_tab_id,
        existing_watch_ids_by_tab_id=existing_watch_ids_by_tab_id,
        site_labels_by_tab_id=site_labels_by_tab_id,
        site_label_list=site_label_list,
        site_hint_list=site_hint_list,
    )

    return page_layout(
        title="選擇 Chrome 分頁",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            {text_link(href="/watches/new", label="← 回新增頁")}
            <h1>從目前專用 Chrome 頁面抓取</h1>
            <p>
              請先在專用 Chrome 中打開你要建立 watch 的
              {escape(site_hint_list)} 頁面，再從下面清單選擇對應分頁。
            </p>
            <p style="{SUCCESS_STYLE}">
              若某個分頁顯示「可能節流」，代表它不是前景活動頁；
              建議先把該分頁切回前景後再抓取，避免背景分頁節流影響內容完整性。
            </p>
          </div>
          {error_html}
          {diagnostics_html}
          <section style="display:grid;gap:12px;">
            {rows_html}
          </section>
        </section>
        """,
    )
