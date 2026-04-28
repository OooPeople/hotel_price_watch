"""debug capture 頁面的 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.application.debug_captures import DebugCaptureDetail, DebugCaptureSummary
from app.web.debug_presenters import (
    DebugCaptureDetailPresentation,
    DebugCaptureListPresentation,
    DebugDiagnosticRowPresentation,
    build_debug_capture_detail_presentation,
    build_debug_capture_list_presentation,
)
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


def render_debug_capture_list_page(
    *,
    captures: tuple[DebugCaptureSummary, ...],
    flash_message: str | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染 preview debug capture 列表頁。"""
    presentation = build_debug_capture_list_presentation(
        captures=captures,
        flash_message=flash_message,
        use_24_hour_time=use_24_hour_time,
    )
    return render_debug_capture_list_page_from_presentation(presentation)


def render_debug_capture_list_page_from_presentation(
    presentation: DebugCaptureListPresentation,
) -> str:
    """依 debug capture 列表 presentation 渲染列表頁。"""
    rows = []
    for row in presentation.rows:
        rows.append(
            table_row(
                (
                    text_link(
                        href=f"/debug/captures/{row.capture_id}",
                        label=row.capture_id,
                    ),
                    escape(row.captured_at_text),
                    escape(row.parsed_hotel_name),
                    escape(row.candidate_count_text),
                    status_badge(
                        label=row.latest_status_badge.label,
                        kind=row.latest_status_badge.kind,
                    ),
                    f"<code>{escape(row.seed_url)}</code>",
                )
            )
        )

    table_body = "\n".join(rows) or '<tr><td colspan="6">目前尚無 preview debug capture。</td></tr>'
    flash_html = render_flash_message(presentation.flash_message)
    summary_html = _render_capture_list_summary(presentation)
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
    presentation = build_debug_capture_detail_presentation(
        capture=capture,
        use_24_hour_time=use_24_hour_time,
    )
    return render_debug_capture_detail_page_from_presentation(presentation)


def render_debug_capture_detail_page_from_presentation(
    presentation: DebugCaptureDetailPresentation,
) -> str:
    """依單筆 debug capture presentation 渲染詳情頁。"""
    diagnostics_html = _render_diagnostics_section(presentation.diagnostic_rows)
    detail_subtitle = (
        "這裡只顯示 preview capture；"
        "背景輪詢的 debug 訊號請到對應監視詳情頁查看。"
    )
    return page_layout(
        title=f"進階診斷 - {presentation.capture_id}",
        body=f"""
        <section style="{stack_style(gap="xl")}">
          {page_header(
              title="Capture 詳情",
              subtitle=detail_subtitle,
              back_href="/debug/captures",
              back_label="回 captures",
              actions_html=_render_capture_html_link(presentation),
          )}
          {_render_capture_detail_summary(presentation)}
          {diagnostics_html}
          {collapsible_section(
              title="Metadata JSON",
              body=f'<pre style="{pre_style()}">{escape(presentation.metadata_json)}</pre>',
          )}
          {_render_html_preview_section(presentation)}
        </section>
        """,
    )


def _render_diagnostics_section(
    diagnostics: tuple[DebugDiagnosticRowPresentation, ...],
) -> str:
    """渲染 preview debug capture 使用的診斷資訊區塊。"""
    if not diagnostics:
        return ""

    rows = []
    for diagnostic in diagnostics:
        rows.append(
            table_row(
                (
                    escape(diagnostic.stage),
                    escape(diagnostic.status),
                    escape(diagnostic.detail_text),
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


def _render_capture_list_summary(
    presentation: DebugCaptureListPresentation,
) -> str:
    """渲染 debug capture 列表頁摘要卡。"""
    latest_status_badge = status_badge(
        label=presentation.latest_status_badge.label,
        kind=presentation.latest_status_badge.kind,
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {card(
          body=f'''
          <span style="{meta_label_style(display="inline")}">Capture 總數</span>
          <strong style="{summary_value_style()}">{presentation.total_count}</strong>
          ''',
      )}
      {card(
          body=f'''
          <span style="{meta_label_style(display="inline")}">候選總數</span>
          <strong style="{summary_value_style()}">{presentation.candidate_total}</strong>
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
    presentation: DebugCaptureDetailPresentation,
) -> str:
    """渲染單筆 capture 的重點摘要，降低 raw metadata 的首屏權重。"""
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return card(
        title=escape(presentation.capture_id),
        body=f"""
        <div style="{summary_grid_style}">
          <div>
            <span style="{meta_label_style()}">時間</span>
            <strong>{escape(presentation.captured_at_text)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">Capture 類型</span>
            <strong>{escape(presentation.capture_scope)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">解析飯店名</span>
            <strong>{escape(presentation.parsed_hotel_name)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">最後狀態</span>
            {status_badge(
                label=presentation.latest_status_badge.label,
                kind=presentation.latest_status_badge.kind,
            )}
          </div>
        </div>
        <p>Seed URL：<code>{escape(presentation.seed_url)}</code></p>
        <p>
          HTML 檔案：
          <code>{escape(presentation.html_path_text)}</code>
        </p>
        <p>Metadata 檔案：<code>{escape(presentation.metadata_path)}</code></p>
        """,
    )


def _render_capture_html_link(presentation: DebugCaptureDetailPresentation) -> str:
    """依 capture 是否有保存 HTML，決定是否顯示完整 HTML 連結。"""
    if presentation.html_link_href is None:
        return "<p>本次為成功摘要紀錄，未保存完整 HTML。</p>"
    return (
        "<p>"
        + text_link(
            href=presentation.html_link_href,
            label="查看完整 HTML",
        )
        + "</p>"
    )


def _render_html_preview_section(
    presentation: DebugCaptureDetailPresentation,
) -> str:
    """依 capture 是否有保存 HTML，決定是否顯示 HTML 摘要區塊。"""
    if not presentation.has_html:
        return empty_state_card(
            title="HTML 內容",
            message="本次僅保存成功摘要，未額外保存完整 HTML。",
        )
    return collapsible_section(
        title="HTML 前 5000 字",
        body=f'<pre style="{pre_style()}">{escape(presentation.html_preview)}</pre>',
    )
