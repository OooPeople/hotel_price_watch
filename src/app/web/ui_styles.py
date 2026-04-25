"""本機 GUI 的語意化 inline style token。"""

from __future__ import annotations

THEME_COLORS = {
    "primary": "#0f6f68",
    "primary_hover": "#0a5f59",
    "primary_soft": "#dff2ed",
    "secondary": "#203a43",
    "background": "#eef5f2",
    "surface": "#fcfffe",
    "surface_alt": "#f8fbfa",
    "border": "#d7e2df",
    "border_strong": "#9fd3c7",
    "text": "#18322f",
    "muted": "#4b635f",
    "muted_soft": "#6b7f7b",
    "success_bg": "#dcfce7",
    "success_text": "#166534",
    "success_border": "#86efac",
    "warning_bg": "#fef3c7",
    "warning_text": "#92400e",
    "warning_border": "#fcd34d",
    "danger_bg": "#fee2e2",
    "danger_text": "#991b1b",
    "danger_border": "#fca5a5",
    "info_bg": "#dbeafe",
    "info_text": "#1e3a8a",
    "info_border": "#93c5fd",
    "muted_bg": "#f1f5f9",
    "muted_text": "#475569",
    "muted_border": "#cbd5e1",
}

SPACING = {
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "24px",
    "2xl": "32px",
    "3xl": "48px",
}

TYPOGRAPHY = {
    "page_title": "34px",
    "section_title": "24px",
    "hero_title": "28px",
    "card_title": "18px",
    "watch_title": "20px",
    "body": "15px",
    "meta": "13px",
    "summary_value": "24px",
    "price_value": "36px",
    "list_price": "22px",
}

RADIUS = {
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "pill": "999px",
}

BUTTON_SIZES = {
    "sm": "padding:8px 12px;font-size:14px;",
    "md": "padding:12px 18px;font-size:15px;",
}

CARD_STYLE = (
    "display:grid;gap:12px;padding:20px;"
    f"border:1px solid {THEME_COLORS['border']};"
    f"background:{THEME_COLORS['surface']};"
    f"border-radius:{RADIUS['lg']};"
)
SUMMARY_CARD_STYLE = (
    "display:grid;gap:8px;padding:18px;"
    f"border:1px solid {THEME_COLORS['border']};"
    f"background:{THEME_COLORS['surface']};"
    f"border-radius:{RADIUS['lg']};"
)
ERROR_STYLE = (
    "padding:12px;"
    f"border:1px solid {THEME_COLORS['danger_border']};"
    f"background:{THEME_COLORS['danger_bg']};"
)
SUCCESS_STYLE = (
    "padding:12px;"
    f"border:1px solid {THEME_COLORS['border_strong']};"
    f"background:{THEME_COLORS['primary_soft']};"
)
BODY_STYLE = (
    f"margin:0;background:{THEME_COLORS['background']};color:{THEME_COLORS['text']};"
    "font-family:'Microsoft JhengHei UI','Noto Sans TC',sans-serif;"
)
TABLE_STYLE = "width:100%;border-collapse:collapse;"
ACTION_ROW_STYLE = "display:flex;gap:8px;flex-wrap:wrap;"
PAGE_MAIN_STYLE = "width:min(1120px,100%);margin:0 auto;padding:32px 20px 64px;"
APP_SHELL_STYLE = "min-height:100vh;display:grid;grid-template-columns:220px minmax(0,1fr);"
SIDEBAR_STYLE = (
    "display:grid;align-content:start;gap:18px;padding:28px 18px;"
    f"border-right:1px solid {THEME_COLORS['border']};"
    f"background:{THEME_COLORS['surface']};"
)
SIDEBAR_BRAND_STYLE = (
    f"color:{THEME_COLORS['secondary']};font-weight:800;font-size:18px;"
    "letter-spacing:0.02em;text-decoration:none;"
)
SIDEBAR_NAV_STYLE = "display:grid;gap:6px;"
NOTICE_BOX_STYLE = (
    "padding:12px;"
    f"border:1px solid {THEME_COLORS['border']};"
    f"background:{THEME_COLORS['surface_alt']};"
    f"border-radius:{RADIUS['md']};"
)


