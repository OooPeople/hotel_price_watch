"""新增 watch 與 Chrome 分頁選擇頁面的頁面級 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.application.watch_editor import WatchCreationPreview
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic, SiteDescriptor
from app.web.ui_components import (
    card,
    flash_message,
    link_button,
    page_header,
    page_layout,
)
from app.web.ui_styles import (
    SUCCESS_STYLE,
    color_token,
    meta_paragraph_style,
    muted_text_style,
    stack_style,
)
from app.web.watch_creation_partials import (
    render_chrome_tab_cards,
    render_diagnostics_section,
    render_preview_section,
)
from app.web.watch_creation_presenters import (
    ChromeTabSelectionPageViewModel,
    NewWatchPageViewModel,
    build_chrome_tab_selection_page_view_model,
    build_new_watch_page_view_model,
)


def render_new_watch_page(
    *,
    preview: WatchCreationPreview | None = None,
    preview_cache_key: str | None = None,
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    seed_url: str = "",
    site_descriptors: tuple[SiteDescriptor, ...] = (),
) -> str:
    """渲染新增 watch item 的 editor 頁。"""
    del seed_url
    view_model = build_new_watch_page_view_model(
        preview=preview,
        preview_cache_key=preview_cache_key,
        error_message=error_message,
        diagnostics=diagnostics,
        site_descriptors=site_descriptors,
    )
    return render_new_watch_page_from_view_model(view_model)


def render_new_watch_page_from_view_model(view_model: NewWatchPageViewModel) -> str:
    """依新增監視頁 view model 渲染新增頁。"""
    preview_html = (
        render_preview_section(
            view_model.preview,
            preview_cache_key=view_model.preview_cache_key,
        )
        if view_model.preview is not None
        else ""
    )
    error_html = flash_message(view_model.error_message, kind="error")
    diagnostics_html = (
        ""
        if view_model.has_preview
        else render_diagnostics_section(view_model.diagnostics)
    )
    source_selection_html = (
        ""
        if view_model.has_preview
        else _render_source_selection_panel(site_label_list=view_model.site_label_list)
    )
    stepper_html = _render_add_watch_stepper(current_step=view_model.current_step)

    return page_layout(
        title="新增監視",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="新增監視",
              subtitle=view_model.page_subtitle,
              back_href="/",
              back_label="回列表",
          )}
          {stepper_html}
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
    view_model = build_chrome_tab_selection_page_view_model(
        tabs=tabs,
        error_message=error_message,
        diagnostics=diagnostics,
        selected_tab_id=selected_tab_id,
        existing_watch_ids_by_tab_id=existing_watch_ids_by_tab_id,
        site_descriptors=site_descriptors,
        site_labels_by_tab_id=site_labels_by_tab_id,
    )
    return render_chrome_tab_selection_page_from_view_model(view_model)


def render_chrome_tab_selection_page_from_view_model(
    view_model: ChromeTabSelectionPageViewModel,
) -> str:
    """依 Chrome 分頁選擇頁 view model 渲染頁面。"""
    error_html = flash_message(view_model.error_message, kind="error")
    diagnostics_html = render_diagnostics_section(view_model.diagnostics)
    throttling_hint_html = (
        f"""
        <p style="{SUCCESS_STYLE};margin:0;">
          若某個分頁顯示「可能節流」，建議先把該分頁切回前景後再抓取。
        </p>
        """
        if view_model.has_throttling_signal
        else ""
    )
    rows_html = render_chrome_tab_cards(
        tabs=view_model.tabs,
        selected_tab_id=view_model.selected_tab_id,
        existing_watch_ids_by_tab_id=view_model.existing_watch_ids_by_tab_id,
        site_labels_by_tab_id=view_model.site_labels_by_tab_id,
        site_label_list=view_model.site_label_list,
        site_hint_list=view_model.site_hint_list,
    )

    return page_layout(
        title="選擇 Chrome 分頁",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="選擇 Chrome 分頁",
              subtitle=f"選擇要建立監視的 {view_model.site_label_list} 分頁。",
              back_href="/watches/new",
              back_label="回新增頁",
          )}
          {_render_add_watch_stepper(current_step=1)}
          <div style="{stack_style(gap="md")}">
            <p style="{meta_paragraph_style()}">
              請先在專用 Chrome 中打開要監視的 {escape(view_model.site_hint_list)} 頁面。
            </p>
            {throttling_hint_html}
          </div>
          {error_html}
          {diagnostics_html}
          <div class="chrome-tab-selection-layout" style="
            display:grid;grid-template-columns:minmax(0,1fr) minmax(240px,300px);
            gap:24px;align-items:start;
          ">
            <section style="{stack_style(gap="md")}">
              {rows_html}
            </section>
            {_render_chrome_tab_help_panel()}
          </div>
        </section>
        """,
    )


