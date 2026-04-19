"""debug capture 頁面的 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.application.debug_captures import DebugCaptureDetail, DebugCaptureSummary
from app.sites.base import LookupDiagnostic
from app.web.view_helpers import (
    CARD_STYLE,
    SUCCESS_STYLE,
    cell_style,
    danger_button_style,
    format_datetime_for_display,
    page_layout,
    pre_style,
    primary_button_style,
)


def render_debug_capture_list_page(
    *,
    captures: tuple[DebugCaptureSummary, ...],
    flash_message: str | None = None,
) -> str:
    """渲染 preview debug capture 列表頁。"""
    rows = []
    for capture in captures:
        captured_at = format_datetime_for_display(capture.captured_at_utc)
        latest_status = capture.diagnostics[-1].status if capture.diagnostics else "n/a"
        candidate_count = (
            str(capture.candidate_count)
            if capture.candidate_count is not None
            else "unknown"
        )
        rows.append(
            f"""
            <tr>
              <td style="{cell_style(head=False)}">
                <a href="/debug/captures/{escape(capture.capture_id)}" style="color:#0f766e;">
                  {escape(capture.capture_id)}
                </a>
              </td>
              <td style="{cell_style(head=False)}">{escape(captured_at)}</td>
              <td style="{cell_style(head=False)}">{escape(capture.parsed_hotel_name)}</td>
              <td style="{cell_style(head=False)}">{escape(candidate_count)}</td>
              <td style="{cell_style(head=False)}">{escape(latest_status)}</td>
              <td style="{cell_style(head=False)}">
                <code>{escape(capture.seed_url)}</code>
              </td>
            </tr>
            """
        )

    table_body = "\n".join(rows) or '<tr><td colspan="5">目前尚無 preview debug capture。</td></tr>'
    flash_html = (
        f'<p style="{SUCCESS_STYLE}">{escape(flash_message)}</p>'
        if flash_message
        else ""
    )
    return page_layout(
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
              <a href="/debug/captures/latest" style="{primary_button_style()}">查看最新一筆</a>
              <form action="/debug/captures/clear" method="post" style="margin:0;">
                <button type="submit" style="{danger_button_style()}">清空紀錄</button>
              </form>
            </div>
          </div>
          {flash_html}
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr>
                <th style="{cell_style(head=True)}">Capture ID</th>
                <th style="{cell_style(head=True)}">時間</th>
                <th style="{cell_style(head=True)}">解析飯店名</th>
                <th style="{cell_style(head=True)}">候選數</th>
                <th style="{cell_style(head=True)}">最後狀態</th>
                <th style="{cell_style(head=True)}">Seed URL</th>
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
    captured_at = format_datetime_for_display(capture.summary.captured_at_utc)
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
          <section style="{CARD_STYLE}">
            <h2>Metadata JSON</h2>
            <pre style="{pre_style()}">{escape(capture.metadata_json)}</pre>
          </section>
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
        <section style="{CARD_STYLE}">
          <h2>HTML 內容</h2>
          <p>本次僅保存成功摘要，未額外保存完整 HTML。</p>
        </section>
        """
    return f"""
    <section style="{CARD_STYLE}">
      <h2>HTML 前 5000 字</h2>
      <pre style="{pre_style()}">{html_preview}</pre>
    </section>
    """
