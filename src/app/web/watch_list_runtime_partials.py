"""Dashboard runtime status dock partial renderer。"""

from __future__ import annotations

from html import escape

from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import icon_svg
from app.web.ui_styles import color_token, muted_text_style, surface_card_style
from app.web.watch_list_presenters import (
    RuntimeStatusItemPresentation,
    RuntimeStatusPresentation,
    build_runtime_status_presentation,
)


def render_runtime_status_section(runtime_status: MonitorRuntimeStatus | None) -> str:
    """在首頁顯示 background monitor runtime 的狀態摘要。"""
    return render_runtime_status_section_with_time_format(
        runtime_status,
        use_24_hour_time=True,
    )


def render_runtime_status_section_with_time_format(
    runtime_status: MonitorRuntimeStatus | None,
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染 background monitor runtime 的狀態摘要。"""
    presentation = build_runtime_status_presentation(
        runtime_status,
        use_24_hour_time=use_24_hour_time,
    )
    return render_runtime_status_section_from_presentation(presentation)


def render_runtime_status_section_from_presentation(
    presentation: RuntimeStatusPresentation | None,
) -> str:
    """依 runtime presentation 渲染首頁系統狀態列。"""
    if presentation is None:
        return ""
    items_html = "".join(
        _render_runtime_status_item(item) for item in presentation.items
    )
    return f"""
    <section
      class="runtime-status-dock"
      data-runtime-status-dock
      style="{surface_card_style(gap="0", padding="0")}"
    >
      <div
        class="runtime-status-header"
        style="
          display:flex;align-items:center;justify-content:space-between;gap:12px;
          padding:14px 18px;border-bottom:1px solid {color_token("border")};
        "
      >
        <h2 style="margin:0;font-size:18px;">系統狀態</h2>
        <button
          type="button"
          data-runtime-status-toggle
          aria-label="收合系統狀態"
          aria-expanded="true"
          style="
            width:28px;height:28px;display:grid;place-items:center;padding:0;
            border:1px solid {color_token("border")};border-radius:999px;
            background:{color_token("surface")};color:{color_token("secondary")};
            cursor:pointer;font-weight:800;line-height:1;
          "
        >
          <span data-runtime-expanded-icon>{icon_svg("chevron-down", size=16)}</span>
          <span data-runtime-collapsed-icon style="display:none;">
            {icon_svg("chevron-up", size=16)}
          </span>
        </button>
      </div>
      <div
        class="runtime-status-panel"
        style="
          display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;
          align-items:center;padding:16px 18px;
        "
      >
        {items_html}
        <div style="display:flex;justify-content:flex-end;">
          <a
            href="{escape(presentation.action.href)}"
            title="{escape(presentation.action.title)}"
            style="
              display:inline-flex;align-items:center;gap:8px;padding:10px 14px;
              border:1px solid {color_token("border")};border-radius:8px;
              color:{color_token("primary")};text-decoration:none;font-weight:700;
              background:{color_token("surface")};
            "
          >
            {escape(presentation.action.label)} <span aria-hidden="true">›</span>
          </a>
        </div>
      </div>
    </section>
    """


def _render_runtime_status_item(
    presentation: RuntimeStatusItemPresentation,
) -> str:
    """渲染系統狀態橫向列的單一狀態項目。"""
    return f"""
    <div
      style="
        display:flex;align-items:center;gap:12px;min-width:0;
        padding:4px 18px 4px 0;border-right:1px solid {color_token("border")};
      "
    >
      <span aria-hidden="true" style="{_runtime_status_icon_style(presentation.icon_kind)}">
        {icon_svg(presentation.icon_name, size=24)}
      </span>
      <span style="display:grid;gap:2px;min-width:0;">
        <span style="{muted_text_style(font_size="13px")}">{escape(presentation.label)}</span>
        <strong style="font-size:15px;color:{color_token("secondary")};">
          {escape(presentation.value)}
        </strong>
      </span>
    </div>
    """


def _runtime_status_icon_style(kind: str) -> str:
    """依 runtime 狀態語意回傳圓形 icon 樣式。"""
    palettes = {
        "success": ("#e8f7ef", "#15935f"),
        "warning": ("#fff3d8", "#d97706"),
    }
    background, color = palettes.get(kind, palettes["success"])
    return (
        "width:42px;height:42px;display:grid;place-items:center;border-radius:999px;"
        f"background:{background};color:{color};"
    )
