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

    def for_browser_page_url(self, url: str) -> SiteAdapter:
        """依 browser page URL 找出可處理該分頁的站點 adapter。"""
        for adapter in self._adapters_by_name.values():
            if adapter.is_browser_page_url(url):
                return adapter
        raise LookupError(f"no adapter matched browser page URL: {url}")

    def adapters(self) -> tuple[SiteAdapter, ...]:
        """列出目前已註冊的 adapter，供 application 層做 capability 掃描。"""
        return tuple(self._adapters_by_name.values())

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters_by_name))
