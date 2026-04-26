"""新增 watch 流程可替換區塊的 HTML partial renderer。"""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

from app.application.watch_editor import WatchCreationPreview
from app.domain.enums import NotificationLeafKind
from app.domain.pricing import calculate_price_per_person_per_night
from app.infrastructure.browser import ChromeTabSummary
from app.sites.base import LookupDiagnostic, SiteDescriptor
from app.web.ui_components import (
    card,
    collapsible_section,
    data_table,
    empty_state_card,
    link_button,
    section_header,
    status_badge,
    submit_button,
    table_row,
)
from app.web.ui_styles import (
    SUCCESS_STYLE,
    card_title_style,
    color_token,
    input_style,
    meta_label_style,
    meta_paragraph_style,
    muted_text_style,
    responsive_grid_style,
    secondary_button_style,
    section_title_style,
    selectable_card_style,
    stack_style,
)


def render_preview_section(
    preview: WatchCreationPreview,
    *,
    preview_cache_key: str | None = None,
) -> str:
    """渲染候選方案與建立 watch item 的第二段表單。"""
    options = []
    for candidate in preview.candidate_bundle.candidates:
        checked = (
            "checked"
            if candidate.room_id == preview.preselected_room_id
            and candidate.plan_id == preview.preselected_plan_id
            else ""
        )
        options.append(
            f"""
            <label style="{_candidate_card_style(checked=bool(checked))}">
              <span style="display:flex;gap:10px;align-items:flex-start;">
                <input
                  type="radio"
                  name="candidate_key"
                  value="{escape(candidate.room_id)}::{escape(candidate.plan_id)}"
                  {checked}
                  required
                >
                <span style="display:grid;gap:6px;">
                  <strong style="{card_title_style()}">{escape(candidate.room_name)}</strong>
                  <span style="{muted_text_style()}">{escape(candidate.plan_name)}</span>
                  {_render_candidate_price(candidate=candidate, preview=preview)}
                </span>
              </span>
            </label>
            """
        )

    prefill_status = "預填選項仍有效" if preview.preselected_still_valid else "需重新選擇有效候選"
    existing_watch_html = ""
    submit_html = submit_button(label="開始監視價格", kind="primary")
    if preview.existing_watch_id is not None:
        existing_watch_html = f"""
        <p style="{SUCCESS_STYLE}">
          目前選定目標已建立監視，不能重複建立。
        </p>
        """
        submit_html = link_button(
            href=f"/watches/{preview.existing_watch_id}",
            label="查看既有監視",
            kind="secondary",
        )
    source_summary_html = _render_preview_source_summary(
        preview=preview,
        prefill_status=prefill_status,
        existing_watch_html=existing_watch_html,
    )
    summary_panel_html = _render_create_summary_panel(preview=preview)

    return f"""
    <div class="add-watch-preview-layout" style="
      display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,340px);
      gap:24px;align-items:start;
    ">
      <form action="/watches" method="post" style="{stack_style(gap="lg")}">
        <input type="hidden" name="seed_url" value="{escape(preview.draft.seed_url)}">
        {_render_preview_browser_tab_hidden_input(preview)}
        {_render_preview_cache_key_hidden_input(preview_cache_key)}
        <section style="{_wizard_panel_style()}">
          {section_header(
              title="Step 1 確認來源",
              subtitle="確認從專用 Chrome 擷取到的飯店與條件。",
          )}
          {source_summary_html}
          {_render_preview_refresh_section(preview)}
        </section>
        <section style="{_wizard_panel_style()}">
          {section_header(
              title="Step 2 選擇方案",
              subtitle="選擇要追蹤的房型與方案。",
          )}
          <div style="{responsive_grid_style(min_width="220px", gap="14px")}">
            {''.join(options) or '<p>目前查無可建立的候選方案。</p>'}
          </div>
        </section>
        <section style="{_wizard_panel_style()}">
          {section_header(
              title="Step 3 設定通知",
              subtitle="設定檢查頻率與觸發通知的條件。",
          )}
          <div style="{responsive_grid_style(min_width="220px", gap="14px")}">
            <label style="{stack_style(gap="sm")}">
              <span>檢查頻率</span>
              <input
                type="number"
                name="scheduler_interval_seconds"
                min="60"
                value="600"
                style="{input_style()}"
              >
              <span style="{muted_text_style(font_size="13px")}">
                系統會依此頻率檢查價格變化。
              </span>
            </label>
            <label style="{stack_style(gap="sm")}">
              <span>通知條件</span>
              <select
                id="create-watch-notification-rule-kind"
                name="notification_rule_kind"
                style="{input_style()}"
              >
                <option value="{NotificationLeafKind.ANY_DROP.value}" selected>價格下降</option>
                <option value="{NotificationLeafKind.BELOW_TARGET_PRICE.value}">
                  低於目標價
                </option>
              </select>
              <span style="{muted_text_style(font_size="13px")}">
                符合條件時才會通知。
              </span>
            </label>
            <div
              id="create-watch-target-price-wrapper"
              style="{_notification_target_price_wrapper_style(NotificationLeafKind.ANY_DROP)}"
            >
              <label>目標價（僅低於目標價時使用）</label>
              <input
                type="text"
                name="target_price"
                placeholder="例如 20000"
                style="{input_style()}"
              >
              {_render_notification_target_price_hint(NotificationLeafKind.ANY_DROP)}
            </div>
          </div>
        </section>
        <section style="{_wizard_confirm_panel_style()}">
          <div>
            <h2 style="{section_title_style()}">確認建立</h2>
            <strong>設定完成後，我們將立即開始監視價格</strong>
            <p style="{meta_paragraph_style()}">
              您可隨時在「總覽」頁面查看監視狀態與價格變化。
            </p>
          </div>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            {submit_html}
          </div>
        </section>
      </form>
      {summary_panel_html}
    </div>
    {_render_notification_rule_toggle_script(
        select_id="create-watch-notification-rule-kind",
        wrapper_id="create-watch-target-price-wrapper",
    )}
    """


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


