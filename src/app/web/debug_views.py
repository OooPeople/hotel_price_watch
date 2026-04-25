"""debug capture 頁面的 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.application.debug_captures import DebugCaptureDetail, DebugCaptureSummary
from app.sites.base import LookupDiagnostic
from app.web.ui_components import (
    card,
    collapsible_section,
    data_table,
    empty_state_card,
    link_button,
    page_header,
    page_layout,
    section_header,
    status_badge,
    submit_button,
    table_row,
    text_link,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.ui_styles import (
    meta_label_style,
    meta_paragraph_style,
    pre_style,
    responsive_grid_style,
    stack_style,
    summary_value_style,
)
from app.web.view_formatters import format_datetime_for_display


def render_debug_capture_list_page(
    *,
    captures: tuple[DebugCaptureSummary, ...],
    flash_message: str | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染 preview debug capture 列表頁。"""
    rows = []
    for capture in captures:
        captured_at = format_datetime_for_display(
            capture.captured_at_utc,
            use_24_hour_time=use_24_hour_time,
        )
        latest_status = capture.diagnostics[-1].status if capture.diagnostics else "n/a"
        candidate_count = (
            str(capture.candidate_count)
            if capture.candidate_count is not None
            else "unknown"
        )
        rows.append(
            table_row(
                (
                    text_link(
                        href=f"/debug/captures/{capture.capture_id}",
                        label=capture.capture_id,
                    ),
                    escape(captured_at),
                    escape(capture.parsed_hotel_name),
                    escape(candidate_count),
                    escape(latest_status),
                    f"<code>{escape(capture.seed_url)}</code>",
                )
            )
        )

    table_body = "\n".join(rows) or '<tr><td colspan="6">目前尚無 preview debug capture。</td></tr>'
    flash_html = render_flash_message(flash_message)
    summary_html = _render_capture_list_summary(captures)
    capture_list_subtitle = "依時間排序的抓取紀錄與 parser 診斷入口。"
    return page_layout(
        title="進階診斷",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="進階診斷",
              subtitle=(
                  "這裡只列出建立監視 / preview 流程保存的 capture，"
                  "方便直接定位 parser 與 browser 問題。"
              ),
              back_href="/",
              back_label="回列表",
              actions_html=(
                  '<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">'
                  + link_button(href="/debug/captures/latest", label="查看最新一筆", kind="primary")
                  + '<form action="/debug/captures/clear" method="post" style="margin:0;">'
                  + submit_button(label="清空紀錄", kind="danger")
                  + "</form></div>"
              ),
          )}
          {card(
              body=f'''
              <p style="{meta_paragraph_style()}">
                若要看背景輪詢期間的節流、blocked page、tab discard 等訊號，
                請到各監視詳情頁的進階診斷區塊。
              </p>
              ''',
          )}
          {flash_html}
          {summary_html}
          {section_header(title="Preview Captures", subtitle=capture_list_subtitle)}
          {data_table(
              headers=("Capture ID", "時間", "解析飯店名", "候選數", "最後狀態", "Seed URL"),
              rows_html=table_body,
          )}
        </section>
        """,
    )


def render_debug_capture_detail_page(
    *,
    capture: DebugCaptureDetail,
    use_24_hour_time: bool = True,
) -> str:
    """渲染單筆 preview debug capture 詳細內容頁。"""
    captured_at = format_datetime_for_display(
        capture.summary.captured_at_utc,
        use_24_hour_time=use_24_hour_time,
    )
    diagnostics_html = _render_diagnostics_section(capture.summary.diagnostics)
    detail_subtitle = (
        "這裡只顯示 preview capture；"
        "背景輪詢的 debug 訊號請到對應監視詳情頁查看。"
    )
    html_preview = (
        escape(capture.html_content[:5000])
        if capture.html_content is not None
        else ""
    )
    return page_layout(
        title=f"進階診斷 - {capture.summary.capture_id}",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="Capture 詳情",
              subtitle=detail_subtitle,
              back_href="/debug/captures",
              back_label="回 captures",
              actions_html=_render_capture_html_link(capture),
          )}
          {_render_capture_detail_summary(capture, captured_at)}
          {diagnostics_html}
          {collapsible_section(
              title="Metadata JSON",
              body=f'<pre style="{pre_style()}">{escape(capture.metadata_json)}</pre>',
          )}
          {_render_html_preview_section(html_preview, capture)}
        </section>
        """,
    )


