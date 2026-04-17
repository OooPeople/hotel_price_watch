"""本機 GUI route 共用的 request 與表單處理 helper。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, Request


async def read_form_data(request: Request) -> dict[str, str]:
    """手動解析表單內容，避免額外依賴 multipart 套件。"""
    body = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def ensure_local_request_origin(request: Request) -> None:
    """驗證 state-changing POST 是否來自允許的本機管理介面來源。"""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if not origin and not referer:
        raise HTTPException(status_code=403, detail="missing request origin")

    expected_scheme = request.url.scheme
    expected_port = request.url.port or (443 if expected_scheme == "https" else 80)
    local_hosts = {"127.0.0.1", "localhost"}

    if origin is not None and is_allowed_local_url(
        origin,
        expected_scheme=expected_scheme,
        expected_port=expected_port,
        local_hosts=local_hosts,
    ):
        return

    if referer is not None and is_allowed_local_url(
        referer,
        expected_scheme=expected_scheme,
        expected_port=expected_port,
        local_hosts=local_hosts,
    ):
        return

    raise HTTPException(status_code=403, detail="invalid request origin")


def is_allowed_local_url(
    raw_url: str,
    *,
    expected_scheme: str,
    expected_port: int,
    local_hosts: set[str],
) -> bool:
    """判斷來源 URL 是否屬於允許的本機管理介面位址。"""
    parsed = urlparse(raw_url)
    hostname = parsed.hostname
    if hostname not in local_hosts:
        return False
    if parsed.scheme != expected_scheme:
        return False
    actual_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return actual_port == expected_port


def parse_candidate_key(raw_value: str) -> tuple[str, str]:
    """把 radio button 的候選 key 還原成 room_id / plan_id。"""
    room_id, separator, plan_id = raw_value.partition("::")
    if not separator or not room_id or not plan_id:
        raise ValueError("請先選擇有效的房型方案")
    return room_id, plan_id


def parse_optional_decimal(raw_value: str) -> Decimal | None:
    """把表單中的目標價字串轉成可選的 Decimal。"""
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("目標價格式不正確") from exc


def parse_checkbox(raw_value: str | None) -> bool:
    """把 HTML checkbox 欄位轉成布林值。"""
    return raw_value == "on"


def to_user_facing_error_message(exc: Exception) -> str:
    """把內部錯誤訊息轉成較適合 GUI 顯示的說法。"""
    raw_message = str(exc)
    if raw_message == "search draft is incomplete for candidate lookup":
        return (
            "目前網址尚未帶齊查候選所需條件；"
            "請改用已帶日期與人數的精確 URL，"
            "或改由專用 Chrome 分頁抓取。"
        )
    return raw_message
