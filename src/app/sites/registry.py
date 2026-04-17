"""提供站點 adapter 的註冊與查找入口。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.sites.base import SiteAdapter, SiteDescriptor


@dataclass(slots=True)
class SiteRegistry:
    """提供 UI 與 application layer 使用的站點 adapter registry。"""

    _adapters_by_name: dict[str, SiteAdapter] = field(default_factory=dict)

    def register(self, adapter: SiteAdapter) -> None:
        """註冊單一站點 adapter，並避免同名站點重複覆蓋。"""
        if adapter.site_name in self._adapters_by_name:
            raise ValueError(f"adapter already registered: {adapter.site_name}")
        self._adapters_by_name[adapter.site_name] = adapter

    def get(self, site_name: str) -> SiteAdapter:
        """依 site name 取得已註冊的 adapter。"""
        try:
            return self._adapters_by_name[site_name]
        except KeyError as exc:
            raise LookupError(f"unknown site adapter: {site_name}") from exc

    def for_url(self, url: str) -> SiteAdapter:
        """依一般 seed URL 找出可處理的站點 adapter。"""
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

    def descriptors(self) -> tuple[SiteDescriptor, ...]:
        """列出目前已註冊站點的 metadata，供 UI 呈現與能力判斷使用。"""
        return tuple(adapter.descriptor for adapter in self._adapters_by_name.values())

    def descriptor_for_browser_page_url(self, url: str) -> SiteDescriptor:
        """依 browser page URL 找出對應站點的 metadata。"""
        return self.for_browser_page_url(url).descriptor

    def default_descriptor(self) -> SiteDescriptor:
        """回傳目前預設站點 metadata；V1 只有單站時用於錯誤頁兜底。"""
        try:
            return next(iter(self._adapters_by_name.values())).descriptor
        except StopIteration as exc:
            raise LookupError("no site adapter registered") from exc

    def names(self) -> tuple[str, ...]:
        """列出目前已註冊的 site name。"""
        return tuple(sorted(self._adapters_by_name))
