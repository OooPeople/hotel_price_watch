"""本機 GUI 的簡單 HTML render helpers。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Iterable

from app.application.debug_captures import DebugCaptureDetail, DebugCaptureSummary
from app.application.watch_editor import WatchCreationPreview
from app.config.models import NotificationChannelSettings
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    WatchItem,
)
from app.domain.enums import NotificationLeafKind
from app.domain.pricing import calculate_price_per_person_per_night
from app.infrastructure.browser import ChromeTabSummary
from app.monitor.runtime import MonitorRuntimeStatus
from app.sites.base import LookupDiagnostic

_CARD_STYLE = "display:grid;gap:12px;padding:20px;border:1px solid #d7e2df;background:#fcfffe;"
_ERROR_STYLE = "padding:12px;border:1px solid #e57c7c;background:#fff3f3;"
_SUCCESS_STYLE = "padding:12px;border:1px solid #9fd3c7;background:#edf7f3;"
_BODY_STYLE = (
    "margin:0;background:#f4f7f6;color:#18322f;"
    "font-family:'Microsoft JhengHei UI','Noto Sans TC',sans-serif;"
)


def render_watch_list_page(
    *,
    watch_items: Iterable[WatchItem],
    flash_message: str | None = None,
    runtime_status: MonitorRuntimeStatus | None = None,
) -> str:
    """渲染 watch item 列表頁。"""
    rows = []
    for watch_item in watch_items:
        date_range = (
            f"{watch_item.target.check_in_date.isoformat()} - "
            f"{watch_item.target.check_out_date.isoformat()}"
        )
        actions_html = _render_watch_action_controls(
            watch_item=watch_item,
            show_check_now=False,
        )
        rows.append(
            f"""
            <tr>
              <td>
                <a href="/watches/{escape(watch_item.id)}" style="color:#0f766e;">
                  {escape(watch_item.hotel_name)}
                </a>
              </td>
              <td>{escape(watch_item.room_name)}</td>
              <td>{escape(watch_item.plan_name)}</td>
              <td>{date_range}</td>
              <td>{watch_item.scheduler_interval_seconds}</td>
              <td>{escape(_describe_watch_status(watch_item))}</td>
              <td>{actions_html}</td>
            </tr>
            """
        )

    flash_html = (
        f'<p style="{_SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    runtime_html = _render_runtime_status_section(runtime_status)
    table_body = "\n".join(rows) or '<tr><td colspan="7">目前尚無 watch item。</td></tr>'
    return _page_layout(
        title="Watch Items",
        body=f"""
        <section>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;">
            <div>
              <h1>Watch Items</h1>
              <p>目前可透過 URL 預填與候選列表建立新的監看項。</p>
            </div>
            <div style="display:flex;gap:12px;align-items:center;">
              <a href="/settings/notifications" style="{_secondary_button_style()}">全域通知設定</a>
              <a href="/debug/captures" style="{_secondary_button_style()}">Debug 區</a>
              <a href="/watches/new" style="{_primary_button_style()}">新增 Watch</a>
            </div>
          </div>
          {flash_html}
          {runtime_html}
          <table style="width:100%;border-collapse:collapse;margin-top:20px;">
            <thead>
              <tr>
                <th style="{_cell_style(head=True)}">飯店</th>
                <th style="{_cell_style(head=True)}">房型</th>
                <th style="{_cell_style(head=True)}">方案</th>
                <th style="{_cell_style(head=True)}">日期</th>
                <th style="{_cell_style(head=True)}">輪詢秒數</th>
                <th style="{_cell_style(head=True)}">狀態</th>
                <th style="{_cell_style(head=True)}">操作</th>
              </tr>
            </thead>
            <tbody>{table_body}</tbody>
          </table>
        </section>
        """,
    )


def _render_runtime_status_section(runtime_status: MonitorRuntimeStatus | None) -> str:
    """在首頁顯示 background monitor runtime 的狀態摘要。"""
    if runtime_status is None:
        return ""

    running_text = "運行中" if runtime_status.is_running else "未啟動"
    chrome_text = "可附著" if runtime_status.chrome_debuggable else "不可附著"
    last_tick_text = _format_datetime_for_display(runtime_status.last_tick_at)
    last_sync_text = _format_datetime_for_display(runtime_status.last_watch_sync_at)
    return f"""
    <section style="{_CARD_STYLE};margin-top:20px;">
      <h2 style="margin:0;">Background Monitor</h2>
      <p style="margin:0;">狀態：{escape(running_text)}</p>
      <p style="margin:0;">Chrome session：{escape(chrome_text)}</p>
      <p style="margin:0;">已啟用 watch：{runtime_status.enabled_watch_count}</p>
      <p style="margin:0;">已註冊排程：{runtime_status.registered_watch_count}</p>
      <p style="margin:0;">執行中 worker：{runtime_status.inflight_watch_count}</p>
      <p style="margin:0;">最後 tick：{escape(last_tick_text)}</p>
      <p style="margin:0;">最後同步 watch：{escape(last_sync_text)}</p>
    </section>
    """


def render_new_watch_page(
    *,
    preview: WatchCreationPreview | None = None,
    error_message: str | None = None,
    diagnostics: tuple[LookupDiagnostic, ...] = (),
    seed_url: str = "",
) -> str:
    """渲染新增 watch item 的 editor 頁。"""
    del seed_url
    preview_html = ""
    if preview is not None:
        preview_html = _render_preview_section(preview)

    error_html = (
        f'<p style="{_ERROR_STYLE}">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    diagnostics_html = _render_diagnostics_section(
        preview.diagnostics if preview is not None else diagnostics
    )

    return _page_layout(
        title="新增 Watch",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            <a href="/" style="color:#0f766e;text-decoration:none;">← 回列表</a>
            <h1>新增 Watch</h1>
            <p>先貼入 `ikyu` 一般飯店頁或已帶 `rm/pln` 的精確 URL。</p>
            <p style="{_SUCCESS_STYLE}">
              建議直接執行
              <code>uv run python -m app.tools.dev_start</code>
              作為單一啟動命令；系統會先檢查可附著的專用 Chrome，
              若尚未啟動則會先喚醒專用 Chrome profile，再接著啟動 GUI。
            </p>
            <p>
              若需檢查最近一次 parser / browser 行為，可直接進入
              <a href="/debug/captures/latest" style="color:#0f766e;">最新 debug capture</a>。
            </p>
          </div>
          {error_html}
          {preview_html}
          <section style="{_CARD_STYLE}">
            <h2 style="margin:0;">從專用 Chrome 建立 Watch</h2>
            <p style="margin:0;">
              不需要再手動貼上 Seed URL。請直接從目前專用 Chrome 頁面抓取，
              再選擇要建立 watch 的 `ikyu` 分頁。
            </p>
            <div style="display:flex;gap:12px;align-items:center;">
              <a href="/watches/chrome-tabs" style="{_primary_button_style()}">
                從目前專用 Chrome 頁面抓取
              </a>
            </div>
          </section>
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
) -> str:
    """渲染專用 Chrome 分頁選擇頁。"""
    error_html = (
        f'<p style="{_ERROR_STYLE}">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    diagnostics_html = _render_diagnostics_section(diagnostics)
    rows = []
    for tab in tabs:
        row_style = _CARD_STYLE
        if tab.tab_id == selected_tab_id:
            row_style += "border-color:#0f766e;"
        throttling_text = "可能節流" if tab.possible_throttling else "正常"
        discarded_text = "；曾被丟棄" if tab.was_discarded else ""
        rows.append(
            f"""
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
              </div>
              <button type="submit" style="{_primary_button_style()}">抓取此分頁</button>
            </form>
            """
        )

    rows_html = "".join(rows) or f"""
    <section style="{_CARD_STYLE}">
      <p>目前找不到可用的 `ikyu` Chrome 分頁。</p>
      <p>
        請先執行 <code>uv run python -m app.tools.dev_start</code>，
        並在專用 Chrome 中打開 `ikyu` 頁面後再重試。
      </p>
    </section>
    """
    return _page_layout(
        title="選擇 Chrome 分頁",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            <a href="/watches/new" style="color:#0f766e;text-decoration:none;">← 回新增頁</a>
            <h1>從目前專用 Chrome 頁面抓取</h1>
            <p>請先在專用 Chrome 中打開你要建立 watch 的 `ikyu` 頁面，再從下面清單選擇對應分頁。</p>
            <p style="{_SUCCESS_STYLE}">
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


def render_watch_detail_page(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    check_events: tuple[CheckEvent, ...],
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
    flash_message: str | None = None,
) -> str:
    """渲染單一 watch item 的詳細頁與歷史摘要。"""
    target_date_range = (
        f"{watch_item.target.check_in_date.isoformat()} - "
        f"{watch_item.target.check_out_date.isoformat()}"
    )
    latest_snapshot_html = _render_latest_snapshot_section(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        notification_state=notification_state,
        debug_artifacts=debug_artifacts,
    )
    check_events_html = _render_check_events_section(check_events)
    debug_artifacts_html = _render_debug_artifacts_section(debug_artifacts)
    flash_html = (
        f'<p style="{_SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    action_controls_html = _render_watch_action_controls(
        watch_item=watch_item,
        show_check_now=True,
    )

    return _page_layout(
        title=f"Watch Detail - {watch_item.hotel_name}",
        body=f"""
        <section style="display:grid;gap:20px;">
          <div>
            <a href="/" style="color:#0f766e;text-decoration:none;">← 回列表</a>
            <h1>{escape(watch_item.hotel_name)}</h1>
            <p>房型：{escape(watch_item.room_name)}</p>
            <p>方案：{escape(watch_item.plan_name)}</p>
            <p>
              監看條件：
              {target_date_range}
              ，{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房
            </p>
            <p>輪詢秒數：{watch_item.scheduler_interval_seconds}</p>
            <p>目前狀態：{escape(_describe_watch_status(watch_item))}</p>
            <p>Canonical URL：<code>{escape(watch_item.canonical_url)}</code></p>
            <p>
              <a
                href="/watches/{escape(watch_item.id)}/notification-settings"
                style="{_secondary_button_style()}"
              >
                通知設定
              </a>
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">{action_controls_html}</div>
          </div>
          {flash_html}
          {latest_snapshot_html}
          {check_events_html}
          {debug_artifacts_html}
        </section>
        """,
    )


def render_notification_settings_page(
    *,
    watch_item: WatchItem,
    error_message: str | None = None,
    flash_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> str:
    """渲染單一 watch item 的通知設定頁。"""
    rule = watch_item.notification_rule
    form_values = form_values or {}
    selected_kind_value = form_values.get(
        "notification_rule_kind",
        getattr(rule, "kind", NotificationLeafKind.ANY_DROP).value,
    )
    selected_kind = NotificationLeafKind(selected_kind_value)
    if "target_price" in form_values:
        target_price_value = escape(form_values["target_price"])
    else:
        stored_target_price = getattr(rule, "target_price", None)
        target_price_value = (
            escape(_format_decimal_for_display(stored_target_price))
            if stored_target_price is not None
            else ""
        )
    error_html = (
        f'<p style="{_ERROR_STYLE}">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    flash_html = (
        f'<p style="{_SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    target_price_wrapper_style = _notification_target_price_wrapper_style(selected_kind)
    return _page_layout(
        title=f"通知設定 - {watch_item.hotel_name}",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            <a href="/watches/{escape(watch_item.id)}" style="color:#0f766e;text-decoration:none;">
              ← 回 watch 詳細頁
            </a>
            <h1>通知設定</h1>
            <p>{escape(watch_item.hotel_name)} / {escape(watch_item.room_name)}</p>
            <p>{escape(watch_item.plan_name)}</p>
          </div>
          {error_html}
          {flash_html}
          <form
            action="/watches/{escape(watch_item.id)}/notification-settings"
            method="post"
            style="{_CARD_STYLE}"
          >
            <label>通知條件</label>
            <select
              id="notification-rule-kind"
              name="notification_rule_kind"
              style="{_input_style()}"
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
            <div id="notification-target-price-wrapper" style="{target_price_wrapper_style}">
              <label>目標價（僅低於目標價時使用）</label>
              <input
                type="text"
                name="target_price"
                value="{target_price_value}"
                placeholder="例如 20000"
                style="{_input_style()}"
              >
              {_render_notification_target_price_hint(selected_kind)}
            </div>
            <button type="submit" style="{_primary_button_style()}">儲存通知設定</button>
          </form>
          {_render_notification_rule_toggle_script(
              select_id="notification-rule-kind",
              wrapper_id="notification-target-price-wrapper",
          )}
        </section>
        """,
    )


