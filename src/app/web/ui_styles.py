"""本機 GUI 的語意化 inline style token。"""

from __future__ import annotations

CARD_STYLE = "display:grid;gap:12px;padding:20px;border:1px solid #d7e2df;background:#fcfffe;"
ERROR_STYLE = "padding:12px;border:1px solid #e57c7c;background:#fff3f3;"
SUCCESS_STYLE = "padding:12px;border:1px solid #9fd3c7;background:#edf7f3;"
BODY_STYLE = (
    "margin:0;background:#f4f7f6;color:#18322f;"
    "font-family:'Microsoft JhengHei UI','Noto Sans TC',sans-serif;"
)
TABLE_STYLE = "width:100%;border-collapse:collapse;"
ACTION_ROW_STYLE = "display:flex;gap:8px;flex-wrap:wrap;"
PAGE_MAIN_STYLE = "max-width:980px;margin:0 auto;padding:32px 20px 64px;"
NOTICE_BOX_STYLE = "padding:12px;border:1px solid #d7e2df;background:#f8fbfa;"


def primary_button_style() -> str:
    """回傳主要按鈕的 inline style。"""
    return (
        "display:inline-block;padding:12px 18px;background:#0f766e;color:#fff;"
        "text-decoration:none;border:none;border-radius:8px;cursor:pointer;"
    )


def secondary_button_style() -> str:
    """回傳次要按鈕的 inline style。"""
    return (
        "display:inline-block;padding:12px 18px;background:#dff2ed;color:#0f766e;"
        "text-decoration:none;border:1px solid #9fd3c7;border-radius:8px;cursor:pointer;"
    )


def danger_button_style() -> str:
    """回傳刪除操作按鈕的 inline style。"""
    return (
        "display:inline-block;padding:8px 12px;background:#fff3f3;color:#9f1239;"
        "border:1px solid #f1aeb5;border-radius:8px;cursor:pointer;"
    )


def disabled_button_style() -> str:
    """回傳不可操作按鈕的 inline style。"""
    return (
        "display:inline-block;padding:12px 18px;background:#e5e7eb;color:#6b7280;"
        "text-decoration:none;border:1px solid #d1d5db;border-radius:8px;cursor:not-allowed;"
        "opacity:0.85;"
    )


def cell_style(*, head: bool) -> str:
    """回傳列表頁表格儲存格的 inline style。"""
    background = "#dff2ed" if head else "#fff"
    return f"padding:10px 12px;border:1px solid #d7e2df;text-align:left;background:{background};"


def input_style() -> str:
    """回傳輸入元件的 inline style。"""
    return (
        "width:100%;padding:10px 12px;border:1px solid #b8cbc7;border-radius:8px;"
        "background:#fff;box-sizing:border-box;"
    )


def pre_style() -> str:
    """回傳 debug 區 `pre` 區塊的 inline style。"""
    return (
        "margin:0;padding:12px;background:#0f172a;color:#e2e8f0;overflow:auto;"
        "white-space:pre-wrap;word-break:break-word;border-radius:8px;"
    )