def color_token(name: str) -> str:
    """依語意名稱回傳 theme 色票，避免 renderer 直接散落 hex color。"""
    return THEME_COLORS[name]


def muted_text_style(*, font_size: str = "14px") -> str:
    """回傳次要文字樣式，集中管理 meta text 的視覺降權。"""
    return f"color:{THEME_COLORS['muted']};font-size:{font_size};"


def meta_paragraph_style(*, font_size: str = "14px") -> str:
    """回傳次要段落文字樣式，避免 renderer 重複寫 margin 與 muted color。"""
    return f"margin:0;{muted_text_style(font_size=font_size)}"


def meta_label_style(*, display: str = "block") -> str:
    """回傳 key-value 標籤樣式，供卡片內小標籤共用。"""
    return f"display:{display};{muted_text_style(font_size=TYPOGRAPHY['meta'])}"


def stack_style(*, gap: str = "xl") -> str:
    """回傳垂直堆疊 layout 樣式，集中管理頁面與區塊間距。"""
    return f"display:grid;gap:{SPACING[gap]};"


def responsive_grid_style(*, min_width: str = "180px", gap: str = "14px") -> str:
    """回傳 responsive grid 樣式，供摘要卡與資訊欄位共用。"""
    return (
        "display:grid;"
        f"grid-template-columns:repeat(auto-fit,minmax({min_width},1fr));"
        f"gap:{gap};"
    )


def page_title_style() -> str:
    """回傳頁面主標題樣式。"""
    return f"margin:0;font-size:{TYPOGRAPHY['page_title']};line-height:1.15;"


def section_title_style() -> str:
    """回傳區塊標題樣式。"""
    return f"margin:0;font-size:{TYPOGRAPHY['section_title']};line-height:1.2;"


def card_title_style() -> str:
    """回傳卡片標題樣式。"""
    return f"margin:0;font-size:{TYPOGRAPHY['card_title']};line-height:1.25;"


def watch_title_style() -> str:
    """回傳 watch card 標題樣式。"""
    return f"margin:0;font-size:{TYPOGRAPHY['watch_title']};line-height:1.25;"


def hero_title_style() -> str:
    """回傳 detail hero 主標題樣式。"""
    return f"margin:0;font-size:{TYPOGRAPHY['hero_title']};line-height:1.15;"


def summary_value_style() -> str:
    """回傳摘要卡主要數字樣式。"""
    return f"font-size:{TYPOGRAPHY['summary_value']};line-height:1.2;"


def list_price_style() -> str:
    """回傳列表卡片價格樣式。"""
    return f"font-size:{TYPOGRAPHY['list_price']};line-height:1.15;"


def hero_price_style() -> str:
    """回傳 detail hero 價格樣式。"""
    return f"font-size:{TYPOGRAPHY['price_value']};line-height:1.1;"


def surface_card_style(*, gap: str = "14px", padding: str = "18px") -> str:
    """回傳一般資訊卡片樣式，讓 partial 不需直接硬寫 border / surface。"""
    return (
        f"display:grid;gap:{gap};padding:{padding};"
        f"border:1px solid {THEME_COLORS['border']};"
        f"background:{THEME_COLORS['surface']};"
        f"border-radius:{RADIUS['lg']};"
    )


def selectable_card_style(*, selected: bool) -> str:
    """回傳可選卡片樣式，讓候選方案與分頁選擇共用選取語意。"""
    border_color = THEME_COLORS["primary"] if selected else THEME_COLORS["border"]
    background = "#f0fdfa" if selected else THEME_COLORS["surface"]
    return (
        "display:block;padding:16px;border:1px solid "
        f"{border_color};background:{background};"
        f"border-radius:{RADIUS['lg']};cursor:pointer;"
    )


def nav_link_style(*, active: bool = False) -> str:
    """回傳 AppShell sidebar 導覽連結樣式。"""
    background = THEME_COLORS["primary_soft"] if active else "transparent"
    color = THEME_COLORS["primary"] if active else THEME_COLORS["secondary"]
    weight = "700" if active else "600"
    return (
        "display:block;padding:10px 12px;text-decoration:none;"
        f"border-radius:{RADIUS['md']};background:{background};"
        f"color:{color};font-weight:{weight};"
    )