def render_notification_channel_settings_page(
    *,
    settings: NotificationChannelSettings,
    error_message: str | None = None,
    flash_message: str | None = None,
    test_result_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> str:
    """渲染主頁層級的全域通知通道設定頁。"""
    form_values = form_values or {}
    desktop_enabled = _form_checkbox_value(
        form_values,
        key="desktop_enabled",
        fallback=settings.desktop_enabled,
    )
    ntfy_enabled = _form_checkbox_value(
        form_values,
        key="ntfy_enabled",
        fallback=settings.ntfy_enabled,
    )
    discord_enabled = _form_checkbox_value(
        form_values,
        key="discord_enabled",
        fallback=settings.discord_enabled,
    )
    ntfy_server_url = escape(
        form_values.get("ntfy_server_url", settings.ntfy_server_url)
    )
    ntfy_topic = escape(form_values.get("ntfy_topic", settings.ntfy_topic or ""))
    discord_webhook_url = escape(
        form_values.get("discord_webhook_url", settings.discord_webhook_url or "")
    )
    error_html = (
        f'<p style="{_ERROR_STYLE}">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    flash_html = (
        f'<p style="{_SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    test_result_html = _render_notification_test_result_section(test_result_message)
    return _page_layout(
        title="全域通知設定",
        body=f"""
        <section style="display:grid;gap:24px;">
          <div>
            <a href="/" style="color:#0f766e;text-decoration:none;">← 回列表</a>
            <h1>全域通知設定</h1>
            <p>這裡設定通知要送到哪些通道；單一 watch 頁面只負責通知規則，不負責 webhook/topic。</p>
          </div>
          {error_html}
          {flash_html}
          {test_result_html}
          <form action="/settings/notifications" method="post" style="{_CARD_STYLE}">
            <label style="display:flex;gap:8px;align-items:center;">
              <input type="checkbox" name="desktop_enabled" {"checked" if desktop_enabled else ""}>
              啟用本機桌面通知
            </label>
            <label style="display:flex;gap:8px;align-items:center;">
              <input
                id="global-ntfy-enabled"
                type="checkbox"
                name="ntfy_enabled"
                {"checked" if ntfy_enabled else ""}
              >
              啟用 ntfy
            </label>
            <div
              id="global-ntfy-settings"
              style="{_channel_wrapper_style(ntfy_enabled)}"
            >
              <label>ntfy Server URL</label>
              <input
                type="text"
                name="ntfy_server_url"
                value="{ntfy_server_url}"
                placeholder="https://ntfy.sh"
                style="{_input_style()}"
              >
              <label>ntfy Topic</label>
              <input
                type="text"
                name="ntfy_topic"
                value="{ntfy_topic}"
                placeholder="例如 hotel-watch"
                style="{_input_style()}"
              >
            </div>
            <label style="display:flex;gap:8px;align-items:center;">
              <input
                id="global-discord-enabled"
                type="checkbox"
                name="discord_enabled"
                {"checked" if discord_enabled else ""}
              >
              啟用 Discord webhook
            </label>
            <div
              id="global-discord-settings"
              style="{_channel_wrapper_style(discord_enabled)}"
            >
              <label>Discord Webhook URL</label>
              <input
                type="text"
                name="discord_webhook_url"
                value="{discord_webhook_url}"
                placeholder="https://discord.com/api/webhooks/..."
                style="{_input_style()}"
              >
            </div>
            <button type="submit" style="{_primary_button_style()}">儲存全域通知設定</button>
          </form>
          <form action="/settings/notifications/test" method="post" style="{_CARD_STYLE}">
            <h2 style="margin:0;">測試通知</h2>
            <p style="margin:0;">
              會使用目前已保存的全域通知設定，走正式 notifier / dispatcher 路徑送出一則測試訊息。
            </p>
            <button type="submit" style="{_secondary_button_style()}">發送測試通知</button>
          </form>
          {_render_checkbox_toggle_script(
              checkbox_id="global-ntfy-enabled",
              wrapper_id="global-ntfy-settings",
          )}
          {_render_checkbox_toggle_script(
              checkbox_id="global-discord-enabled",
              wrapper_id="global-discord-settings",
          )}
        </section>
        """,
    )


def _render_preview_section(preview: WatchCreationPreview) -> str:
    """渲染候選方案與建立 watch item 的第二段表單。"""
    options = []
    for candidate in preview.candidate_bundle.candidates:
        checked = (
            'checked'
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
    <section style="{_CARD_STYLE}">
      <div>
        <h2>{escape(preview.candidate_bundle.hotel_name)}</h2>
        <p>日期：{preview.draft.check_in_date} - {preview.draft.check_out_date}</p>
        <p>人數 / 房數：{preview.draft.people_count} / {preview.draft.room_count}</p>
        {_render_preview_browser_source(preview)}
        <p style="color:{prefill_color};">{prefill_status}</p>
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
          style="{_input_style()}"
        >
        <label>通知條件</label>
        <select
          id="create-watch-notification-rule-kind"
          name="notification_rule_kind"
          style="{_input_style()}"
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
          <input type="text" name="target_price" placeholder="例如 20000" style="{_input_style()}">
          {_render_notification_target_price_hint(NotificationLeafKind.BELOW_TARGET_PRICE)}
        </div>
        <button type="submit" style="{_primary_button_style()}">建立 Watch Item</button>
      </form>
      {_render_notification_rule_toggle_script(
          select_id="create-watch-notification-rule-kind",
          wrapper_id="create-watch-target-price-wrapper",
      )}
    </section>
    """


def _render_preview_browser_source(preview: WatchCreationPreview) -> str:
    """渲染目前 preview 的瀏覽器來源分頁資訊。"""
    if preview.browser_tab_id is None:
        return ""
    title = preview.browser_tab_title or "untitled tab"
    return (
        f"<p>來源分頁：{escape(title)} "
        f"（tab id: {escape(preview.browser_tab_id)}）</p>"
    )


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
          <button type="submit" style="{_secondary_button_style()}">
            從同一個 Chrome 分頁重新抓取
          </button>
        </form>
        """
    return f"""
    <div style="display:grid;gap:12px;">
      <p style="margin:0;color:#4b635f;">
        若要以專用 Chrome 目前頁面為準重新抓取，請改用 Chrome 分頁選擇流程。
      </p>
      <a href="/watches/chrome-tabs" style="{_secondary_button_style()}">
        從目前專用 Chrome 頁面抓取
      </a>
    </div>
    """


def _render_diagnostics_section(diagnostics: tuple[LookupDiagnostic, ...]) -> str:
    """渲染 seed URL 預覽流程的診斷資訊。"""
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
              <td style="{_cell_style(head=False)}">{escape(diagnostic.stage)}</td>
              <td style="{_cell_style(head=False)}">{escape(diagnostic.status)}</td>
              <td style="{_cell_style(head=False)}">
                {escape(diagnostic.detail)} {escape(cooldown_text)}
              </td>
            </tr>
            """
        )

    return f"""
    <section style="{_CARD_STYLE}">
      <div>
        <h2>診斷資訊</h2>
        <p>顯示本次 preview 嘗試過的方法與各步驟結果。</p>
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr>
            <th style="{_cell_style(head=True)}">階段</th>
            <th style="{_cell_style(head=True)}">結果</th>
            <th style="{_cell_style(head=True)}">說明</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _render_candidate_price(*, candidate, preview: WatchCreationPreview) -> str:
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
            "<br><span style=\"color:#0f766e;\">"
            f"每人每晚：約 {escape(currency)} {escape(per_person_price_text)}"
            "</span>"
        )

    return (
        "<br><span style=\"color:#18322f;\">"
        f"總價：{total_price_html}"
        f"{per_person_html}"
        "</span>"
    )


def render_debug_capture_list_page(
    *,
    captures: tuple[DebugCaptureSummary, ...],
    flash_message: str | None = None,
) -> str:
    """渲染 preview debug capture 列表頁。"""
    rows = []
    for capture in captures:
        captured_at = _format_datetime_for_display(capture.captured_at_utc)
        latest_status = capture.diagnostics[-1].status if capture.diagnostics else "n/a"
        candidate_count = (
            str(capture.candidate_count)
            if capture.candidate_count is not None
            else "unknown"
        )
        rows.append(
            f"""
            <tr>
              <td style="{_cell_style(head=False)}">
                <a href="/debug/captures/{escape(capture.capture_id)}" style="color:#0f766e;">
                  {escape(capture.capture_id)}
                </a>
              </td>
              <td style="{_cell_style(head=False)}">{escape(captured_at)}</td>
              <td style="{_cell_style(head=False)}">{escape(capture.parsed_hotel_name)}</td>
              <td style="{_cell_style(head=False)}">{escape(candidate_count)}</td>
              <td style="{_cell_style(head=False)}">{escape(latest_status)}</td>
              <td style="{_cell_style(head=False)}">
                <code>{escape(capture.seed_url)}</code>
              </td>
            </tr>
            """
        )

    table_body = "\n".join(rows) or '<tr><td colspan="5">目前尚無 preview debug capture。</td></tr>'
    flash_html = (
        f'<p style="{_SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    return _page_layout(
        title="Debug Captures",
        body=f"""
        <section style="display:grid;gap:20px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;">
            <div>
              <a href="/" style="color:#0f766e;text-decoration:none;">← 回列表</a>
              <h1>Debug Captures</h1>
              <p>
                這裡只列出建立 watch / preview 流程保存的 capture，
                方便直接定位 parser 與 browser 問題。
              </p>
              <p>
                若要看背景輪詢期間的節流、blocked page、tab discard 等訊號，
                請到各 watch 詳細頁的 Debug Artifacts 區塊。
              </p>
            </div>
            <div style="display:flex;gap:12px;align-items:center;">
              <a href="/debug/captures/latest" style="{_primary_button_style()}">查看最新一筆</a>
              <form action="/debug/captures/clear" method="post" style="margin:0;">
                <button type="submit" style="{_danger_button_style()}">清空紀錄</button>
              </form>
            </div>
          </div>
          {flash_html}
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr>
                <th style="{_cell_style(head=True)}">Capture ID</th>
                <th style="{_cell_style(head=True)}">時間</th>
                <th style="{_cell_style(head=True)}">解析飯店名</th>
                <th style="{_cell_style(head=True)}">候選數</th>
                <th style="{_cell_style(head=True)}">最後狀態</th>
                <th style="{_cell_style(head=True)}">Seed URL</th>
              </tr>
            </thead>
            <tbody>{table_body}</tbody>
          </table>
        </section>
        """,
    )


def render_debug_capture_detail_page(
    *,
    capture: DebugCaptureDetail,
) -> str:
    """渲染單筆 preview debug capture 詳細內容頁。"""
    captured_at = _format_datetime_for_display(capture.summary.captured_at_utc)
    diagnostics_html = _render_diagnostics_section(capture.summary.diagnostics)
    html_preview = (
        escape(capture.html_content[:5000])
        if capture.html_content is not None
        else ""
    )
    return _page_layout(
        title=f"Debug Capture {capture.summary.capture_id}",
        body=f"""
        <section style="display:grid;gap:20px;">
          <div>
            <a href="/debug/captures" style="color:#0f766e;text-decoration:none;">← 回 captures</a>
            <h1>{escape(capture.summary.capture_id)}</h1>
            <p>時間：{escape(captured_at)}</p>
            <p>Capture 類型：{escape(capture.summary.capture_scope)}</p>
            <p>Seed URL：<code>{escape(capture.summary.seed_url)}</code></p>
            <p>解析飯店名：{escape(capture.summary.parsed_hotel_name)}</p>
            <p>
              HTML 檔案：
              <code>{escape(capture.summary.html_path or "未保存（成功摘要模式）")}</code>
            </p>
            <p>Metadata 檔案：<code>{escape(capture.summary.metadata_path)}</code></p>
            <p>這裡只顯示 preview capture；背景輪詢的 debug 訊號請到對應 watch 詳細頁查看。</p>
            {_render_capture_html_link(capture)}
          </div>
          {diagnostics_html}
          <section style="{_CARD_STYLE}">
            <h2>Metadata JSON</h2>
            <pre style="{_pre_style()}">{escape(capture.metadata_json)}</pre>
          </section>
          {_render_html_preview_section(html_preview, capture)}
        </section>
        """,
    )


def _render_latest_snapshot_section(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
) -> str:
    """渲染單一 watch item 的最近一次摘要與通知狀態。"""
    if latest_snapshot is None:
        return f"""
        <section style="{_CARD_STYLE}">
          <h2>最近摘要</h2>
          <p>目前尚無任何檢查結果。</p>
        </section>
        """

    runtime_signal_html = _render_runtime_signal_summary(debug_artifacts)
    latest_price = _format_optional_money(
        latest_snapshot.currency,
        latest_snapshot.normalized_price_amount,
    )
    last_notified_price = (
        _format_optional_money(
            latest_snapshot.currency,
            notification_state.last_notified_price,
        )
        if notification_state is not None
        else "unknown"
    )
    last_notified_availability = (
        notification_state.last_notified_availability.value
        if notification_state and notification_state.last_notified_availability
        else "none"
    )
    last_notified_at = (
        _format_datetime_for_display(notification_state.last_notified_at)
        if notification_state and notification_state.last_notified_at
        else "none"
    )
    return f"""
    <section style="{_CARD_STYLE}">
      <h2>最近摘要</h2>
      <p>最近檢查：{escape(_format_datetime_for_display(latest_snapshot.checked_at))}</p>
      <p>Availability：{escape(latest_snapshot.availability.value)}</p>
      <p>最近價格：{escape(latest_price)}</p>
      <p>連續失敗次數：{latest_snapshot.consecutive_failures}</p>
      <p>最後錯誤：{escape(latest_snapshot.last_error_code or "none")}</p>
      <p>目前是否 degraded：{"是" if latest_snapshot.is_degraded else "否"}</p>
      <p>最近通知價格：{escape(last_notified_price)}</p>
      <p>
        最近通知 availability：
        {escape(last_notified_availability)}
      </p>
      <p>
        最近通知時間：
        {escape(last_notified_at)}
      </p>
      <p>
        目前設定的通知規則：
        {escape(_describe_notification_rule(watch_item))}
      </p>
      {runtime_signal_html}
    </section>
    """


def _render_check_events_section(check_events: tuple[CheckEvent, ...]) -> str:
    """渲染檢查歷史與錯誤摘要。"""
    if not check_events:
        return f"""
        <section style="{_CARD_STYLE}">
          <h2>檢查歷史</h2>
          <p>目前尚無檢查歷史。</p>
        </section>
        """

    rows = []
    for event in sorted(check_events, key=lambda item: item.checked_at, reverse=True)[:20]:
        event_kind_text = ", ".join(event.event_kinds) or "checked"
        event_price_text = _format_optional_money(
            event.currency,
            event.normalized_price_amount,
        )
        rows.append(
            f"""
            <tr>
              <td style="{_cell_style(head=False)}">
                {escape(_format_datetime_for_display(event.checked_at))}
              </td>
              <td style="{_cell_style(head=False)}">{escape(event.availability.value)}</td>
              <td style="{_cell_style(head=False)}">{escape(event_kind_text)}</td>
              <td style="{_cell_style(head=False)}">{escape(event_price_text)}</td>
              <td style="{_cell_style(head=False)}">{escape(event.error_code or "none")}</td>
              <td style="{_cell_style(head=False)}">{escape(event.notification_status.value)}</td>
            </tr>
            """
        )

    return f"""
    <section style="{_CARD_STYLE}">
      <h2>檢查歷史</h2>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr>
            <th style="{_cell_style(head=True)}">時間</th>
            <th style="{_cell_style(head=True)}">Availability</th>
            <th style="{_cell_style(head=True)}">事件</th>
            <th style="{_cell_style(head=True)}">價格</th>
            <th style="{_cell_style(head=True)}">錯誤</th>
            <th style="{_cell_style(head=True)}">通知結果</th>
          </tr>
        </thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </section>
    """


def _render_debug_artifacts_section(debug_artifacts: tuple[DebugArtifact, ...]) -> str:
    """渲染與單一 watch item 關聯的 debug artifact 摘要。"""
    if not debug_artifacts:
        return f"""
        <section style="{_CARD_STYLE}">
          <h2>Debug Artifacts</h2>
          <p>目前尚無 background runtime debug artifact。</p>
          <p>若要看建立 watch / preview 過程的 debug capture，請到首頁的 Debug 區。</p>
        </section>
        """

    rows = []
    for artifact in debug_artifacts[:10]:
        http_status_text = (
            str(artifact.http_status) if artifact.http_status is not None else "none"
        )
        reason_text = _describe_debug_reason(artifact.reason)
        rows.append(
            f"""
            <tr>
              <td style="{_cell_style(head=False)}">
                {escape(_format_datetime_for_display(artifact.captured_at))}
              </td>
              <td style="{_cell_style(head=False)}">{escape(reason_text)}</td>
              <td style="{_cell_style(head=False)}">{escape(artifact.source_url or "none")}</td>
              <td style="{_cell_style(head=False)}">{escape(http_status_text)}</td>
            </tr>
            """
        )

    return f"""
    <section style="{_CARD_STYLE}">
      <h2>Debug Artifacts</h2>
      <p>
        這裡只顯示 background runtime 寫入的 debug artifact，
        例如節流、blocked page、tab discard。
      </p>
      <p>preview / parser 問題請到首頁的 Debug 區查看 preview captures。</p>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr>
            <th style="{_cell_style(head=True)}">時間</th>
            <th style="{_cell_style(head=True)}">原因</th>
            <th style="{_cell_style(head=True)}">來源 URL</th>
            <th style="{_cell_style(head=True)}">HTTP 狀態</th>
          </tr>
        </thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </section>
    """


def _render_runtime_signal_summary(debug_artifacts: tuple[DebugArtifact, ...]) -> str:
    """整理最近的 runtime 訊號，讓 watch 詳細頁可快速判讀背景狀態。"""
    if not debug_artifacts:
        return """
        <div style="padding:12px;border:1px solid #d7e2df;background:#f8fbfa;">
          <strong>最近 runtime 訊號：</strong> 目前沒有 blocked page、節流或 tab discard 紀錄。
        </div>
        """

    recent_artifacts = debug_artifacts[:10]
    counts: dict[str, int] = {}
    for artifact in recent_artifacts:
        counts[artifact.reason] = counts.get(artifact.reason, 0) + 1

    latest_artifact = recent_artifacts[0]
    latest_reason = _describe_debug_reason(latest_artifact.reason)
    latest_at = _format_datetime_for_display(latest_artifact.captured_at)
    summary_parts = [
        f"{_describe_debug_reason(reason)} {count} 次"
        for reason, count in sorted(counts.items())
    ]
    summary_text = "；".join(summary_parts)
    return f"""
    <div style="padding:12px;border:1px solid #d7e2df;background:#f8fbfa;">
      <strong>最近 runtime 訊號：</strong>
      最近一次為 {escape(latest_reason)}（{escape(latest_at)}）。
      <span>{escape(summary_text)}</span>
    </div>
    """


def _render_watch_action_controls(*, watch_item: WatchItem, show_check_now: bool) -> str:
    """依 watch 狀態渲染可用的啟用、暫停、停用與立即檢查操作。"""
    actions: list[str] = []
    if watch_item.enabled and watch_item.paused_reason is None:
        if show_check_now:
            actions.append(
                _render_watch_action_form(
                    watch_item_id=watch_item.id,
                    action="check-now",
                    label="立即檢查",
                    button_style=_primary_button_style(),
                )
            )
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="pause",
                label="暫停",
                button_style=_secondary_button_style(),
            )
        )
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="disable",
                label="停用",
                button_style=_secondary_button_style(),
            )
        )
    elif watch_item.enabled and watch_item.paused_reason is not None:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="resume",
                label="恢復",
                button_style=_primary_button_style(),
            )
        )
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="disable",
                label="停用",
                button_style=_secondary_button_style(),
            )
        )
    else:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="enable",
                label="啟用",
                button_style=_primary_button_style(),
            )
        )
    actions.append(
        _render_watch_action_form(
            watch_item_id=watch_item.id,
            action="delete",
            label="刪除",
            button_style=_danger_button_style(),
        )
    )
    return '<div style="display:flex;gap:8px;flex-wrap:wrap;">' + "".join(actions) + "</div>"


