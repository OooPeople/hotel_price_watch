"""處理 `ikyu` seed URL 的比對、正規化與草稿解析。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.domain.value_objects import SearchDraft

_SUPPORTED_HOSTS = {"ikyu.com", "www.ikyu.com"}
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}
_CHECK_IN_KEYS = ("checkin", "check_in", "checkin_date", "check_in_date", "ci")
_CHECK_OUT_KEYS = ("checkout", "check_out", "checkout_date", "check_out_date", "co")
_PEOPLE_COUNT_KEYS = ("adults", "adult", "people_count", "occupancy", "guests", "ppc")
_ROOM_COUNT_KEYS = ("rooms", "room_count", "room_num", "rc")
_HOTEL_ID_KEYS = ("hotel_id",)
_ROOM_ID_KEYS = ("rm", "room_id")
_PLAN_ID_KEYS = ("pln", "plan_id")
_STAY_NIGHTS_KEYS = ("si", "nights", "stay_nights")


def is_supported_ikyu_url(url: str) -> bool:
    """判斷 URL 是否屬於目前支援的 `ikyu` 站點。"""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in _SUPPORTED_HOSTS


def normalize_seed_url(url: str) -> str:
    """移除追蹤參數並穩定化 query 順序，作為草稿的標準 seed URL。"""
    parsed = urlparse(url)
    if not is_supported_ikyu_url(url):
        raise ValueError("unsupported ikyu URL")

    filtered_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key not in _TRACKING_QUERY_KEYS and not key.startswith(_TRACKING_QUERY_PREFIXES)
    ]
    normalized_query = urlencode(sorted(filtered_pairs))
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            "https",
            parsed.netloc.lower(),
            normalized_path,
            "",
            normalized_query,
            "",
        )
    )


def parse_seed_url(url: str) -> SearchDraft:
    """把 `ikyu` URL 解析成可由 UI 繼續補完的 `SearchDraft`。"""
    normalized_url = normalize_seed_url(url)
    parsed = urlparse(normalized_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    check_in_date = _parse_check_in_date(query)
    check_out_date = _parse_check_out_date(query)
    if check_out_date is None and check_in_date is not None:
        stay_nights = _parse_positive_int(_extract_first(query, _STAY_NIGHTS_KEYS))
        if stay_nights is not None:
            check_out_date = check_in_date + timedelta(days=stay_nights)

    draft = SearchDraft(
        seed_url=normalized_url,
        hotel_id=_extract_hotel_id_from_path(parsed.path) or _extract_first(query, _HOTEL_ID_KEYS),
        room_id=_extract_first(query, _ROOM_ID_KEYS),
        plan_id=_extract_first(query, _PLAN_ID_KEYS),
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        people_count=_parse_positive_int(_extract_first(query, _PEOPLE_COUNT_KEYS)),
        room_count=_parse_positive_int(_extract_first(query, _ROOM_COUNT_KEYS)),
    )
    return normalize_search_draft(draft)


def normalize_search_draft(draft: SearchDraft) -> SearchDraft:
    """驗證並正規化 `ikyu` 查詢草稿欄位。"""
    if draft.check_in_date and draft.check_out_date and draft.check_out_date <= draft.check_in_date:
        raise ValueError("check_out_date must be after check_in_date")

    for field_name, value in (
        ("people_count", draft.people_count),
        ("room_count", draft.room_count),
    ):
        if value is not None and value <= 0:
            raise ValueError(f"{field_name} must be positive")

    if (draft.check_in_date is None) != (draft.check_out_date is None):
        raise ValueError("check_in_date and check_out_date must be provided together")

    return replace(
        draft,
        hotel_id=_normalize_optional_token(draft.hotel_id),
        room_id=_normalize_optional_token(draft.room_id),
        plan_id=_normalize_optional_token(draft.plan_id),
    )


def _extract_first(query: dict[str, str], keys: tuple[str, ...]) -> str | None:
    """依優先順序從 query 取出第一個存在的參數值。"""
    for key in keys:
        value = query.get(key)
        if value:
            return value
    return None


def _parse_date(raw_value: str | None) -> date | None:
    """支援多種常見日期格式，失敗時拋出例外避免靜默錯判。"""
    if raw_value is None:
        return None

    normalized = raw_value.replace("/", "-")
    if len(normalized) == 8 and normalized.isdigit():
        normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"
    return date.fromisoformat(normalized)


def _parse_check_in_date(query: dict[str, str]) -> date | None:
    """解析一般 check-in 欄位，並支援 `ikyu` 的 `cid=YYYYMMDD`。"""
    direct_value = _extract_first(query, _CHECK_IN_KEYS)
    if direct_value is not None:
        return _parse_date(direct_value)

    cid_value = query.get("cid")
    if cid_value is not None and _looks_like_compact_date(cid_value):
        return _parse_date(cid_value)
    return None


def _parse_check_out_date(query: dict[str, str]) -> date | None:
    """解析一般 check-out 欄位。"""
    return _parse_date(_extract_first(query, _CHECK_OUT_KEYS))


def _parse_positive_int(raw_value: str | None) -> int | None:
    """把 query 內的正整數欄位轉成 `int`。"""
    if raw_value is None:
        return None

    value = int(raw_value)
    if value <= 0:
        raise ValueError("value must be positive")
    return value


def _extract_hotel_id_from_path(path: str) -> str | None:
    """從一般飯店頁路徑中推測最後一段作為 hotel id。"""
    parts = [part for part in path.split("/") if part]
    if not parts:
        return None
    return parts[-1]


def _normalize_optional_token(value: str | None) -> str | None:
    """清理字串型識別欄位，避免保存空白或空字串。"""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _looks_like_compact_date(value: str) -> bool:
    """判斷字串是否符合 `YYYYMMDD` 日期格式。"""
    return len(value) == 8 and value.isdigit()
