from datetime import date

import pytest

from app.sites.ikyu import IkyuAdapter
from app.sites.ikyu.normalizer import normalize_search_draft, normalize_seed_url, parse_seed_url


def test_normalize_seed_url_strips_tracking_params_and_sorts_query() -> None:
    """驗證 seed URL 正規化會移除追蹤參數並固定 query 排序。"""
    normalized = normalize_seed_url(
        "http://www.ikyu.com/hotel/hotel-123/?utm_source=newsletter&pln=plan-1&rm=room-1&cid=hotel-123"
    )

    assert normalized == (
        "https://www.ikyu.com/hotel/hotel-123?cid=hotel-123&pln=plan-1&rm=room-1"
    )


def test_parse_fixed_plan_url_prefills_core_fields() -> None:
    """驗證精確方案 URL 可預填建立 watch 需要的核心欄位。"""
    draft = parse_seed_url(
        "https://ikyu.com/hotel/hotel-123?cid=hotel-123&rm=room-1&pln=plan-1"
        "&ci=2026-05-01&co=2026-05-03&adults=2&rooms=1"
    )

    assert draft.seed_url == (
        "https://ikyu.com/hotel/hotel-123?adults=2&ci=2026-05-01&cid=hotel-123"
        "&co=2026-05-03&pln=plan-1&rm=room-1&rooms=1"
    )
    assert draft.hotel_id == "hotel-123"
    assert draft.room_id == "room-1"
    assert draft.plan_id == "plan-1"
    assert draft.check_in_date == date(2026, 5, 1)
    assert draft.check_out_date == date(2026, 5, 3)
    assert draft.people_count == 2
    assert draft.room_count == 1
    assert draft.nights == 2
    assert draft.is_ready_for_candidate_lookup() is True


def test_parse_general_hotel_url_allows_partial_prefill() -> None:
    """驗證一般飯店 URL 可建立不完整但可繼續編輯的 search draft。"""
    draft = parse_seed_url("https://www.ikyu.com/hotel/hotel-456/")

    assert draft.seed_url == "https://www.ikyu.com/hotel/hotel-456"
    assert draft.hotel_id == "hotel-456"
    assert draft.room_id is None
    assert draft.plan_id is None
    assert draft.check_in_date is None
    assert draft.check_out_date is None
    assert draft.people_count is None
    assert draft.room_count is None
    assert draft.is_ready_for_candidate_lookup() is False


def test_parse_real_ikyu_precise_url_prefills_date_from_cid_and_si() -> None:
    """驗證真實 `ikyu` URL 的 `cid` / `si` 可還原入住與退房日期。"""
    draft = parse_seed_url(
        "https://www.ikyu.com/zh-tw/00082173/"
        "?adc=1&cid=20260918&discsort=1&lc=1&pln=11035620"
        "&ppc=2&rc=1&rm=10191605&si=1&st=1"
    )

    assert draft.hotel_id == "00082173"
    assert draft.room_id == "10191605"
    assert draft.plan_id == "11035620"
    assert draft.check_in_date == date(2026, 9, 18)
    assert draft.check_out_date == date(2026, 9, 19)
    assert draft.people_count == 2
    assert draft.room_count == 1
    assert draft.is_ready_for_candidate_lookup() is True


def test_normalize_search_draft_requires_date_pair() -> None:
    """驗證搜尋草稿若只有入住日而缺退房日，應拒絕正規化。"""
    draft = parse_seed_url("https://ikyu.com/hotel/hotel-123?cid=hotel-123")

    with pytest.raises(ValueError):
        normalize_search_draft(
            draft.__class__(
                seed_url=draft.seed_url,
                hotel_id=draft.hotel_id,
                check_in_date=date(2026, 5, 1),
            )
        )


def test_adapter_matches_ikyu_urls() -> None:
    """驗證 `ikyu` adapter 只接受支援的 `ikyu.com` URL。"""
    adapter = IkyuAdapter()

    assert adapter.match_url("https://ikyu.com/hotel/hotel-123")
    assert adapter.match_url("https://www.ikyu.com/hotel/hotel-123")
    assert adapter.match_url("http://ikyu.com/hotel/hotel-123")
    assert adapter.match_url("https://example.com/hotel/hotel-123") is False