def _render_watch_action_form(
    *,
    watch_item_id: str,
    action: str,
    label: str,
    button_style: str,
) -> str:
    """渲染單一 watch 操作按鈕表單。"""
    return f"""
    <form
      action="/watches/{escape(watch_item_id)}/{escape(action)}"
      method="post"
      style="margin:0;"
    >
      <button type="submit" style="{button_style}">{escape(label)}</button>
    </form>
    """


def _describe_watch_status(watch_item: WatchItem) -> str:
    """把 watch 的啟用與暫停狀態整理成較易讀的文字。"""
    if not watch_item.enabled:
        return "停用"
    if watch_item.paused_reason is not None:
        return "暫停"
    return "啟用"


def _page_layout(*, title: str, body: str) -> str:
    """輸出 GUI 共用頁面框架。"""
    return f"""
    <!doctype html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
      </head>
      <body style="{_BODY_STYLE}">
        <main style="max-width:980px;margin:0 auto;padding:32px 20px 64px;">
          {body}
        </main>
      </body>
    </html>
    """


def _primary_button_style() -> str:
    """回傳主要按鈕的 inline style。"""
    return (
        "display:inline-block;padding:12px 18px;background:#0f766e;color:#fff;"
        "text-decoration:none;border:none;border-radius:8px;cursor:pointer;"
    )