def _render_add_watch_stepper(*, current_step: int) -> str:
    """渲染新增監視流程的三步驟導覽，避免上方流程與頁內區塊互相跳號。"""
    steps = (
        (1, "選擇來源", "從專用 Chrome 選擇頁面"),
        (2, "選擇方案", "選擇監視房型與追蹤期間"),
        (3, "設定通知與確認", "設定條件並建立監視"),
    )
    step_items = "".join(
        _render_stepper_item(
            number=number,
            title=title,
            subtitle=subtitle,
            current_step=current_step,
        )
        for number, title, subtitle in steps
    )
    return f"""
    <nav
      aria-label="新增監視流程"
      class="add-watch-stepper"
      style="
        display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;
        padding:18px;border:1px solid {color_token("border")};
        border-radius:16px;background:{color_token("surface")};
      "
    >
      {step_items}
    </nav>
    """


def _render_stepper_item(
    *,
    number: int,
    title: str,
    subtitle: str,
    current_step: int,
) -> str:
    """渲染新增監視 stepper 中的單一節點。"""
    is_done = number < current_step
    is_active = number == current_step
    circle_background = color_token("primary") if is_done or is_active else "#fff"
    circle_color = "#fff" if is_done or is_active else color_token("muted")
    circle_border = color_token("primary") if is_done or is_active else color_token("muted_border")
    title_color = color_token("secondary") if is_done or is_active else color_token("muted")
    return f"""
    <div style="display:flex;gap:10px;align-items:center;min-width:0;">
      <span
        aria-hidden="true"
        style="
          width:34px;height:34px;display:grid;place-items:center;border-radius:999px;
          border:1px solid {circle_border};background:{circle_background};
          color:{circle_color};font-weight:800;flex:0 0 auto;
        "
      >{"✓" if is_done else number}</span>
      <span style="display:grid;gap:2px;min-width:0;">
        <strong style="color:{title_color};white-space:nowrap;">{escape(title)}</strong>
        <span style="{muted_text_style(font_size="12px")}">{escape(subtitle)}</span>
      </span>
    </div>
    """


def _render_source_selection_panel(*, site_label_list: str) -> str:
    """渲染新增監視入口的來源選擇區塊。"""
    return f"""
    <section style="
      display:grid;grid-template-columns:minmax(260px,420px) minmax(0,1fr);
      gap:32px;align-items:center;padding:28px;
      border:1px solid {color_token("border")};border-radius:16px;
      background:{color_token("surface")};
      box-shadow:0 10px 28px {color_token("shadow_soft")};
    ">
      {_render_source_browser_mock()}
      <div style="{stack_style(gap="lg")}">
        <div>
          <p style="margin:0 0 6px;color:{color_token("primary")};font-weight:800;">
            Step 1｜選擇來源
          </p>
          <h2 style="margin:0 0 12px;font-size:24px;">
            請從專用 Chrome 選擇 {escape(site_label_list)} 頁面
          </h2>
          <p style="{meta_paragraph_style()}">
            請在專用 Chrome 中開啟您想監視的飯店與方案頁面；
            確認頁面完整載入後，再選擇該分頁開始建立監視。
          </p>
        </div>
        {link_button(
            href="/watches/chrome-tabs",
            label="選擇 Chrome 分頁",
            kind="primary",
        )}
        <p style="{meta_paragraph_style(font_size="13px")}">
          我們只會讀取頁面內容，不會儲存帳號資訊或進行任何訂房操作。
        </p>
      </div>
    </section>
    {_render_start_tips_panel()}
    """


