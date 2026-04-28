"""頁面級 layout pattern helper，避免 partial 重複堆 inline style。"""

from __future__ import annotations

from html import escape

from app.web.ui_styles import (
    SPACING,
    input_style,
    responsive_grid_style,
    stack_style,
    surface_card_style,
)


def page_stack(body: str, *, gap: str = "xl") -> str:
    """渲染頁面主內容垂直堆疊容器。"""
    return f'<section style="{stack_style(gap=gap)}">{body}</section>'


def responsive_section_grid(
    body: str,
    *,
    min_width: str = "180px",
    gap: str = "14px",
) -> str:
    """渲染頁面區塊常用的 responsive grid。"""
    style = responsive_grid_style(min_width=min_width, gap=gap)
    return f'<section style="{style}">{body}</section>'


def inline_cluster(body: str, *, gap: str = "md", align: str = "center") -> str:
    """渲染可換行的水平控制群組。"""
    return (
        f'<div style="display:flex;gap:{SPACING[gap]};'
        f'align-items:{align};flex-wrap:wrap;">{body}</div>'
    )


def checkbox_label(*, input_html: str, label: str) -> str:
    """渲染 checkbox 與文字同列的標準 label。"""
    return (
        '<label style="display:flex;gap:8px;align-items:center;">'
        f"{input_html}{escape(label)}</label>"
    )


def details_panel(*, title: str, body: str, open_by_default: bool = True) -> str:
    """渲染設定或診斷頁常用的 details panel。"""
    open_attr = " open" if open_by_default else ""
    return f"""
    <details{open_attr} style="{surface_card_style(gap="12px", padding="16px")}">
      <summary style="cursor:pointer;font-weight:700;">{escape(title)}</summary>
      <div style="{stack_style(gap="md")}margin-top:12px;">
        {body}
      </div>
    </details>
    """


def field_stack(body: str, *, visible: bool = True) -> str:
    """渲染表單欄位群組，並可依初始狀態隱藏。"""
    return f'<div style="{field_stack_style(visible=visible)}">{body}</div>'


def field_stack_style(*, visible: bool = True) -> str:
    """回傳表單欄位群組樣式，供需要固定 DOM id 的容器使用。"""
    display = "grid" if visible else "none"
    return f"display:{display};gap:8px;"


def text_input(
    *,
    name: str,
    value: str,
    placeholder: str,
    input_type: str = "text",
) -> str:
    """渲染共用文字輸入欄位。"""
    return (
        f'<input type="{escape(input_type)}" name="{escape(name)}" '
        f'value="{escape(value)}" placeholder="{escape(placeholder)}" '
        f'style="{input_style()}">'
    )
