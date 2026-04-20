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
from app.web.view_helpers import (
    CARD_STYLE,
    SUCCESS_STYLE,
    cell_style,
    input_style,
    primary_button_style,
    secondary_button_style,
)


def render_preview_section(preview: WatchCreationPreview) -> str:
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
            <label style="display:block;padding:12px;border:1px solid #d7e2df;margin-bottom:8px;">
              <input
                type="radio"
                name="candidate_key"
                value="{escape(candidate.room_id)}::{escape(candidate.plan_id)}"
                {checked}
                required
              >
              <strong>{escape(candidate.room_name)}</strong><br>
              <span>{escape(candidate.plan_name)}</span>
              {_render_candidate_price(candidate=candidate, preview=preview)}
            </label>
            """
        )

    prefill_status = "預填選項仍有效" if preview.preselected_still_valid else "需重新選擇有效候選"
    prefill_color = "#166534" if preview.preselected_still_valid else "#92400e"
    existing_watch_html = ""
    submit_html = (
        f'<button type="submit" style="{primary_button_style()}">'
        "建立 Watch Item"
        "</button>"
    )
    if preview.existing_watch_id is not None:
        existing_watch_html = f"""
        <p style="{SUCCESS_STYLE}">
          目前選定目標已建立 watch。
          <a
            href="/watches/{escape(preview.existing_watch_id)}"
            style="color:#0f766e;"
          >
            查看既有 watch
          </a>
        </p>
        """
        submit_html = (
            f'<button type="button" style="{_disabled_button_style()}" disabled>'
            "已建立 watch"
            "</button>"
        )
    debug_capture_html = ""
    if preview.candidate_bundle.debug_artifact_paths:
        html_path, meta_path = preview.candidate_bundle.debug_artifact_paths
        debug_capture_html = f"""
        <p style="color:#92400e;">
          已自動保存 debug capture：
          HTML = <code>{escape(html_path)}</code>，
          Metadata = <code>{escape(meta_path)}</code>
        </p>
        <p><a href="/debug/captures/latest" style="color:#0f766e;">查看最新 debug capture</a></p>
        """

    return f"""
    <section style="{CARD_STYLE}">
      <div>
        <h2>{escape(preview.candidate_bundle.hotel_name)}</h2>
        <p>日期：{preview.draft.check_in_date} - {preview.draft.check_out_date}</p>
        <p>人數 / 房數：{preview.draft.people_count} / {preview.draft.room_count}</p>
        {_render_preview_browser_source(preview)}
        <p style="color:{prefill_color};">{prefill_status}</p>
        {existing_watch_html}
        {debug_capture_html}
      </div>
      {_render_preview_refresh_section(preview)}
      <form action="/watches" method="post" style="display:grid;gap:12px;">
        <input type="hidden" name="seed_url" value="{escape(preview.draft.seed_url)}">
        {_render_preview_browser_tab_hidden_input(preview)}
        <div>{''.join(options) or '<p>目前查無可建立的候選方案。</p>'}</div>
        <label>輪詢秒數</label>
        <input
          type="number"
          name="scheduler_interval_seconds"
          min="60"
          value="600"
          style="{input_style()}"
        >
        <label>通知條件</label>
        <select
          id="create-watch-notification-rule-kind"
          name="notification_rule_kind"
          style="{input_style()}"
        >
          <option value="{NotificationLeafKind.ANY_DROP.value}">價格下降</option>
          <option
            value="{NotificationLeafKind.BELOW_TARGET_PRICE.value}"
            selected
          >
            低於目標價
          </option>
        </select>
        <div
          id="create-watch-target-price-wrapper"
          style="{_notification_target_price_wrapper_style(NotificationLeafKind.BELOW_TARGET_PRICE)}"
        >
          <label>目標價（僅低於目標價時使用）</label>
          <input type="text" name="target_price" placeholder="例如 20000" style="{input_style()}">
          {_render_notification_target_price_hint(NotificationLeafKind.BELOW_TARGET_PRICE)}
        </div>
        {submit_html}
      </form>
      {_render_notification_rule_toggle_script(
          select_id="create-watch-notification-rule-kind",
          wrapper_id="create-watch-target-price-wrapper",
      )}
    </section>
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

    return "".join(rows) or f"""
    <section style="{CARD_STYLE}">
      <p>目前找不到可用的 {escape(site_label_list)} Chrome 分頁。</p>
      <p>
        請先執行 <code>uv run python -m app.tools.dev_start</code>，
        並在專用 Chrome 中打開 {escape(site_hint_list)} 頁面後再重試。
      </p>
    </section>
    """


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
            f"""
            <tr>
              <td style="{cell_style(head=False)}">{escape(diagnostic.stage)}</td>
              <td style="{cell_style(head=False)}">{escape(diagnostic.status)}</td>
              <td style="{cell_style(head=False)}">
                {escape(diagnostic.detail)} {escape(cooldown_text)}
              </td>
            </tr>
            """
        )

    return f"""
    <section style="{CARD_STYLE}">
      <div>
        <h2>診斷資訊</h2>
        <p>顯示本次 preview 嘗試過的方法與各步驟結果。</p>
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr>
            <th style="{cell_style(head=True)}">階段</th>
            <th style="{cell_style(head=True)}">結果</th>
            <th style="{cell_style(head=True)}">說明</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


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
    row_style = CARD_STYLE
    if tab.tab_id == selected_tab_id:
        row_style += "border-color:#0f766e;"
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
        <div style="display:grid;gap:8px;justify-items:start;">
          <span style="color:#92400e;font-weight:600;">已建立 watch</span>
          <a href="/watches/{escape(linked_watch_id)}" style="{secondary_button_style()}">
            查看既有 watch
          </a>
          <button
            type="button"
            style="{_disabled_button_style()}"
            disabled
          >
            已建立 watch
          </button>
        </div>
        """
        if linked_watch_id is not None
        else f'<button type="submit" style="{primary_button_style()}">抓取此分頁</button>'
    )
    return f"""
    <form action="/watches/chrome-tabs/preview" method="post" style="{row_style}">
      <input type="hidden" name="tab_id" value="{escape(tab.tab_id)}">
      <div style="display:grid;gap:8px;">
        <strong>{escape(tab.title or "untitled tab")}</strong>
        <code style="word-break:break-all;">{escape(tab.url)}</code>
        <p style="margin:0;">
          可見性：{escape(tab.visibility_state or "unknown")}，
          焦點：{escape(_format_focus_text(tab.has_focus))}，
          訊號：{escape(throttling_text + discarded_text)}
        </p>
        {site_label_html}
      </div>
      {action_html}
    </form>
    """


