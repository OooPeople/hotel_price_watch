import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.enums import SourceKind
from app.domain.value_objects import SearchDraft, WatchTarget, WatchTargetIdentity
from app.sites.base import CandidateSelection
from app.sites.ikyu import IkyuAdapter
from app.sites.ikyu.client import HtmlFetchResult, IkyuHtmlClient
from app.sites.ikyu.parser import (
    parse_candidate_bundle,
    parse_target_snapshot,
    parse_target_snapshot_with_source,
)

_FIXTURE_DIR = Path("fixtures/ikyu")


def test_parse_candidate_bundle_from_available_fixture() -> None:
    html = _read_fixture("available_basic.html")

    bundle = parse_candidate_bundle(html)

    assert bundle.hotel_id == "hotel-123"
    assert bundle.hotel_name == "Ocean Hotel"
    assert bundle.canonical_url == "https://www.ikyu.com/hotel/hotel-123"
    assert len(bundle.candidates) == 2
    assert bundle.candidates[0].room_id == "room-1"
    assert bundle.candidates[0].plan_id == "plan-1"
    assert bundle.candidates[0].display_price_text == "JPY 24000"
    assert bundle.candidates[0].normalized_price_amount == Decimal("24000")
    assert bundle.candidates[0].currency == "JPY"


def test_parse_candidate_bundle_returns_empty_result_when_payload_missing() -> None:
    """驗證候選解析在缺少 payload script 時會穩定降級。"""
    bundle = parse_candidate_bundle("<html><body>missing payload</body></html>")

    assert bundle.hotel_id == ""
    assert bundle.hotel_name == "unknown hotel"
    assert bundle.canonical_url == ""
    assert bundle.candidates == ()


def test_parse_candidate_bundle_skips_invalid_offer_entries() -> None:
    """驗證候選解析遇到缺欄位 offer 時只略過壞資料。"""
    html = """
    <script id="__IKYU_DATA__" type="application/json">
    {
      "hotel": {
        "id": "hotel-123",
        "name": "Ocean Hotel",
        "canonical_url": "https://www.ikyu.com/hotel/hotel-123"
      },
      "offers": [
        {
          "room_id": "room-1",
          "room_name": "Standard Room",
          "plan_id": "plan-1",
          "plan_name": "Room Only"
        },
        {
          "room_id": "room-2",
          "plan_id": "plan-2"
        }
      ]
    }
    </script>
    """

    bundle = parse_candidate_bundle(html)

    assert bundle.hotel_id == "hotel-123"
    assert len(bundle.candidates) == 1
    assert bundle.candidates[0].room_id == "room-1"


def test_parse_candidate_bundle_falls_back_to_hotel_json_ld() -> None:
    """缺少舊 payload 時，應可從 Hotel JSON-LD 解析精確候選。"""
    html = """
    <script type="application/ld+json">
    {
      "@context": "http://schema.org",
      "@type": "Hotel",
      "url": "https://www.ikyu.com/zh-tw/00082173/",
      "identifier": "00082173",
      "name": "Debug Hotel",
      "containsPlace": {
        "@type": ["HotelRoom", "Product"],
        "identifier": "10191605",
        "name": "禁菸 標準雙人房",
        "offers": {
          "@type": ["Offer", "LodgingReservation"],
          "identifier": "11035620",
          "price": 22990,
          "priceCurrency": "JPY",
          "availability": "https://schema.org/InStock"
        }
      }
    }
    </script>
    """

    bundle = parse_candidate_bundle(html)

    assert bundle.hotel_id == "00082173"
    assert bundle.hotel_name == "Debug Hotel"
    assert bundle.candidates[0].room_id == "10191605"
    assert bundle.candidates[0].plan_id == "11035620"
    assert bundle.candidates[0].room_name == "禁菸 標準雙人房"
    assert bundle.candidates[0].display_price_text == "JPY 22990"
    assert bundle.candidates[0].normalized_price_amount == Decimal("22990")
    assert bundle.candidates[0].currency == "JPY"


