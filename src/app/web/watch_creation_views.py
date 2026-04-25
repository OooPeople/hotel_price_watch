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
    page_header,
    page_layout,
)
from app.web.ui_styles import SUCCESS_STYLE, meta_paragraph_style, stack_style
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
    preview_html = render_preview_section(preview) if preview is not None else ""
    error_html = flash_message(error_message, kind="error")
    diagnostics_html = "" if preview is not None else render_diagnostics_section(diagnostics)
    page_subtitle = (
        "確認來源、房型與通知條件後開始監視。"
        if preview is not None
        else f"從專用 Chrome 中已開啟的 {site_label_list} 頁面建立價格監視。"
    )
    source_selection_html = (
        ""
        if preview is not None
        else card(
            title="Step 1 選擇來源",
            body=f'''
            <p style="margin:0;">
              選擇目前專用 Chrome 中要建立監視的 {escape(site_label_list)} 分頁。
            </p>
            {action_row(
                body=link_button(
                    href="/watches/chrome-tabs",
                    label="選擇 Chrome 分頁",
                    kind="primary",
                ),
                extra_style="align-items:center;",
            )}
            ''',
        )
    )

    return page_layout(
        title="新增監視",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="新增監視",
              subtitle=page_subtitle,
              back_href="/",
              back_label="回列表",
          )}
          {error_html}
          {preview_html}
          {source_selection_html}
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
    throttling_hint_html = (
        f"""
        <p style="{SUCCESS_STYLE};margin:0;">
          若某個分頁顯示「可能節流」，建議先把該分頁切回前景後再抓取。
        </p>
        """
        if any(tab.possible_throttling for tab in tabs)
        else ""
    )
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
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="選擇 Chrome 分頁",
              subtitle=f"選擇要建立監視的 {site_label_list} 分頁。",
              back_href="/watches/new",
              back_label="回新增頁",
          )}
          <div style="{stack_style(gap="md")}">
            <p style="{meta_paragraph_style()}">
              請先在專用 Chrome 中打開要監視的 {escape(site_hint_list)} 頁面。
            </p>
            {throttling_hint_html}
          </div>
          {error_html}
          {diagnostics_html}
          <section style="{stack_style(gap="md")}">
            {rows_html}
          </section>
        </section>
        """,
    )
