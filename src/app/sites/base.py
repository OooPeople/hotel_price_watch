"""Base adapter contract for supported booking sites."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities import PriceSnapshot
from app.domain.value_objects import SearchDraft, WatchTarget


@dataclass(frozen=True, slots=True)
class OfferCandidate:
    """Candidate room-plan pair surfaced to the watch editor."""

    room_id: str
    room_name: str
    plan_id: str
    plan_name: str


@dataclass(frozen=True, slots=True)
class CandidateBundle:
    """Candidate list returned from a site-specific lookup."""

    hotel_id: str
    hotel_name: str
    canonical_url: str
    candidates: tuple[OfferCandidate, ...]


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """Final editor selection used to create a canonical watch target."""

    room_id: str
    plan_id: str


class SiteAdapter(ABC):
    """Abstract contract used by application and monitor layers."""

    site_name: str

    @abstractmethod
    def match_url(self, url: str) -> bool:
        """Return whether this adapter supports the incoming seed URL."""

    @abstractmethod
    def parse_seed_url(self, url: str) -> SearchDraft:
        """Parse a raw URL into a site-agnostic draft."""

    @abstractmethod
    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        """Normalize draft fields before lookup or persistence."""

    @abstractmethod
    def fetch_candidates(self, draft: SearchDraft) -> CandidateBundle:
        """Return watchable room-plan candidates for the draft."""

    @abstractmethod
    def resolve_watch_target(
        self,
        draft: SearchDraft,
        selection: CandidateSelection,
    ) -> WatchTarget:
        """Build a canonical target from the chosen candidate."""

    @abstractmethod
    def fetch_target_snapshot(self, target: WatchTarget) -> PriceSnapshot:
        """Fetch one normalized snapshot for the canonical target."""