def badge_style(kind: str) -> str:
    """依狀態語意回傳 badge 的 inline style。"""
    palette = {
        "success": (
            THEME_COLORS["success_bg"],
            THEME_COLORS["success_text"],
            THEME_COLORS["success_border"],
        ),
        "warning": (
            THEME_COLORS["warning_bg"],
            THEME_COLORS["warning_text"],
            THEME_COLORS["warning_border"],
        ),
        "danger": (
            THEME_COLORS["danger_bg"],
            THEME_COLORS["danger_text"],
            THEME_COLORS["danger_border"],
        ),
        "info": (
            THEME_COLORS["info_bg"],
            THEME_COLORS["info_text"],
            THEME_COLORS["info_border"],
        ),
        "muted": (
            THEME_COLORS["muted_bg"],
            THEME_COLORS["muted_text"],
            THEME_COLORS["muted_border"],
        ),
    }
    background, color, border = palette.get(kind, palette["muted"])
    return (
        "display:inline-flex;align-items:center;width:max-content;"
        "padding:4px 9px;border-radius:999px;font-size:13px;font-weight:600;"
        f"background:{background};color:{color};border:1px solid {border};"
    )


def primary_button_style(*, size: str = "md") -> str:
    """回傳主要按鈕的 inline style。"""
    size_style = BUTTON_SIZES[size]
    return (
        f"display:inline-block;{size_style}color:#fff;"
        f"background:{THEME_COLORS['primary']};"
        f"border-radius:{RADIUS['md']};"
        "text-decoration:none;border:none;cursor:pointer;font-weight:700;"
    )


def secondary_button_style(*, size: str = "md") -> str:
    """回傳次要按鈕的 inline style。"""
    size_style = BUTTON_SIZES[size]
    return (
        f"display:inline-block;{size_style}"
        f"background:{THEME_COLORS['primary_soft']};color:{THEME_COLORS['primary']};"
        f"border:1px solid {THEME_COLORS['border_strong']};"
        f"border-radius:{RADIUS['md']};"
        "text-decoration:none;cursor:pointer;font-weight:700;"
    )


def danger_button_style(*, size: str = "sm") -> str:
    """回傳刪除操作按鈕的 inline style。"""
    size_style = BUTTON_SIZES[size]
    return (
        f"display:inline-block;{size_style}"
        f"background:{THEME_COLORS['danger_bg']};color:{THEME_COLORS['danger_text']};"
        f"border:1px solid {THEME_COLORS['danger_border']};"
        f"border-radius:{RADIUS['md']};cursor:pointer;"
    )


def disabled_button_style(*, size: str = "md") -> str:
    """回傳不可操作按鈕的 inline style。"""
    size_style = BUTTON_SIZES[size]
    return (
        f"display:inline-block;{size_style}background:#e5e7eb;color:#6b7280;"
        "text-decoration:none;border:1px solid #d1d5db;border-radius:8px;cursor:not-allowed;"
        "opacity:0.85;"
    )


def cell_style(*, head: bool) -> str:
    """回傳列表頁表格儲存格的 inline style。"""
    background = THEME_COLORS["primary_soft"] if head else "#fff"
    return (
        "padding:10px 12px;text-align:left;"
        f"border:1px solid {THEME_COLORS['border']};background:{background};"
    )


def input_style() -> str:
    """回傳輸入元件的 inline style。"""
    return (
        "width:100%;padding:10px 12px;"
        f"border:1px solid {THEME_COLORS['border_strong']};"
        f"border-radius:{RADIUS['md']};"
        "background:#fff;box-sizing:border-box;"
    )


def pre_style() -> str:
    """回傳 debug 區 `pre` 區塊的 inline style。"""
    return (
        "margin:0;padding:12px;background:#0f172a;color:#e2e8f0;overflow:auto;"
        "white-space:pre-wrap;word-break:break-word;border-radius:8px;"
    )
