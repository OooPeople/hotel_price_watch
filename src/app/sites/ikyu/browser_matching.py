"""提供 `ikyu` browser page 與 watch target 的穩定比對規則。"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from app.domain.value_objects import WatchTarget


@dataclass(frozen=True, slots=True)
class IkyuBrowserPageSignature:
    """整理 `ikyu` URL 中可用於分頁與 watch 比對的關鍵識別訊號。"""

    hotel_id: str | None
    room_id: str | None
    plan_id: str | None
    check_in: str | None
    people_count: str | None
    room_count: str | None


def is_ikyu_page_url(url: str) -> bool:
    """判斷目前分頁是否為 `ikyu` 網站頁面。"""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.endswith("ikyu.com")


def extract_ikyu_browser_page_signature(url: str) -> IkyuBrowserPageSignature:
    """從 `ikyu` URL 萃取房型、方案與查詢條件供穩定比對使用。"""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    hotel_id = path_segments[-1] if path_segments else None
    if hotel_id is not None and not hotel_id.isdigit():
        hotel_id = None

    return IkyuBrowserPageSignature(
        hotel_id=hotel_id,
        room_id=_first_query_value(query, "rm"),
        plan_id=_first_query_value(query, "pln"),
        check_in=_first_query_value(query, "cid"),
        people_count=_first_query_value(query, "ppc"),
        room_count=_first_query_value(query, "rc"),
    )


def score_ikyu_browser_page(
    current_url: str,
    *,
    expected_url: str,
    profile_start_url: str,
) -> int:
    """依 URL 與 target 訊號相似度，計算目前分頁是否接近目標頁。"""
    current = urlparse(current_url)
    expected = urlparse(expected_url)
    profile_start = urlparse(profile_start_url)
    current_signature = extract_ikyu_browser_page_signature(current_url)
    expected_signature = extract_ikyu_browser_page_signature(expected_url)

    if current_url in {"about:blank", ""}:
        return 1
    if not current.scheme or not current.netloc:
        return 0
    if current.netloc != expected.netloc:
        return 0
    if current.path.rstrip("/") == profile_start.path.rstrip("/"):
        return 1
    if current_url == expected_url:
        return 100

    score = 0
    if current.path.rstrip("/") == expected.path.rstrip("/"):
        score += 20
    elif current.path.rstrip("/").startswith(expected.path.rstrip("/")):
        score += 10

    if (
        current_signature.hotel_id is not None
        and current_signature.hotel_id == expected_signature.hotel_id
    ):
        score += 10
    if (
        current_signature.room_id is not None
        and current_signature.room_id == expected_signature.room_id
    ):
        score += 25
    if (
        current_signature.plan_id is not None
        and current_signature.plan_id == expected_signature.plan_id
    ):
        score += 25
    if (
        current_signature.check_in is not None
        and current_signature.check_in == expected_signature.check_in
    ):
        score += 8
    if (
        current_signature.people_count is not None
        and current_signature.people_count == expected_signature.people_count
    ):
        score += 5
    if (
        current_signature.room_count is not None
        and current_signature.room_count == expected_signature.room_count
    ):
        score += 5

    if score > 0:
        return score
    if current.path.rstrip("/") == expected.path.rstrip("/"):
        return 3
    if current.path.rstrip("/").startswith(expected.path.rstrip("/")):
        return 2
    return 1


def is_confident_ikyu_page_match(
    *,
    current_signature: IkyuBrowserPageSignature,
    expected_signature: IkyuBrowserPageSignature,
    score: int,
    minimum_score: int,
) -> bool:
    """判斷分頁訊號是否足夠接近精確 target，可安全沿用既有分頁。"""
    expected_has_precise_target = (
        expected_signature.room_id is not None or expected_signature.plan_id is not None
    )
    if not expected_has_precise_target:
        return score > 0

    if score < minimum_score:
        return False

    room_matches = (
        current_signature.room_id is not None
        and current_signature.room_id == expected_signature.room_id
    )
    plan_matches = (
        current_signature.plan_id is not None
        and current_signature.plan_id == expected_signature.plan_id
    )
    return room_matches or plan_matches


def ikyu_urls_match_confidently(*, left_url: str, right_url: str) -> bool:
    """判斷兩個 `ikyu` URL 是否指向同一個精確 room-plan watch 目標。"""
    return ikyu_signatures_match_confidently(
        left=extract_ikyu_browser_page_signature(left_url),
        right=extract_ikyu_browser_page_signature(right_url),
    )


def ikyu_signature_matches_watch_target(
    *,
    signature: IkyuBrowserPageSignature,
    target: WatchTarget,
) -> bool:
    """以 URL signature 判斷目前分頁是否對應指定 watch target。"""
    expected_check_in = target.check_in_date.isoformat().replace("-", "")
    expected_people_count = str(target.people_count)
    expected_room_count = str(target.room_count)
    return (
        target.site == "ikyu"
        and signature.hotel_id == target.hotel_id
        and signature.room_id == target.room_id
        and signature.plan_id == target.plan_id
        and (signature.check_in is None or signature.check_in == expected_check_in)
        and (
            signature.people_count is None
            or signature.people_count == expected_people_count
        )
        and (signature.room_count is None or signature.room_count == expected_room_count)
    )


def ikyu_signatures_match_confidently(
    *,
    left: IkyuBrowserPageSignature,
    right: IkyuBrowserPageSignature,
) -> bool:
    """僅在精確 target 足夠一致時，才把兩個 signature 視為同一 watch。"""
    if not all(
        (
            left.hotel_id,
            left.room_id,
            left.plan_id,
            right.hotel_id,
            right.room_id,
            right.plan_id,
        )
    ):
        return False

    return (
        left.hotel_id == right.hotel_id
        and left.room_id == right.room_id
        and left.plan_id == right.plan_id
        and _optional_signature_field_matches(left.check_in, right.check_in)
        and _optional_signature_field_matches(left.people_count, right.people_count)
        and _optional_signature_field_matches(left.room_count, right.room_count)
    )


def _optional_signature_field_matches(left: str | None, right: str | None) -> bool:
    """兩邊都存在時需一致；任一方缺省時，視為可接受的非衝突狀態。"""
    if left is None or right is None:
        return True
    return left == right


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    """安全取出 query string 第一個值，避免空字串與缺值混淆。"""
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None
