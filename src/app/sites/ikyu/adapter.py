"""`ikyu` 站點專用 adapter。"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.domain.entities import PriceSnapshot, WatchItem
from app.domain.enums import SourceKind
from app.domain.value_objects import SearchDraft, WatchTarget
from app.sites.base import (
    CandidateBundle,
    CandidateLookupError,
    CandidateSelection,
    LookupDiagnostic,
    SiteAdapter,
)
from app.sites.ikyu.browser_matching import (
    extract_ikyu_browser_page_signature,
    ikyu_signature_matches_watch_target,
    ikyu_urls_match_confidently,
    is_ikyu_page_url,
)
from app.sites.ikyu.client import HtmlFetchResult, IkyuHtmlClient
from app.sites.ikyu.normalizer import (
    is_supported_ikyu_url,
    normalize_search_draft,
    parse_seed_url,
)
from app.sites.ikyu.parser import (
    parse_candidate_bundle,
    parse_target_snapshot_with_source,
)

DEBUG_CAPTURE_DIR = Path("debug")


class IkyuAdapter(SiteAdapter):
    """封裝 `ikyu` 站點的 URL 解析與後續查詢入口。"""

    site_name = "ikyu"

    def __init__(self, html_client: IkyuHtmlClient | None = None) -> None:
        """建立 adapter，並允許後續注入實際的 HTML 抓取實作。"""
        self._html_client = html_client

    def match_url(self, url: str) -> bool:
        """判斷是否由 `ikyu` adapter 負責處理此 seed URL。"""
        return is_supported_ikyu_url(url)

    def is_browser_page_url(self, url: str) -> bool:
        """判斷 Chrome 分頁 URL 是否屬於可建立 `ikyu` preview 的頁面。"""
        return is_ikyu_page_url(url)

    def browser_tab_matches_watch(
        self,
        *,
        tab_url: str,
        watch_item: WatchItem,
        draft: SearchDraft | None,
    ) -> bool:
        """判斷 `ikyu` 分頁是否對應到既有 watch target。"""
        if watch_item.target.site != self.site_name:
            return False
        if draft is not None and draft.browser_page_url is not None and (
            draft.browser_page_url == tab_url
            or ikyu_urls_match_confidently(
                left_url=draft.browser_page_url,
                right_url=tab_url,
            )
        ):
            return True
        if ikyu_urls_match_confidently(
            left_url=watch_item.canonical_url,
            right_url=tab_url,
        ):
            return True
        return ikyu_signature_matches_watch_target(
            signature=extract_ikyu_browser_page_signature(tab_url),
            target=watch_item.target,
        )

    def parse_seed_url(self, url: str) -> SearchDraft:
        """將原始 `ikyu` URL 轉成可供 editor 使用的查詢草稿。"""
        return parse_seed_url(url)

    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        """套用 `ikyu` 規則驗證並正規化草稿欄位。"""
        return normalize_search_draft(draft)

    def fetch_candidates(self, draft: SearchDraft) -> CandidateBundle:
        """依查詢草稿重新抓取候選房型方案。"""
        normalized_draft = self.normalize_search_draft(draft)
        if not normalized_draft.is_ready_for_candidate_lookup():
            raise ValueError("search draft is incomplete for candidate lookup")
        if self._html_client is None:
            raise NotImplementedError("ikyu html client is not configured")
        try:
            fetch_result = self._html_client.fetch_search_page(normalized_draft)
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            raise CandidateLookupError(
                str(exc),
                diagnostics=diagnostics,
            ) from exc

        normalized_fetch_result = _normalize_fetch_result(fetch_result)
        candidate_bundle = parse_candidate_bundle(normalized_fetch_result.html)
        parser_diagnostic = _build_candidate_parse_diagnostic(candidate_bundle)
        diagnostics = normalized_fetch_result.diagnostics + (parser_diagnostic,)
        debug_artifact_paths = _capture_preview_debug_summary(
            draft=normalized_draft,
            fetch_result=normalized_fetch_result,
            candidate_bundle=replace(candidate_bundle, diagnostics=diagnostics),
            include_html=not candidate_bundle.candidates,
        )
        if not candidate_bundle.candidates:
            diagnostics = diagnostics + (
                LookupDiagnostic(
                    stage="debug_capture",
                    status="saved",
                    detail=(
                        "已自動保存本次真實頁面 HTML，供後續修正 parser。"
                        f" HTML：{debug_artifact_paths[0]}，Metadata：{debug_artifact_paths[1]}"
                    ),
                ),
            )
        return replace(
            candidate_bundle,
            diagnostics=diagnostics,
            debug_artifact_paths=debug_artifact_paths,
        )

    def resolve_watch_target(
        self,
        draft: SearchDraft,
        selection: CandidateSelection,
    ) -> WatchTarget:
        """把已預填完成的草稿與選擇結果轉成正式 watch target。"""
        normalized_draft = self.normalize_search_draft(draft)
        if not normalized_draft.is_ready_for_candidate_lookup():
            raise ValueError("search draft is incomplete for watch target resolution")
        if normalized_draft.hotel_id is None:
            raise ValueError("hotel_id is required for watch target resolution")
        if normalized_draft.check_in_date is None or normalized_draft.check_out_date is None:
            raise ValueError("date range is required for watch target resolution")
        if normalized_draft.people_count is None or normalized_draft.room_count is None:
            raise ValueError("occupancy is required for watch target resolution")

        room_id = selection.room_id.strip()
        plan_id = selection.plan_id.strip()
        if not room_id or not plan_id:
            raise ValueError("room_id and plan_id must not be blank")

        return WatchTarget(
            site=self.site_name,
            hotel_id=normalized_draft.hotel_id,
            room_id=room_id,
            plan_id=plan_id,
            check_in_date=normalized_draft.check_in_date,
            check_out_date=normalized_draft.check_out_date,
            people_count=normalized_draft.people_count,
            room_count=normalized_draft.room_count,
        )

    def build_preview_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        diagnostics: tuple[LookupDiagnostic, ...] = (),
    ) -> tuple[SearchDraft, CandidateBundle]:
        """直接以已開啟的瀏覽器分頁內容建立 editor preview。"""
        draft = self.parse_seed_url(page_url)
        candidate_bundle = parse_candidate_bundle(html)
        parser_diagnostic = _build_candidate_parse_diagnostic(candidate_bundle)
        combined_diagnostics = diagnostics + (parser_diagnostic,)
        debug_artifact_paths = _capture_preview_debug_summary(
            draft=draft,
            fetch_result=HtmlFetchResult(html=html, diagnostics=combined_diagnostics),
            candidate_bundle=replace(candidate_bundle, diagnostics=combined_diagnostics),
            include_html=not candidate_bundle.candidates,
        )
        if not candidate_bundle.candidates:
            combined_diagnostics = combined_diagnostics + (
                LookupDiagnostic(
                    stage="debug_capture",
                    status="saved",
                    detail=(
                        "已自動保存本次真實頁面 HTML，供後續修正 parser。"
                        f" HTML：{debug_artifact_paths[0]}，Metadata：{debug_artifact_paths[1]}"
                    ),
                ),
            )
        return (
            draft,
            replace(
                candidate_bundle,
                canonical_url=candidate_bundle.canonical_url or page_url,
                diagnostics=combined_diagnostics,
                debug_artifact_paths=debug_artifact_paths,
            ),
        )

    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        """直接以已附著 Chrome 分頁內容建立單次價格快照。"""
        return parse_target_snapshot_with_source(
            html,
            target,
            source_kind=SourceKind.BROWSER,
        )


def _build_candidate_parse_diagnostic(candidate_bundle: CandidateBundle) -> LookupDiagnostic:
    """把候選解析結果整理成可供 GUI 顯示的診斷資訊。"""
    if candidate_bundle.candidates:
        return LookupDiagnostic(
            stage="candidate_parse",
            status="success",
            detail=f"成功解析出 {len(candidate_bundle.candidates)} 筆候選房型方案。",
        )

    return LookupDiagnostic(
        stage="candidate_parse",
        status="empty",
        detail="頁面已取得，但目前未解析出可建立的候選方案。",
    )


def _normalize_fetch_result(fetch_result: HtmlFetchResult | str) -> HtmlFetchResult:
    """讓舊式測試替身回傳裸字串時，仍可轉成統一結果模型。"""
    if isinstance(fetch_result, HtmlFetchResult):
        return fetch_result
    return HtmlFetchResult(html=fetch_result)


def _capture_preview_debug_summary(
    *,
    draft: SearchDraft,
    fetch_result: HtmlFetchResult,
    candidate_bundle: CandidateBundle,
    include_html: bool,
) -> tuple[str, str]:
    """保存本次 preview 的 debug 摘要，必要時再附帶完整 HTML。"""
    DEBUG_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    capture_stem = f"{IkyuAdapter.site_name}_preview_{timestamp}"
    captured_html_path = DEBUG_CAPTURE_DIR / f"{capture_stem}.html"
    captured_meta_path = DEBUG_CAPTURE_DIR / f"{capture_stem}_meta.json"
    html_path = DEBUG_CAPTURE_DIR / f"{IkyuAdapter.site_name}_preview_last.html"
    meta_path = DEBUG_CAPTURE_DIR / f"{IkyuAdapter.site_name}_preview_last_meta.json"

    stored_html_path: str | None = None
    latest_html_path: str | None = None
    if include_html:
        captured_html_path.write_text(fetch_result.html, encoding="utf-8")
        html_path.write_text(fetch_result.html, encoding="utf-8")
        stored_html_path = str(captured_html_path)
        latest_html_path = str(html_path)

    metadata = {
        "site_name": IkyuAdapter.site_name,
        "capture_scope": "preview",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed_url": draft.seed_url,
        "hotel_id": draft.hotel_id,
        "check_in_date": (
            draft.check_in_date.isoformat() if draft.check_in_date is not None else None
        ),
        "check_out_date": (
            draft.check_out_date.isoformat() if draft.check_out_date is not None else None
        ),
        "people_count": draft.people_count,
        "room_count": draft.room_count,
        "prefilled_room_id": draft.room_id,
        "prefilled_plan_id": draft.plan_id,
        "parsed_hotel_name": candidate_bundle.hotel_name,
        "candidate_count": len(candidate_bundle.candidates),
        "html_saved": include_html,
        "diagnostics": [
            {
                "stage": diagnostic.stage,
                "status": diagnostic.status,
                "detail": diagnostic.detail,
                "cooldown_seconds": diagnostic.cooldown_seconds,
            }
            for diagnostic in candidate_bundle.diagnostics
        ],
        "html_path": stored_html_path,
        "metadata_path": str(captured_meta_path),
    }
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    captured_meta_path.write_text(
        metadata_json,
        encoding="utf-8",
    )
    metadata["html_path"] = latest_html_path
    metadata["metadata_path"] = str(meta_path)
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return (str(html_path), str(meta_path))
