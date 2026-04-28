"""watch creation preview 診斷資訊 partial renderer。"""

from __future__ import annotations

from html import escape

from app.sites.base import LookupDiagnostic
from app.web.ui_components import collapsible_section, data_table, table_row
from app.web.ui_styles import section_title_style


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