def test_parse_available_snapshot_matches_expected_fixture() -> None:
    expected = _read_expectation("available_basic.json")

    snapshot = parse_target_snapshot(_read_fixture("available_basic.html"), _build_target())

    assert snapshot.display_price_text == expected["snapshot"]["display_price_text"]
    assert snapshot.normalized_price_amount == Decimal(
        expected["snapshot"]["normalized_price_amount"]
    )
    assert snapshot.currency == expected["snapshot"]["currency"]
    assert snapshot.availability.value == expected["snapshot"]["availability"]


def test_parse_sold_out_snapshot_matches_expected_fixture() -> None:
    expected = _read_expectation("sold_out_basic.json")

    snapshot = parse_target_snapshot(_read_fixture("sold_out_basic.html"), _build_target())

    assert asdict(snapshot) == {
        "display_price_text": expected["snapshot"]["display_price_text"],
        "normalized_price_amount": expected["snapshot"]["normalized_price_amount"],
        "currency": expected["snapshot"]["currency"],
        "availability": snapshot.availability,
        "source_kind": snapshot.source_kind,
    }
    assert snapshot.availability.value == expected["snapshot"]["availability"]


def test_parse_target_missing_snapshot_matches_expected_fixture() -> None:
    expected = _read_expectation("target_missing_basic.json")

    snapshot = parse_target_snapshot(_read_fixture("target_missing_basic.html"), _build_target())

    assert snapshot.display_price_text is None
    assert snapshot.normalized_price_amount is None
    assert snapshot.currency is None
    assert snapshot.availability.value == expected["snapshot"]["availability"]


def test_parse_format_variation_snapshot_uses_normalized_amount() -> None:
    expected = _read_expectation("format_variation_basic.json")

    snapshot = parse_target_snapshot(_read_fixture("format_variation_basic.html"), _build_target())

    assert snapshot.display_price_text == expected["snapshot"]["display_price_text"]
    assert snapshot.normalized_price_amount == Decimal(
        expected["snapshot"]["normalized_price_amount"]
    )
    assert snapshot.currency == expected["snapshot"]["currency"]
    assert snapshot.availability.value == expected["snapshot"]["availability"]


def test_parse_target_snapshot_returns_parse_error_when_payload_script_missing() -> None:
    """驗證缺少 payload script 時，target snapshot 會穩定降級。"""
    snapshot = parse_target_snapshot("<html><body>missing payload</body></html>", _build_target())

    assert snapshot.display_price_text is None
    assert snapshot.normalized_price_amount is None
    assert snapshot.currency is None
    assert snapshot.availability.value == "parse_error"


def test_parse_target_snapshot_falls_back_to_hotel_json_ld() -> None:
    """缺少舊 payload 時，應可從 Hotel JSON-LD 解析精確方案價格。"""
    html = """
    <script type="application/ld+json">
    {
      "@context": "http://schema.org",
      "@type": "Hotel",
      "url": "https://www.ikyu.com/zh-tw/00082173/",
      "identifier": "00082173",
      "name": "Debug Hotel",
      "containsPlace": {
        "@type": ["HotelRoom", "Product"],
        "identifier": "room-1",
        "name": "Standard Room",
        "offers": {
          "@type": ["Offer", "LodgingReservation"],
          "identifier": "plan-1",
          "price": 22990,
          "priceCurrency": "JPY",
          "availability": "https://schema.org/InStock"
        }
      }
    }
    </script>
    """

    snapshot = parse_target_snapshot(html, _build_target())

    assert snapshot.display_price_text == "JPY 22990"
    assert snapshot.normalized_price_amount == Decimal("22990")
    assert snapshot.currency == "JPY"
    assert snapshot.availability.value == "available"


def test_parse_target_snapshot_returns_parse_error_for_invalid_json_payload() -> None:
    """驗證 payload JSON 損毀時，target snapshot 會回 parse_error。"""
    html = """
    <script id="__IKYU_DATA__" type="application/json">
    {"hotel": {"id": "hotel-123"}, "offers": [
    </script>
    """

    snapshot = parse_target_snapshot(html, _build_target())

    assert snapshot.availability.value == "parse_error"


