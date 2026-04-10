"""Registry for looking up site adapters by URL or site name."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.sites.base import SiteAdapter


@dataclass(slots=True)
class SiteRegistry:
    """In-memory registry used by the UI and application layer."""

    _adapters_by_name: dict[str, SiteAdapter] = field(default_factory=dict)

    def register(self, adapter: SiteAdapter) -> None:
        if adapter.site_name in self._adapters_by_name:
            raise ValueError(f"adapter already registered: {adapter.site_name}")
        self._adapters_by_name[adapter.site_name] = adapter

    def get(self, site_name: str) -> SiteAdapter:
        try:
            return self._adapters_by_name[site_name]
        except KeyError as exc:
            raise LookupError(f"unknown site adapter: {site_name}") from exc

    def for_url(self, url: str) -> SiteAdapter:
        for adapter in self._adapters_by_name.values():
            if adapter.match_url(url):
                return adapter
        raise LookupError(f"no adapter matched URL: {url}")

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters_by_name))
