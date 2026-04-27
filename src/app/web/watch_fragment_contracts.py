"""watch list / detail fragment payload 與 DOM hook contract。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WatchListDomIds:
    """首頁局部更新會使用的 DOM id。"""

    flash: str = "dashboard-flash-section"
    summary: str = "dashboard-summary-section"
    runtime: str = "runtime-status-section"
    watch_list: str = "watch-list-table-body"


@dataclass(frozen=True, slots=True)
class WatchListPayloadKeys:
    """首頁 fragment JSON payload 的固定欄位名稱。"""

    version: str = "version"
    flash_html: str = "flash_html"
    summary_html: str = "summary_html"
    runtime_html: str = "runtime_html"
    table_body_html: str = "table_body_html"


@dataclass(frozen=True, slots=True)
class WatchListFragmentPayload:
    """首頁局部更新回傳給前端的固定 payload schema。"""

    version: str
    flash_html: str
    summary_html: str
    runtime_html: str
    table_body_html: str

    def to_dict(self) -> dict[str, str]:
        """轉成 FastAPI JSONResponse 可直接序列化的 dict。"""
        keys = WATCH_LIST_PAYLOAD_KEYS
        return {
            keys.version: self.version,
            keys.flash_html: self.flash_html,
            keys.summary_html: self.summary_html,
            keys.runtime_html: self.runtime_html,
            keys.table_body_html: self.table_body_html,
        }


@dataclass(frozen=True, slots=True)
class WatchDetailDomIds:
    """watch 詳細頁局部更新會使用的 DOM id。"""

    hero: str = "watch-detail-hero-section"
    price_summary: str = "watch-detail-price-summary-section"
    price_trend: str = "watch-detail-price-trend-section"
    check_events: str = "watch-detail-check-events-section"
    runtime_state_events: str = "watch-detail-runtime-state-events-section"
    debug_artifacts: str = "watch-detail-debug-artifacts-section"


@dataclass(frozen=True, slots=True)
class WatchDetailPayloadKeys:
    """watch 詳細頁 fragment JSON payload 的固定欄位名稱。"""

    version: str = "version"
    hero_section_html: str = "hero_section_html"
    price_summary_section_html: str = "price_summary_section_html"
    price_trend_section_html: str = "price_trend_section_html"
    check_events_section_html: str = "check_events_section_html"
    runtime_state_events_section_html: str = "runtime_state_events_section_html"
    debug_artifacts_section_html: str = "debug_artifacts_section_html"


@dataclass(frozen=True, slots=True)
class WatchDetailFragmentPayload:
    """詳細頁局部更新回傳給前端的固定 payload schema。"""

    version: str
    sections: dict[str, str]

    def to_dict(self) -> dict[str, str]:
        """轉成 FastAPI JSONResponse 可直接序列化的 dict。"""
        return {WATCH_DETAIL_PAYLOAD_KEYS.version: self.version, **self.sections}


WATCH_LIST_DOM_IDS = WatchListDomIds()
WATCH_LIST_PAYLOAD_KEYS = WatchListPayloadKeys()
WATCH_DETAIL_DOM_IDS = WatchDetailDomIds()
WATCH_DETAIL_PAYLOAD_KEYS = WatchDetailPayloadKeys()