def _secondary_button_style() -> str:
    """回傳次要按鈕的 inline style。"""
    return (
        "display:inline-block;padding:12px 18px;background:#dff2ed;color:#0f766e;"
        "text-decoration:none;border:1px solid #9fd3c7;border-radius:8px;cursor:pointer;"
    )


def _danger_button_style() -> str:
    """回傳刪除操作按鈕的 inline style。"""
    return (
        "display:inline-block;padding:8px 12px;background:#fff3f3;color:#9f1239;"
        "border:1px solid #f1aeb5;border-radius:8px;cursor:pointer;"
    )


def _input_style() -> str:
    """回傳輸入元件的 inline style。"""
    return (
        "width:100%;padding:10px 12px;border:1px solid #b8cbc7;border-radius:8px;"
        "background:#fff;box-sizing:border-box;"
    )


def _cell_style(*, head: bool) -> str:
    """回傳列表頁表格儲存格的 inline style。"""
    background = "#dff2ed" if head else "#fff"
    return f"padding:10px 12px;border:1px solid #d7e2df;text-align:left;background:{background};"


def _pre_style() -> str:
    """回傳 debug 區 `pre` 區塊的 inline style。"""
    return (
        "margin:0;padding:12px;background:#0f172a;color:#e2e8f0;overflow:auto;"
        "white-space:pre-wrap;word-break:break-word;border-radius:8px;"
    )


