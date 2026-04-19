"""本機 GUI renderer 共用的 HTML helper 與 inline style。"""

from __future__ import annotations

from datetime import datetime
from html import escape

CARD_STYLE = "display:grid;gap:12px;padding:20px;border:1px solid #d7e2df;background:#fcfffe;"
ERROR_STYLE = "padding:12px;border:1px solid #e57c7c;background:#fff3f3;"
SUCCESS_STYLE = "padding:12px;border:1px solid #9fd3c7;background:#edf7f3;"
BODY_STYLE = (
    "margin:0;background:#f4f7f6;color:#18322f;"
    "font-family:'Microsoft JhengHei UI','Noto Sans TC',sans-serif;"
)


def page_layout(*, title: str, body: str) -> str:
    """輸出 GUI 共用頁面框架。"""
    return f"""
    <!doctype html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
      </head>
      <body style="{BODY_STYLE}">
        <main style="max-width:980px;margin:0 auto;padding:32px 20px 64px;">
          {body}
        </main>
      </body>
    </html>
    """


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


def format_datetime_for_display(value: datetime | None) -> str:
    """將 aware datetime 轉成使用者電腦目前的本地時間格式。"""
    if value is None:
        return "none"
    return value.astimezone().strftime("%Y/%m/%d %H:%M")