def test_parse_target_snapshot_returns_parse_error_for_unknown_availability() -> None:
    """驗證未知 availability 值不會炸掉 parser。"""
    html = """
    <script id="__IKYU_DATA__" type="application/json">
    {
      "hotel": {"id": "hotel-123", "name": "Ocean Hotel", "canonical_url": "https://www.ikyu.com/hotel/hotel-123"},
      "offers": [{
        "room_id": "room-1",
        "room_name": "Standard Room",
        "plan_id": "plan-1",
        "plan_name": "Room Only",
        "availability": "mystery_state",
        "price": {"display_text": "JPY 24000", "normalized_amount": "24000", "currency": "JPY"}
      }]
    }
    </script>
    """

    snapshot = parse_target_snapshot(html, _build_target())

    assert snapshot.availability.value == "parse_error"


def test_parse_target_snapshot_returns_parse_error_when_price_shape_is_invalid() -> None:
    """驗證 matched offer 的 price 欄位異常時，target snapshot 會降級。"""
    html = """
    <script id="__IKYU_DATA__" type="application/json">
    {
      "hotel": {"id": "hotel-123", "name": "Ocean Hotel", "canonical_url": "https://www.ikyu.com/hotel/hotel-123"},
      "offers": [{
        "room_id": "room-1",
        "room_name": "Standard Room",
        "plan_id": "plan-1",
        "plan_name": "Room Only",
        "availability": "available",
        "price": "JPY 24000"
      }]
    }
    </script>
    """

    snapshot = parse_target_snapshot(html, _build_target())

    assert snapshot.availability.value == "parse_error"


def test_adapter_resolve_watch_target_builds_canonical_target() -> None:
    adapter = IkyuAdapter()
    draft = SearchDraft(
        seed_url="https://www.ikyu.com/hotel/hotel-123?cid=hotel-123&ci=2026-05-01&co=2026-05-03&adults=2&rooms=1",
        hotel_id="hotel-123",
        check_in_date=date(2026, 5, 1),
        check_out_date=date(2026, 5, 3),
        people_count=2,
        room_count=1,
    )

    target = adapter.resolve_watch_target(
        draft=draft,
        selection=CandidateSelection(room_id=" room-1 ", plan_id=" plan-1 "),
    )

    assert target.identity_key() == WatchTargetIdentity(
        site="ikyu",
        hotel_id="hotel-123",
        room_id="room-1",
        plan_id="plan-1",
        check_in_date=date(2026, 5, 1),
        check_out_date=date(2026, 5, 3),
        people_count=2,
        room_count=1,
    )


def test_adapter_refetches_candidates_when_draft_changes() -> None:
    adapter = IkyuAdapter(html_client=FakeIkyuHtmlClient())

    first_bundle = adapter.fetch_candidates(
        SearchDraft(
            seed_url="https://www.ikyu.com/hotel/hotel-123?cid=hotel-123&ci=2026-05-01&co=2026-05-03&adults=2&rooms=1",
            hotel_id="hotel-123",
            check_in_date=date(2026, 5, 1),
            check_out_date=date(2026, 5, 3),
            people_count=2,
            room_count=1,
        )
    )
    second_bundle = adapter.fetch_candidates(
        SearchDraft(
            seed_url="https://www.ikyu.com/hotel/hotel-123?cid=hotel-123&ci=2026-05-03&co=2026-05-05&adults=2&rooms=1",
            hotel_id="hotel-123",
            check_in_date=date(2026, 5, 3),
            check_out_date=date(2026, 5, 5),
            people_count=2,
            room_count=1,
        )
    )

    assert first_bundle.candidates[0].plan_id == "plan-1"
    assert second_bundle.candidates[0].plan_id == "plan-7"


def test_adapter_build_snapshot_from_browser_page_marks_browser_source() -> None:
    adapter = IkyuAdapter()

    snapshot = adapter.build_snapshot_from_browser_page(
        page_url="https://www.ikyu.com/zh-tw/hotel-123/?top=rooms",
        html=_read_fixture("available_basic.html"),
        target=_build_target(),
    )

    assert snapshot.display_price_text == "JPY 24000"
    assert snapshot.source_kind.value == "browser"


