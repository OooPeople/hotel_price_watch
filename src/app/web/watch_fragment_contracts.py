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
class WatchDetailFragmentSection:
    """描述 watch detail 單一 fragment section 的 DOM 與 payload contract。"""

    name: str
    dom_id: str
    payload_key: str

    def to_client_config(self) -> dict[str, str]:
        """轉成 client script 可直接使用的 section 設定。"""
        return {
            "name": self.name,
            "domId": self.dom_id,
            "payloadKey": self.payload_key,
        }


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
WATCH_DETAIL_FRAGMENT_SECTIONS = (
    WatchDetailFragmentSection(
        name="hero",
        dom_id=WATCH_DETAIL_DOM_IDS.hero,
        payload_key=WATCH_DETAIL_PAYLOAD_KEYS.hero_section_html,
    ),
    WatchDetailFragmentSection(
        name="price_summary",
        dom_id=WATCH_DETAIL_DOM_IDS.price_summary,
        payload_key=WATCH_DETAIL_PAYLOAD_KEYS.price_summary_section_html,
    ),
    WatchDetailFragmentSection(
        name="price_trend",
        dom_id=WATCH_DETAIL_DOM_IDS.price_trend,
        payload_key=WATCH_DETAIL_PAYLOAD_KEYS.price_trend_section_html,
    ),
    WatchDetailFragmentSection(
        name="check_events",
        dom_id=WATCH_DETAIL_DOM_IDS.check_events,
        payload_key=WATCH_DETAIL_PAYLOAD_KEYS.check_events_section_html,
    ),
    WatchDetailFragmentSection(
        name="runtime_state_events",
        dom_id=WATCH_DETAIL_DOM_IDS.runtime_state_events,
        payload_key=WATCH_DETAIL_PAYLOAD_KEYS.runtime_state_events_section_html,
    ),
    WatchDetailFragmentSection(
        name="debug_artifacts",
        dom_id=WATCH_DETAIL_DOM_IDS.debug_artifacts,
        payload_key=WATCH_DETAIL_PAYLOAD_KEYS.debug_artifacts_section_html,
    ),
)
