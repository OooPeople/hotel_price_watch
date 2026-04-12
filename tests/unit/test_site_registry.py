from datetime import date
from decimal import Decimal

import pytest

from app.domain.entities import PriceSnapshot
from app.domain.enums import Availability, SourceKind
from app.domain.value_objects import SearchDraft, WatchTarget
from app.sites.base import CandidateBundle, CandidateSelection, OfferCandidate, SiteAdapter
from app.sites.registry import SiteRegistry


class DummyAdapter(SiteAdapter):
    site_name = "dummy"

    def match_url(self, url: str) -> bool:
        return url.startswith("https://dummy.example/")

    def parse_seed_url(self, url: str) -> SearchDraft:
        return SearchDraft(
            seed_url=url,
            check_in_date=date(2026, 4, 20),
            check_out_date=date(2026, 4, 21),
            people_count=2,
            room_count=1,
            hotel_id="hotel-1",
        )

    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        return draft

    def fetch_candidates(self, draft: SearchDraft) -> CandidateBundle:
        return CandidateBundle(
            hotel_id="hotel-1",
            hotel_name="Dummy Hotel",
            canonical_url="https://dummy.example/hotel-1",
            candidates=(
                OfferCandidate(
                    room_id="room-1",
                    room_name="Room 1",
                    plan_id="plan-1",
                    plan_name="Plan 1",
                ),
            ),
        )

    def build_preview_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        diagnostics=(),
    ) -> tuple[SearchDraft, CandidateBundle]:
        return self.parse_seed_url(page_url), self.fetch_candidates(self.parse_seed_url(page_url))

    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        del page_url, html, target
        return PriceSnapshot(
            display_price_text="JPY 20,000",
            normalized_price_amount=Decimal("20000"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        )

    def resolve_watch_target(
        self,
        draft: SearchDraft,
        selection: CandidateSelection,
    ) -> WatchTarget:
        return WatchTarget(
            site=self.site_name,
            hotel_id=draft.hotel_id or "hotel-1",
            room_id=selection.room_id,
            plan_id=selection.plan_id,
            check_in_date=draft.check_in_date,
            check_out_date=draft.check_out_date,
            people_count=draft.people_count,
            room_count=draft.room_count,
        )


def test_registry_matches_adapter_by_url() -> None:
    registry = SiteRegistry()
    registry.register(DummyAdapter())

    adapter = registry.for_url("https://dummy.example/hotel-1")

    assert adapter.site_name == "dummy"


def test_registry_rejects_duplicate_site_names() -> None:
    registry = SiteRegistry()
    registry.register(DummyAdapter())

    with pytest.raises(ValueError):
        registry.register(DummyAdapter())
