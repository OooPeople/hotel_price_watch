"""Value objects used by the domain layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SearchDraft:
    """User-editable query input before it becomes a watch target."""

    seed_url: str
    check_in_date: date
    check_out_date: date
    people_count: int
    room_count: int
    hotel_id: str | None = None
    room_id: str | None = None
    plan_id: str | None = None


@dataclass(frozen=True, slots=True)
class WatchTarget:
    """Canonicalized target used by the monitor runtime."""

    site: str
    hotel_id: str
    room_id: str
    plan_id: str
    check_in_date: date
    check_out_date: date
    people_count: int
    room_count: int

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    def identity_key(self) -> tuple[str, str, str, str, date, date, int, int]:
        """Stable identity that intentionally excludes currency/display context."""
        return (
            self.site,
            self.hotel_id,
            self.room_id,
            self.plan_id,
            self.check_in_date,
            self.check_out_date,
            self.people_count,
            self.room_count,
        )