def _render_source_browser_mock() -> str:
    """渲染新增監視入口的輕量示意圖，不使用假飯店圖片。"""
    dot_style = "width:8px;height:8px;border-radius:999px;"
    line_style = f"height:10px;border-radius:999px;background:{color_token('border')};"
    pill_style = (
        f"height:28px;width:88px;border-radius:8px;background:{color_token('primary_soft')};"
    )
    return f"""
    <div
      aria-hidden="true"
      style="
        min-height:220px;display:grid;place-items:center;border-radius:16px;
        background:linear-gradient(135deg,{color_token("primary_faint")},#fff);
      "
    >
      <div style="
        width:min(320px,90%);display:grid;gap:16px;padding:22px;
        border:1px solid {color_token("border")};border-radius:12px;background:#fff;
        box-shadow:0 16px 32px rgba(15,23,42,0.08);
      ">
        <div style="display:flex;gap:8px;">
          <span style="{dot_style}background:#94a3b8;"></span>
          <span style="{dot_style}background:{color_token("primary")};"></span>
        </div>
        <div style="display:grid;grid-template-columns:84px 1fr;gap:16px;align-items:center;">
          <div style="height:84px;border-radius:8px;background:{color_token("muted_bg")};"></div>
          <div style="display:grid;gap:10px;">
            <span style="{line_style}"></span>
            <span style="{line_style}"></span>
            <span style="{pill_style}"></span>
          </div>
        </div>
        <strong style="justify-self:end;color:{color_token("primary")};">JPY 18,434</strong>
      </div>
    </div>
    """


def _render_start_tips_panel() -> str:
    """渲染新增監視入口的開始前提醒。"""
    tips_html = "".join(
        (
            _tip_item(
                title="在專用 Chrome 開啟頁面",
                text="使用專用 Chrome 開啟 IKYU，並登入您的帳號。",
            ),
            _tip_item(
                title="確認頁面已完整載入",
                text="等待價格與房型內容完整顯示，可提高擷取成功率。",
            ),
            _tip_item(
                title="維持分頁不關閉",
                text="建立後請保留該分頁，以確保監視穩定運作。",
            ),
        )
    )
    return card(
        title="開始前的小提醒",
        body=f"""
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;">
          {tips_html}
        </div>
        """,
    )


def _tip_item(*, title: str, text: str) -> str:
    """渲染新增監視入口的小提醒項目。"""
    return f"""
    <div style="display:grid;gap:6px;">
      <strong>{escape(title)}</strong>
      <p style="{meta_paragraph_style(font_size="13px")}">{escape(text)}</p>
    </div>
    """


def _render_chrome_tab_help_panel() -> str:
    """渲染 Chrome 分頁選擇頁右側說明。"""
    tips_html = "".join(
        (
            _tip_item(
                title="僅顯示可附著的 IKYU 分頁",
                text="清單會過濾目前可讀取的專用 Chrome 分頁。",
            ),
            _tip_item(
                title="已建立的頁面不可重複建立",
                text="若目標已存在，請回到既有監視查看。",
            ),
            _tip_item(
                title="URL 僅作辨識",
                text="完整網址會降權顯示，主要以飯店與狀態判斷。",
            ),
        )
    )
    return card(
        title="選擇說明",
        body=f"""
        <div style="{stack_style(gap="md")}">
          {tips_html}
        </div>
        """,
    )