def test_parse_target_snapshot_with_source_can_mark_browser_origin() -> None:
    snapshot = parse_target_snapshot_with_source(
        _read_fixture("available_basic.html"),
        _build_target(),
        source_kind=SourceKind.BROWSER,
    )

    assert snapshot.source_kind is SourceKind.BROWSER


def test_adapter_saves_debug_capture_when_candidate_parse_is_empty(
    monkeypatch,
    tmp_path,
) -> None:
    """候選解析為空時，應自動保存真實頁面 HTML 與 metadata。"""
    import app.sites.ikyu.adapter as adapter_module

    monkeypatch.setattr(adapter_module, "DEBUG_CAPTURE_DIR", tmp_path / "debug")
    adapter = IkyuAdapter(html_client=EmptyCandidateHtmlClient())

    bundle = adapter.fetch_candidates(
        SearchDraft(
            seed_url="https://www.ikyu.com/zh-tw/00082173/?cid=20260918&si=1&ppc=2&rc=1",
            hotel_id="00082173",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )
    )

    assert bundle.candidates == ()
    assert len(bundle.debug_artifact_paths) == 2
    assert (tmp_path / "debug" / "ikyu_preview_last.html").exists()
    metadata = json.loads(
        (tmp_path / "debug" / "ikyu_preview_last_meta.json").read_text(encoding="utf-8")
    )
    assert metadata["site_name"] == "ikyu"
    assert metadata["seed_url"] == "https://www.ikyu.com/zh-tw/00082173/?cid=20260918&si=1&ppc=2&rc=1"
    assert any(diagnostic.stage == "debug_capture" for diagnostic in bundle.diagnostics)


class FakeIkyuHtmlClient(IkyuHtmlClient):
    """用 fixture 模擬依日期回傳不同 HTML 的測試 client。"""

    def fetch_search_page(self, draft: SearchDraft) -> str:
        """依草稿日期選擇對應的 fixture，模擬候選項重查。"""
        if draft.check_in_date == date(2026, 5, 1):
            return _read_fixture("available_basic.html")
        return _read_fixture("available_changed_date.html")

    def fetch_target_page(self, target: WatchTarget) -> str:
        """依正式 target 回傳對應的單一方案 fixture。"""
        if target.plan_id == "plan-1":
            return _read_fixture("available_basic.html")
        return _read_fixture("target_missing_basic.html")


class EmptyCandidateHtmlClient(IkyuHtmlClient):
    """回傳可讀取但無候選 offer 的頁面，用於驗證 debug capture。"""

    def fetch_search_page(self, draft: SearchDraft) -> HtmlFetchResult:
        """回傳空候選頁面與既有 diagnostics。"""
        html = """
        <script id="__IKYU_DATA__" type="application/json">
        {
          "hotel": {
            "id": "00082173",
            "name": "Debug Hotel",
            "canonical_url": "https://www.ikyu.com/zh-tw/00082173/"
          },
          "offers": []
        }
        </script>
        """
        return HtmlFetchResult(html=html)

    def fetch_target_page(self, target: WatchTarget) -> HtmlFetchResult:
        """本測試不使用 target snapshot。"""
        raise NotImplementedError


def _read_fixture(filename: str) -> str:
    """讀取 parser 測試用 HTML fixture。"""
    return (_FIXTURE_DIR / filename).read_text(encoding="utf-8")


def _read_expectation(filename: str) -> dict[str, object]:
    """讀取與 fixture 同名的期望值 JSON。"""
    return json.loads((_FIXTURE_DIR / filename).read_text(encoding="utf-8"))


def _build_target() -> WatchTarget:
    """建立 parser fixture 測試共用的 watch target。"""
    return WatchTarget(
        site="ikyu",
        hotel_id="hotel-123",
        room_id="room-1",
        plan_id="plan-1",
        check_in_date=date(2026, 5, 1),
        check_out_date=date(2026, 5, 3),
        people_count=2,
        room_count=1,
    )