def _render_capture_html_link(capture: DebugCaptureDetail) -> str:
    """依 capture 是否有保存 HTML，決定是否顯示完整 HTML 連結。"""
    if capture.summary.html_path is None:
        return "<p>本次為成功摘要紀錄，未保存完整 HTML。</p>"
    return f"""
    <p>
      <a
        href="/debug/captures/{escape(capture.summary.capture_id)}/html"
        style="color:#0f766e;"
      >
        查看完整 HTML
      </a>
    </p>
    """


def _render_html_preview_section(html_preview: str, capture: DebugCaptureDetail) -> str:
    """依 capture 是否有保存 HTML，決定是否顯示 HTML 摘要區塊。"""
    if capture.html_content is None:
        return f"""
        <section style="{_CARD_STYLE}">
          <h2>HTML 內容</h2>
          <p>本次僅保存成功摘要，未額外保存完整 HTML。</p>
        </section>
        """
    return f"""
    <section style="{_CARD_STYLE}">
      <h2>HTML 前 5000 字</h2>
      <pre style="{_pre_style()}">{html_preview}</pre>
    </section>
    """


def _format_decimal_for_display(amount) -> str:
    """把 Decimal 數字格式化成較適合 GUI 顯示的文字。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")


def _format_datetime_for_display(value: datetime | None) -> str:
    """將 aware datetime 轉成使用者電腦目前的本地時間格式。"""
    if value is None:
        return "none"
    return value.astimezone().strftime("%Y/%m/%d %H:%M")


def _format_optional_money(currency: str | None, amount: Decimal | None) -> str:
    """把可選價格欄位整理成較易讀的文字。"""
    if amount is None:
        return "none"
    amount_text = _format_decimal_for_display(amount)
    return f"{currency or ''} {amount_text}".strip()


def _describe_notification_rule(watch_item: WatchItem) -> str:
    """把 V1 單規則通知條件整理成摘要文字。"""
    rule = watch_item.notification_rule
    if getattr(rule, "kind", None) == NotificationLeafKind.ANY_DROP:
        return "價格下降"
    target_price = getattr(rule, "target_price", None)
    if getattr(rule, "kind", None) == NotificationLeafKind.BELOW_TARGET_PRICE:
        return f"低於目標價 {target_price}" if target_price is not None else "低於目標價"
    return "複合規則"


def _format_focus_text(has_focus: bool | None) -> str:
    """把分頁焦點狀態整理成較易讀的文字。"""
    if has_focus is True:
        return "focused"
    if has_focus is False:
        return "not_focused"
    return "unknown"


def _describe_debug_reason(reason: str) -> str:
    """把 runtime debug artifact 的原因轉成較易讀的中文。"""
    mapping = {
        "possible_throttling": "可能節流",
        "page_was_discarded": "分頁曾被瀏覽器丟棄",
        "http_403": "站方阻擋頁 / 403",
        "parse_failed": "解析失敗",
        "target_missing": "目標房型方案消失",
        "network_timeout": "網路逾時",
        "network_error": "網路錯誤",
    }
    return mapping.get(reason, reason)


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


def _render_notification_test_result_section(test_result_message: str | None) -> str:
    """把測試通知結果整理成較易讀的摘要區塊。"""
    if not test_result_message:
        return ""

    sent_text = _extract_test_result_segment(test_result_message, "sent")
    throttled_text = _extract_test_result_segment(test_result_message, "throttled")
    failed_text = _extract_test_result_segment(test_result_message, "failed")
    details_text = _extract_test_result_segment(test_result_message, "details")
    return f"""
    <section style="{_CARD_STYLE}">
      <h2 style="margin:0;">測試通知結果</h2>
      <p style="margin:0;">成功通道：{escape(sent_text or "none")}</p>
      <p style="margin:0;">節流通道：{escape(throttled_text or "none")}</p>
      <p style="margin:0;">失敗通道：{escape(failed_text or "none")}</p>
      <p style="margin:0;">失敗原因：{escape(details_text or "none")}</p>
    </section>
    """


def _extract_test_result_segment(message: str, key: str) -> str:
    """從 redirect 的測試通知摘要中取出指定欄位內容。"""
    marker = f"{key}="
    if marker not in message:
        return ""

    suffix = message.split(marker, 1)[1]
    for separator in ("；", ";"):
        if separator in suffix:
            return suffix.split(separator, 1)[0].strip()
    return suffix.strip()


def _notification_target_price_wrapper_style(kind: NotificationLeafKind) -> str:
    """依通知規則回傳目標價欄位容器的顯示樣式。"""
    display = "none" if kind is NotificationLeafKind.ANY_DROP else "grid"
    return f"display:{display};gap:8px;"


def _channel_wrapper_style(enabled: bool) -> str:
    """依通道是否啟用回傳設定區塊的顯示樣式。"""
    display = "grid" if enabled else "none"
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


def _render_checkbox_toggle_script(*, checkbox_id: str, wrapper_id: str) -> str:
    """渲染 checkbox 切換腳本，用於控制通道設定區塊顯示。"""
    return f"""
    <script>
      (() => {{
        const checkbox = document.getElementById("{escape(checkbox_id)}");
        const wrapper = document.getElementById("{escape(wrapper_id)}");
        if (!checkbox || !wrapper) {{
          return;
        }}

        const syncVisibility = () => {{
          wrapper.style.display = checkbox.checked ? "grid" : "none";
        }};

        syncVisibility();
        checkbox.addEventListener("change", syncVisibility);
      }})();
    </script>
    """


def _form_checkbox_value(
    form_values: dict[str, str],
    *,
    key: str,
    fallback: bool,
) -> bool:
    """依表單回填資料或既有設定決定 checkbox 是否勾選。"""
    if key not in form_values:
        return fallback
    return form_values[key] == "on"