def render_diagnostics_section(diagnostics: tuple[LookupDiagnostic, ...]) -> str:
    """渲染 preview 流程的診斷資訊。"""
    if not diagnostics:
        return ""

    rows = []
    for diagnostic in diagnostics:
        cooldown_text = (
            f"（冷卻 {diagnostic.cooldown_seconds:.0f} 秒）"
            if diagnostic.cooldown_seconds is not None
            else ""
        )
        rows.append(
            table_row(
                (
                    escape(diagnostic.stage),
                    escape(diagnostic.status),
                    f"{escape(diagnostic.detail)} {escape(cooldown_text)}",
                )
            )
        )

    return collapsible_section(
        title="抓取詳情",
        body=f"""
        <h2 style="{section_title_style()}">診斷資訊</h2>
        <p>顯示本次 preview 嘗試過的方法與各步驟結果，平常不需要展開。</p>
        {data_table(
            headers=("階段", "結果", "說明"),
            rows_html="".join(rows),
        )}
        """,
    )


def format_site_label_list(site_descriptors: tuple[SiteDescriptor, ...]) -> str:
    """把站點顯示名稱整理成適合 GUI 句子使用的文字。"""
    labels = tuple(
        descriptor.display_name
        for descriptor in site_descriptors
        if descriptor.supports_browser_preview
    )
    return "、".join(labels) if labels else "支援站點"


