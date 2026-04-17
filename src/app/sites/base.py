"""支援站點共用的 adapter 契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from app.domain.entities import PriceSnapshot, WatchItem
from app.domain.value_objects import SearchDraft, WatchTarget


@dataclass(frozen=True, slots=True)
class OfferCandidate:
    """表示 watch editor 可選的房型與方案組合。"""

    room_id: str
    room_name: str
    plan_id: str
    plan_name: str
    display_price_text: str | None = None
    normalized_price_amount: Decimal | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateBundle:
    """表示站點查詢後回傳的一組候選方案。"""

    hotel_id: str
    hotel_name: str
    canonical_url: str
    candidates: tuple[OfferCandidate, ...]
    diagnostics: tuple["LookupDiagnostic", ...] = ()
    debug_artifact_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LookupDiagnostic:
    """表示單次候選查詢流程中的一個診斷步驟。"""

    stage: str
    status: str
    detail: str
    cooldown_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """表示使用者在 editor 中最後選定的候選項。"""

    room_id: str
    plan_id: str


class CandidateLookupError(ValueError):
    """表示候選查詢失敗，並攜帶可供 GUI 顯示的診斷資訊。"""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: tuple[LookupDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class SiteAdapter(ABC):
    """定義 application 與 monitor 共同依賴的站點介面。"""

    site_name: str

    @abstractmethod
    def match_url(self, url: str) -> bool:
        """判斷目前 adapter 是否支援這個 seed URL。"""

    @abstractmethod
    def parse_seed_url(self, url: str) -> SearchDraft:
        """將原始 URL 解析為站點無關的查詢草稿。"""

    @abstractmethod
    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        """在查詢或儲存前驗證並正規化草稿欄位。"""

    @abstractmethod
    def fetch_candidates(self, draft: SearchDraft) -> CandidateBundle:
        """依查詢草稿抓取可監看的候選房型方案。"""

    @abstractmethod
    def build_preview_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        diagnostics: tuple[LookupDiagnostic, ...] = (),
    ) -> tuple[SearchDraft, CandidateBundle]:
        """直接以已附著 Chrome 分頁內容建立 watch editor preview。"""

    @abstractmethod
    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        """直接以已附著 Chrome 分頁內容建立單次價格快照。"""

    @abstractmethod
    def resolve_watch_target(
        self,
        draft: SearchDraft,
        selection: CandidateSelection,
    ) -> WatchTarget:
        """依草稿與使用者選擇建立正式的 canonical target。"""

    def is_browser_page_url(self, url: str) -> bool:
        """判斷 Chrome 分頁 URL 是否屬於此站點可處理範圍。"""
        return self.match_url(url)

    def browser_tab_matches_watch(
        self,
        *,
        tab_url: str,
        watch_item: WatchItem,
        draft: SearchDraft | None,
    ) -> bool:
        """判斷 Chrome 分頁是否已對應指定 watch，站點可覆寫精確規則。"""
        if watch_item.target.site != self.site_name:
            return False
        if draft is not None and draft.browser_page_url == tab_url:
            return True
        return watch_item.canonical_url == tab_url