def _render_preview_browser_source(preview: WatchCreationPreview) -> str:
    """渲染目前 preview 的瀏覽器來源分頁資訊。"""
    if preview.browser_tab_id is None:
        return ""
    title = preview.browser_tab_title or "untitled tab"
    return f"<p>來源分頁：{escape(title)}</p>"


def _render_preview_browser_tab_hidden_input(preview: WatchCreationPreview) -> str:
    """在建立 watch 表單中保留目前預覽所來自的 Chrome 分頁 id。"""
    if preview.browser_tab_id is None:
        return ""
    return (
        f'<input type="hidden" name="browser_tab_id" '
        f'value="{escape(preview.browser_tab_id)}">'
    )


def _render_preview_refresh_section(preview: WatchCreationPreview) -> str:
    """渲染從 Chrome 分頁重新抓取的操作區塊。"""
    if preview.browser_tab_id is not None:
        return f"""
        <form action="/watches/chrome-tabs/preview" method="post" style="display:grid;gap:12px;">
          <input type="hidden" name="tab_id" value="{escape(preview.browser_tab_id)}">
          <button type="submit" style="{secondary_button_style()}">
            從同一個 Chrome 分頁重新抓取
          </button>
        </form>
        """
    return f"""
    <div style="display:grid;gap:12px;">
      <p style="margin:0;color:#4b635f;">
        若要以專用 Chrome 目前頁面為準重新抓取，請改用 Chrome 分頁選擇流程。
      </p>
      <a href="/watches/chrome-tabs" style="{secondary_button_style()}">
        從目前專用 Chrome 頁面抓取
      </a>
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
            '<br><span style="color:#0f766e;">'
            f"每人每晚：約 {escape(currency)} {escape(per_person_price_text)}"
            "</span>"
        )

    return (
        '<br><span style="color:#18322f;">'
        f"總價：{total_price_html}"
        f"{per_person_html}"
        "</span>"
    )


def _disabled_button_style() -> str:
    """回傳不可操作按鈕的 inline style。"""
    return (
        "display:inline-block;padding:12px 18px;background:#e5e7eb;color:#6b7280;"
        "text-decoration:none;border:1px solid #d1d5db;border-radius:8px;cursor:not-allowed;"
        "opacity:0.85;"
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
            '<p style="margin:0;color:#4b635f;">'
            "目前為「價格下降」，目標價欄位會被忽略。"
            "</p>"
        )
    return (
        '<p style="margin:0;color:#4b635f;">'
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