def format_site_hint_list(site_descriptors: tuple[SiteDescriptor, ...]) -> str:
    """把站點瀏覽器開頁提示整理成適合 GUI 句子使用的文字。"""
    hints = tuple(
        descriptor.browser_tab_hint
        for descriptor in site_descriptors
        if descriptor.supports_browser_preview
    )
    return "、".join(hints) if hints else "支援站點"


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
        f'<p style="margin:0;">站點：{escape(site_label)}</p>'
        if site_label is not None
        else ""
    )
    action_html = (
        f"""
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
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
            '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">'
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
          <div style="display:grid;gap:8px;min-width:0;">
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
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


def _render_preview_source_summary(
    *,
    preview: WatchCreationPreview,
    prefill_status: str,
    existing_watch_html: str,
) -> str:
    """渲染新增監視預覽的來源摘要卡，只保留使用者需要確認的條件。"""
    prefill_status_html = (
        ""
        if preview.preselected_still_valid
        else f"""
        <p style="margin:0;">
          {status_badge(label=prefill_status, kind="warning")}
        </p>
        """
    )
    source_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    nights_text = (
        f"{preview.draft.nights} 晚"
        if preview.draft.nights is not None
        else "晚數未確認"
    )
    return f"""
        <div style="{source_grid_style};padding:16px;border:1px solid {color_token("border")};
          border-radius:12px;background:{color_token("surface_alt")};">
          <div>
            <span style="{meta_label_style()}">日期</span>
            <strong>{preview.draft.check_in_date} - {preview.draft.check_out_date}</strong>
            <p style="{meta_paragraph_style(font_size="13px")}">{escape(nights_text)}</p>
          </div>
          <div>
            <span style="{meta_label_style()}">人數 / 房數</span>
            <strong>{preview.draft.people_count} 人 / {preview.draft.room_count} 房</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">來源</span>
            <strong>專用 Chrome 分頁</strong>
          </div>
        </div>
        {prefill_status_html}
        {existing_watch_html}
    """


def _render_preview_browser_source(preview: WatchCreationPreview) -> str:
    """渲染目前 preview 的瀏覽器來源分頁資訊。"""
    if preview.browser_tab_id is None:
        return ""
    title = preview.browser_tab_title or "untitled tab"
    return f'<p style="{meta_paragraph_style()}">來源分頁：{escape(title)}</p>'


def _render_preview_browser_tab_hidden_input(preview: WatchCreationPreview) -> str:
    """在建立 watch 表單中保留目前預覽所來自的 Chrome 分頁 id。"""
    if preview.browser_tab_id is None:
        return ""
    return (
        f'<input type="hidden" name="browser_tab_id" '
        f'value="{escape(preview.browser_tab_id)}">'
    )


def _render_preview_cache_key_hidden_input(preview_cache_key: str | None) -> str:
    """在建立 watch 表單中保留本次 preview cache key，避免提交時重抓分頁。"""
    if preview_cache_key is None:
        return ""
    return (
        '<input type="hidden" name="preview_cache_key" '
        f'value="{escape(preview_cache_key)}">'
    )


def _render_create_summary_panel(*, preview: WatchCreationPreview) -> str:
    """渲染建立監視流程右側摘要，讓建立前設定可快速掃描。"""
    first_candidate = next(iter(preview.candidate_bundle.candidates), None)
    selected_candidate = next(
        (
            candidate
            for candidate in preview.candidate_bundle.candidates
            if candidate.room_id == preview.preselected_room_id
            and candidate.plan_id == preview.preselected_plan_id
        ),
        first_candidate,
    )
    selected_room_text = selected_candidate.room_name if selected_candidate else "尚未選擇"
    selected_price_text = (
        selected_candidate.display_price_text
        if selected_candidate and selected_candidate.display_price_text
        else "依選取方案確認"
    )
    return f"""
    <aside
      class="add-watch-summary"
      style="
        position:sticky;top:24px;display:grid;gap:14px;padding:20px;
        border:1px solid {color_token("border")};border-radius:16px;
        background:{color_token("surface")};
        box-shadow:0 10px 28px {color_token("shadow_soft")};
      "
    >
      <h2 style="{card_title_style()}">本次監視摘要</h2>
      {_summary_line(label="住宿設施", value=preview.candidate_bundle.hotel_name)}
      {_summary_line(
          label="入住日期",
          value=f"{preview.draft.check_in_date} - {preview.draft.check_out_date}",
      )}
      {_summary_line(
          label="人數 / 房數",
          value=f"{preview.draft.people_count} 人 / {preview.draft.room_count} 房",
      )}
      {_summary_line(label="選擇方案", value=selected_room_text)}
      {_summary_line(label="目前價格", value=selected_price_text)}
      {_summary_line(label="通知條件", value="價格下降時")}
      {_summary_line(label="檢查頻率", value="每 10 分鐘檢查一次")}
    </aside>
    """


def _summary_line(*, label: str, value: str) -> str:
    """渲染右側摘要中的單列 key-value 資訊。"""
    row_style = (
        "display:grid;gap:4px;padding-bottom:12px;"
        f"border-bottom:1px solid {color_token('border')};"
    )
    return f"""
    <div style="{row_style}">
      <span style="{meta_label_style()}">{escape(label)}</span>
      <strong>{escape(value)}</strong>
    </div>
    """


def _render_preview_refresh_section(preview: WatchCreationPreview) -> str:
    """渲染從 Chrome 分頁重新抓取的操作區塊。"""
    if preview.browser_tab_id is not None:
        return f"""
        <button
          type="submit"
          name="tab_id"
          value="{escape(preview.browser_tab_id)}"
          formaction="/watches/chrome-tabs/preview"
          formmethod="post"
          style="{secondary_button_style(size='sm')}"
        >重新抓取此分頁</button>
        """
    return f"""
    <div style="{stack_style(gap="md")}">
      <p style="{meta_paragraph_style()}">
        若要以專用 Chrome 目前頁面為準重新抓取，請改用 Chrome 分頁選擇流程。
      </p>
      {link_button(href="/watches/chrome-tabs", label="從目前專用 Chrome 頁面抓取", size="sm")}
    </div>
    """


def _render_candidate_price(*, candidate: Any, preview: WatchCreationPreview) -> str:
    """把候選方案的總價與每人每晚衍生價格渲染成簡單區塊。"""
    if candidate.display_price_text is None and candidate.normalized_price_amount is None:
        return ""

    if candidate.display_price_text is not None:
        total_price_html = escape(candidate.display_price_text)
    elif candidate.normalized_price_amount is not None and candidate.currency is not None:
        total_price_html = (
            f"{escape(candidate.currency)} "
            f"{escape(_format_decimal_for_display(candidate.normalized_price_amount))}"
        )
    else:
        total_price_html = ""

    per_person_html = ""
    if (
        candidate.normalized_price_amount is not None
        and preview.draft.nights is not None
        and preview.draft.people_count is not None
    ):
        per_person_price = calculate_price_per_person_per_night(
            candidate.normalized_price_amount,
            nights=preview.draft.nights,
            people_count=preview.draft.people_count,
        )
        currency = candidate.currency or ""
        per_person_price_text = _format_decimal_for_display(per_person_price)
        per_person_html = (
            f'<br><span style="color:{color_token("primary")};">'
            f"每人每晚：約 {escape(currency)} {escape(per_person_price_text)}"
            "</span>"
        )

    return (
        f'<span style="color:{color_token("text")};">'
        f"總價：{total_price_html}"
        f"{per_person_html}"
        "</span>"
    )


def _candidate_card_style(*, checked: bool) -> str:
    """回傳候選方案卡片樣式，讓已預選方案更容易辨識。"""
    return selectable_card_style(selected=checked)


def _wizard_panel_style() -> str:
    """回傳新增監視流程中一般步驟區塊的樣式。"""
    return (
        "display:grid;gap:14px;padding:18px;"
        f"border:1px solid {color_token('border')};"
        f"background:{color_token('surface')};"
        "border-radius:16px;"
        f"box-shadow:0 10px 28px {color_token('shadow_soft')};"
    )


def _wizard_confirm_panel_style() -> str:
    """回傳新增監視流程中確認建立區塊的樣式。"""
    return (
        "display:flex;justify-content:space-between;gap:16px;align-items:center;"
        "flex-wrap:wrap;padding:18px;"
        f"border:1px solid {color_token('border_strong')};"
        f"background:{color_token('primary_faint')};"
        "border-radius:16px;"
    )


def _format_decimal_for_display(amount: Decimal) -> str:
    """把 Decimal 數字格式化成較適合 GUI 顯示的文字。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")


def _format_focus_text(has_focus: bool | None) -> str:
    """把分頁焦點狀態整理成較易讀的文字。"""
    if has_focus is True:
        return "focused"
    if has_focus is False:
        return "not_focused"
    return "unknown"


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
    display = "none" if kind is NotificationLeafKind.ANY_DROP else "grid"
    return f"display:{display};gap:8px;"


def _render_notification_rule_toggle_script(*, select_id: str, wrapper_id: str) -> str:
    """渲染通知規則切換腳本，控制目標價欄位顯示與隱藏。"""
    any_drop_value = NotificationLeafKind.ANY_DROP.value
    return f"""
    <script>
      (() => {{
        const select = document.getElementById("{escape(select_id)}");
        const wrapper = document.getElementById("{escape(wrapper_id)}");
        if (!select || !wrapper) {{
          return;
        }}

        const syncTargetPriceVisibility = () => {{
          wrapper.style.display = select.value === "{escape(any_drop_value)}" ? "none" : "grid";
        }};

        syncTargetPriceVisibility();
        select.addEventListener("change", syncTargetPriceVisibility);
      }})();
    </script>
    """
