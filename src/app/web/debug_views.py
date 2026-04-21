"""debug capture 頁面的 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.application.debug_captures import DebugCaptureDetail, DebugCaptureSummary
from app.sites.base import LookupDiagnostic
from app.web.ui_components import (
    card,
    data_table,
    empty_state_card,
    link_button,
    page_layout,
    submit_button,
    table_row,
    text_link,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.ui_styles import (
    pre_style,
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
    return page_layout(
        title="Debug Captures",
        body=f"""
        <section style="display:grid;gap:20px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;">
            <div>
              {text_link(href="/", label="← 回列表")}
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
              {link_button(href="/debug/captures/latest", label="查看最新一筆", kind="primary")}
              <form action="/debug/captures/clear" method="post" style="margin:0;">
                {submit_button(label="清空紀錄", kind="danger")}
              </form>
            </div>
          </div>
          {flash_html}
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
    html_preview = (
        escape(capture.html_content[:5000])
        if capture.html_content is not None
        else ""
    )
    return page_layout(
        title=f"Debug Capture {capture.summary.capture_id}",
        body=f"""
        <section style="display:grid;gap:20px;">
          <div>
            {text_link(href="/debug/captures", label="← 回 captures")}
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
          {card(
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
    return card(
        title="HTML 前 5000 字",
        body=f'<pre style="{pre_style()}">{html_preview}</pre>',
    )
