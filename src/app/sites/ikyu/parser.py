"""解析 `ikyu` fixture 或頁面內容中的候選方案與價格資訊。"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from app.domain.enums import Availability, SourceKind
from app.domain.value_objects import WatchTarget
from app.sites.base import CandidateBundle, OfferCandidate
from app.sites.ikyu.models import ParsedPriceSnapshot

_PAYLOAD_PATTERN = re.compile(
    r'<script id="__IKYU_DATA__" type="application/json">\s*(?P<payload>.*?)\s*</script>',
    re.DOTALL,
)
_JSON_LD_PATTERN = re.compile(
    r'<script type="application/ld\+json">\s*(?P<payload>.*?)\s*</script>',
    re.DOTALL,
)


def parse_candidate_bundle(html: str) -> CandidateBundle:
    """從頁面內嵌資料解析可供 watch editor 使用的候選方案。"""
    try:
        payload = _extract_payload(html)
    except ValueError:
        return _parse_candidate_bundle_from_json_ld(html)

    hotel = payload.get("hotel")
    if not isinstance(hotel, dict):
        return _empty_candidate_bundle()

    offers = payload.get("offers", [])
    if not isinstance(offers, list):
        return _empty_candidate_bundle(
            hotel_id=_optional_string(hotel.get("id")) or "",
            hotel_name=_optional_string(hotel.get("name")) or "unknown hotel",
            canonical_url=_optional_string(hotel.get("canonical_url")) or "",
        )

    parsed_offers = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        candidate = _offer_to_candidate(offer)
        if candidate is not None:
            parsed_offers.append(candidate)

    return CandidateBundle(
        hotel_id=_optional_string(hotel.get("id")) or "",
        hotel_name=_optional_string(hotel.get("name")) or "unknown hotel",
        canonical_url=_optional_string(hotel.get("canonical_url")) or "",
        candidates=tuple(parsed_offers),
    )


def parse_target_snapshot(html: str, target: WatchTarget) -> ParsedPriceSnapshot:
    """依據指定的 `WatchTarget` 解析對應房型方案的價格快照。"""
    return parse_target_snapshot_with_source(
        html,
        target,
        source_kind=SourceKind.HTTP,
    )


def parse_target_snapshot_with_source(
    html: str,
    target: WatchTarget,
    *,
    source_kind: SourceKind,
) -> ParsedPriceSnapshot:
    """依來源型別解析對應房型方案的價格快照。"""
    try:
        payload = _extract_payload(html)
    except ValueError:
        return _parse_target_snapshot_from_json_ld(
            html,
            target,
            source_kind=source_kind,
        )

    offers = payload.get("offers", [])
    if not isinstance(offers, list):
        return _parse_error_snapshot()

    for offer in offers:
        if not isinstance(offer, dict):
            continue
        room_id = _optional_string(offer.get("room_id"))
        plan_id = _optional_string(offer.get("plan_id"))
        if room_id != target.room_id or plan_id != target.plan_id:
            continue

        availability = _parse_availability(offer.get("availability"))
        if availability is None:
            return _parse_error_snapshot()

        price = offer.get("price") or {}
        if not isinstance(price, dict):
            return _parse_error_snapshot()

        return ParsedPriceSnapshot(
            display_price_text=_optional_string(price.get("display_text")),
            normalized_price_amount=_optional_decimal(price.get("normalized_amount")),
            currency=_optional_string(price.get("currency")),
            availability=availability,
            source_kind=source_kind,
        )

    return ParsedPriceSnapshot(
        display_price_text=None,
        normalized_price_amount=None,
        currency=None,
        availability=Availability.TARGET_MISSING,
        source_kind=source_kind,
    )


def _extract_payload(html: str) -> dict[str, object]:
    """從 HTML 中抽出固定 script tag 內的 JSON payload。"""
    matched = _PAYLOAD_PATTERN.search(html)
    if matched is None:
        raise ValueError("ikyu payload script not found")
    try:
        payload = json.loads(matched.group("payload"))
    except json.JSONDecodeError as exc:
        raise ValueError("ikyu payload is not valid json") from exc

    if not isinstance(payload, dict):
        raise ValueError("ikyu payload root must be an object")
    return payload


def _offer_to_candidate(offer: dict[str, object]) -> OfferCandidate | None:
    """把站點 offer 資料轉成站點無關的候選方案物件。"""
    room_id = _optional_string(offer.get("room_id"))
    room_name = _optional_string(offer.get("room_name"))
    plan_id = _optional_string(offer.get("plan_id"))
    plan_name = _optional_string(offer.get("plan_name"))
    if None in {room_id, room_name, plan_id, plan_name}:
        return None
    price = offer.get("price") or {}
    display_price_text = None
    normalized_price_amount = None
    currency = None
    if isinstance(price, dict):
        display_price_text = _optional_string(price.get("display_text"))
        normalized_price_amount = _optional_decimal(price.get("normalized_amount"))
        currency = _optional_string(price.get("currency"))

    return OfferCandidate(
        room_id=room_id,
        room_name=room_name,
        plan_id=plan_id,
        plan_name=plan_name,
        display_price_text=display_price_text,
        normalized_price_amount=normalized_price_amount,
        currency=currency,
    )


def _optional_decimal(raw_value: object) -> Decimal | None:
    """將 payload 內的價格欄位安全轉成 `Decimal`。"""
    if raw_value is None:
        return None
    return Decimal(str(raw_value))


def _optional_string(raw_value: object) -> str | None:
    """將 payload 欄位轉成去空白字串；空值則回傳 `None`。"""
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


def _parse_availability(raw_value: object) -> Availability | None:
    """把 payload 內的 availability 字串安全轉成列舉。"""
    normalized = _optional_string(raw_value)
    if normalized is None:
        return None
    try:
        return Availability(normalized)
    except ValueError:
        return None


def _parse_error_snapshot() -> ParsedPriceSnapshot:
    """建立 parser 無法穩定解析時回傳的降級快照。"""
    return ParsedPriceSnapshot(
        display_price_text=None,
        normalized_price_amount=None,
        currency=None,
        availability=Availability.PARSE_ERROR,
        source_kind=SourceKind.HTTP,
    )


def _parse_candidate_bundle_from_json_ld(html: str) -> CandidateBundle:
    """從 `schema.org Hotel` 的 JSON-LD 降級解析單一候選方案。"""
    hotel_schema = _extract_hotel_schema_json_ld(html)
    if hotel_schema is None:
        return _empty_candidate_bundle()

    room_schema = _extract_contains_place(hotel_schema)
    if room_schema is None:
        return _empty_candidate_bundle(
            hotel_id=_optional_string(hotel_schema.get("identifier")) or "",
            hotel_name=_optional_string(hotel_schema.get("name")) or "unknown hotel",
            canonical_url=_optional_string(hotel_schema.get("url")) or "",
        )

    room_id = _optional_string(room_schema.get("identifier"))
    room_name = _optional_string(room_schema.get("name"))
    offer_schema = room_schema.get("offers")
    if not isinstance(offer_schema, dict):
        return _empty_candidate_bundle(
            hotel_id=_optional_string(hotel_schema.get("identifier")) or "",
            hotel_name=_optional_string(hotel_schema.get("name")) or "unknown hotel",
            canonical_url=_optional_string(hotel_schema.get("url")) or "",
        )
    plan_id = _optional_string(offer_schema.get("identifier"))
    if None in {room_id, room_name, plan_id}:
        return _empty_candidate_bundle(
            hotel_id=_optional_string(hotel_schema.get("identifier")) or "",
            hotel_name=_optional_string(hotel_schema.get("name")) or "unknown hotel",
            canonical_url=_optional_string(hotel_schema.get("url")) or "",
        )

    return CandidateBundle(
        hotel_id=_optional_string(hotel_schema.get("identifier")) or "",
        hotel_name=_optional_string(hotel_schema.get("name")) or "unknown hotel",
        canonical_url=_optional_string(hotel_schema.get("url")) or "",
        candidates=(
            OfferCandidate(
                room_id=room_id,
                room_name=room_name,
                plan_id=plan_id,
                plan_name=_optional_string(offer_schema.get("name")) or f"已選方案 {plan_id}",
                display_price_text=_build_schema_price_display_text(offer_schema),
                normalized_price_amount=_optional_decimal(offer_schema.get("price")),
                currency=_optional_string(offer_schema.get("priceCurrency")),
            ),
        ),
    )


def _parse_target_snapshot_from_json_ld(
    html: str,
    target: WatchTarget,
    *,
    source_kind: SourceKind,
) -> ParsedPriceSnapshot:
    """從 `schema.org Hotel` 的 JSON-LD 降級解析單一方案快照。"""
    hotel_schema = _extract_hotel_schema_json_ld(html)
    if hotel_schema is None:
        return _parse_error_snapshot()

    room_schema = _extract_contains_place(hotel_schema)
    if room_schema is None:
        return _parse_error_snapshot()

    room_id = _optional_string(room_schema.get("identifier"))
    offer_schema = room_schema.get("offers")
    if room_id != target.room_id or not isinstance(offer_schema, dict):
        return ParsedPriceSnapshot(
            display_price_text=None,
            normalized_price_amount=None,
            currency=None,
            availability=Availability.TARGET_MISSING,
            source_kind=source_kind,
        )

    plan_id = _optional_string(offer_schema.get("identifier"))
    if plan_id != target.plan_id:
        return ParsedPriceSnapshot(
            display_price_text=None,
            normalized_price_amount=None,
            currency=None,
            availability=Availability.TARGET_MISSING,
            source_kind=source_kind,
        )

    amount = _optional_decimal(offer_schema.get("price"))
    currency = _optional_string(offer_schema.get("priceCurrency"))
    availability = _parse_schema_availability(offer_schema.get("availability"))
    if amount is None or currency is None or availability is None:
        return _parse_error_snapshot()

    return ParsedPriceSnapshot(
        display_price_text=f"{currency} {amount}",
        normalized_price_amount=amount,
        currency=currency,
        availability=availability,
        source_kind=source_kind,
    )


def _extract_hotel_schema_json_ld(html: str) -> dict[str, object] | None:
    """找出頁面中的 `Hotel` JSON-LD 區塊。"""
    for matched in _JSON_LD_PATTERN.finditer(html):
        try:
            payload = json.loads(matched.group("payload"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and _is_hotel_schema(payload):
            return payload
    return None


def _is_hotel_schema(payload: dict[str, object]) -> bool:
    """判斷 JSON-LD payload 是否為 `Hotel` 結構。"""
    schema_type = payload.get("@type")
    if isinstance(schema_type, str):
        return schema_type == "Hotel"
    if isinstance(schema_type, list):
        return "Hotel" in schema_type
    return False


def _extract_contains_place(hotel_schema: dict[str, object]) -> dict[str, object] | None:
    """從 `Hotel` JSON-LD 取出對應房型區塊。"""
    contains_place = hotel_schema.get("containsPlace")
    if isinstance(contains_place, dict):
        return contains_place
    if isinstance(contains_place, list):
        for item in contains_place:
            if isinstance(item, dict):
                return item
    return None


def _parse_schema_availability(raw_value: object) -> Availability | None:
    """把 `schema.org` availability URL 轉成系統內部列舉。"""
    normalized = _optional_string(raw_value)
    if normalized is None:
        return None
    if normalized.endswith("/InStock"):
        return Availability.AVAILABLE
    if normalized.endswith("/SoldOut") or normalized.endswith("/OutOfStock"):
        return Availability.SOLD_OUT
    return None


def _build_schema_price_display_text(offer_schema: dict[str, object]) -> str | None:
    """把 JSON-LD 內的價格欄位轉成適合 UI 顯示的字串。"""
    amount = _optional_decimal(offer_schema.get("price"))
    currency = _optional_string(offer_schema.get("priceCurrency"))
    if amount is None or currency is None:
        return None
    return f"{currency} {_format_decimal_for_display(amount)}"


def _format_decimal_for_display(amount: Decimal) -> str:
    """把 Decimal 轉成不帶多餘尾零的顯示字串。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")


def _empty_candidate_bundle(
    *,
    hotel_id: str = "",
    hotel_name: str = "unknown hotel",
    canonical_url: str = "",
) -> CandidateBundle:
    """建立候選解析失敗時使用的空結果。"""
    return CandidateBundle(
        hotel_id=hotel_id,
        hotel_name=hotel_name,
        canonical_url=canonical_url,
        candidates=(),
    )