def _render_diagnostics_section(diagnostics: tuple[LookupDiagnostic, ...]) -> str:
    """渲染 preview debug capture 使用的診斷資訊區塊。"""
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

    return card(
        title="診斷資訊",
        body=f"""
        <p>顯示本次 preview 嘗試過的方法與各步驟結果。</p>
        {data_table(
            headers=("階段", "結果", "說明"),
            rows_html="".join(rows),
        )}
        """,
    )


def _render_capture_list_summary(captures: tuple[DebugCaptureSummary, ...]) -> str:
    """渲染 debug capture 列表頁摘要卡。"""
    latest_status = "n/a"
    if captures and captures[0].diagnostics:
        latest_status = captures[0].diagnostics[-1].status
    latest_status_badge = status_badge(
        label=latest_status,
        kind=_diagnostic_status_badge_kind(latest_status),
    )
    candidate_total = sum(
        capture.candidate_count or 0
        for capture in captures
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {card(
          body=f'''
          <span style="{meta_label_style(display="inline")}">Capture 總數</span>
          <strong style="{summary_value_style()}">{len(captures)}</strong>
          ''',
      )}
      {card(
          body=f'''
          <span style="{meta_label_style(display="inline")}">候選總數</span>
          <strong style="{summary_value_style()}">{candidate_total}</strong>
          ''',
      )}
      {card(
          body=f'''
          <span style="{meta_label_style(display="inline")}">最新狀態</span>
          <div>{latest_status_badge}</div>
          ''',
      )}
    </section>
    """


def _render_capture_detail_summary(
    capture: DebugCaptureDetail,
    captured_at: str,
) -> str:
    """渲染單筆 capture 的重點摘要，降低 raw metadata 的首屏權重。"""
    latest_status = (
        capture.summary.diagnostics[-1].status
        if capture.summary.diagnostics
        else "n/a"
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return card(
        title=escape(capture.summary.capture_id),
        body=f"""
        <div style="{summary_grid_style}">
          <div>
            <span style="{meta_label_style()}">時間</span>
            <strong>{escape(captured_at)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">Capture 類型</span>
            <strong>{escape(capture.summary.capture_scope)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">解析飯店名</span>
            <strong>{escape(capture.summary.parsed_hotel_name)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">最後狀態</span>
            {status_badge(
                label=latest_status,
                kind=_diagnostic_status_badge_kind(latest_status),
            )}
          </div>
        </div>
        <p>Seed URL：<code>{escape(capture.summary.seed_url)}</code></p>
        <p>
          HTML 檔案：
          <code>{escape(capture.summary.html_path or "未保存（成功摘要模式）")}</code>
        </p>
        <p>Metadata 檔案：<code>{escape(capture.summary.metadata_path)}</code></p>
        """,
    )


def _render_capture_html_link(capture: DebugCaptureDetail) -> str:
    """依 capture 是否有保存 HTML，決定是否顯示完整 HTML 連結。"""
    if capture.summary.html_path is None:
        return "<p>本次為成功摘要紀錄，未保存完整 HTML。</p>"
    return (
        "<p>"
        + text_link(
            href=f"/debug/captures/{capture.summary.capture_id}/html",
            label="查看完整 HTML",
        )
        + "</p>"
    )


def _render_html_preview_section(html_preview: str, capture: DebugCaptureDetail) -> str:
    """依 capture 是否有保存 HTML，決定是否顯示 HTML 摘要區塊。"""
    if capture.html_content is None:
        return empty_state_card(
            title="HTML 內容",
            message="本次僅保存成功摘要，未額外保存完整 HTML。",
        )
    return collapsible_section(
        title="HTML 前 5000 字",
        body=f'<pre style="{pre_style()}">{html_preview}</pre>',
    )


def _diagnostic_status_badge_kind(status: str) -> str:
    """依 diagnostic status 粗略決定 badge 語意。"""
    if status == "success":
        return "success"
    if "error" in status or "failed" in status or "403" in status:
        return "danger"
    if "empty" in status or "waiting" in status or "cooldown" in status:
        return "warning"
    return "muted"
