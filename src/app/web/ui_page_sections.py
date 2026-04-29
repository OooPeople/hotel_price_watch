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
    return f'<div style="{cluster_style(gap=gap, align=align)}">{body}</div>'


def two_column_grid_style(
    *,
    left: str,
    right: str,
    gap: str = "lg",
    align: str = "start",
) -> str:
    """回傳兩欄 responsive 區塊常用的 grid 樣式。"""
    return (
        f"display:grid;grid-template-columns:{left} {right};"
        f"gap:{SPACING[gap]};align-items:{align};"
    )


def equal_columns_grid_style(*, columns: int, gap: str = "lg") -> str:
    """回傳固定欄數且等寬的 grid 樣式。"""
    return (
        f"display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));"
        f"gap:{SPACING[gap]};"
    )


def cluster_style(
    *,
    gap: str = "md",
    align: str = "center",
    justify: str | None = None,
    wrap: bool = True,
) -> str:
    """回傳水平 cluster layout 樣式。"""
    justify_style = f"justify-content:{justify};" if justify is not None else ""
    wrap_style = "wrap" if wrap else "nowrap"
    return (
        f"display:flex;gap:{SPACING[gap]};align-items:{align};"
        f"flex-wrap:{wrap_style};{justify_style}"
    )


def stack_block_style(*, gap: str = "sm", min_width: str | None = None) -> str:
    """回傳局部 grid stack 樣式。"""
    min_width_style = f"min-width:{min_width};" if min_width is not None else ""
    return f"display:grid;gap:{SPACING[gap]};{min_width_style}"


def zero_margin_style(extra: str = "") -> str:
    """回傳零 margin 文字樣式。"""
    return f"margin:0;{extra}"


def block_nowrap_style(extra: str = "") -> str:
    """回傳分行但不換字的文字樣式。"""
    return f"display:block;white-space:nowrap;{extra}"


def table_action_cell_style() -> str:
    """回傳 watch list 操作欄的垂直置中 layout 樣式。"""
    return "display:flex;flex-direction:column;justify-content:center;height:100%;"


def checkbox_label(*, input_html: str, label: str) -> str:
    """渲染 checkbox 與文字同列的標準 label。"""
    return f'<label style="{cluster_style(gap="sm")}">{input_html}{escape(label)}</label>'


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
