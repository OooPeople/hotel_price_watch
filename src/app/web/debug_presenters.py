"""進階診斷頁使用的 presentation model。"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.debug_captures import DebugCaptureDetail, DebugCaptureSummary
from app.sites.base import LookupDiagnostic
from app.web.ui_presenters import BadgePresentation
from app.web.view_formatters import format_datetime_for_display


@dataclass(frozen=True, slots=True)
class DebugCaptureListRowPresentation:
    """描述 debug capture 列表的一列顯示資料。"""

    capture_id: str
    captured_at_text: str
    parsed_hotel_name: str
    candidate_count_text: str
    latest_status_badge: BadgePresentation
    seed_url: str


@dataclass(frozen=True, slots=True)
class DebugCaptureListPresentation:
    """集中 debug capture 列表頁摘要與表格資料。"""

    total_count: int
    candidate_total: int
    latest_status_badge: BadgePresentation
    rows: tuple[DebugCaptureListRowPresentation, ...]
    flash_message: str | None


@dataclass(frozen=True, slots=True)
class DebugDiagnosticRowPresentation:
    """描述 preview diagnostic 表格的一列資料。"""

    stage: str
    status: str
    detail_text: str


@dataclass(frozen=True, slots=True)
class DebugCaptureDetailPresentation:
    """集中單筆 debug capture 詳情頁所需顯示資料。"""

    capture_id: str
    captured_at_text: str
    capture_scope: str
    parsed_hotel_name: str
    latest_status_badge: BadgePresentation
    seed_url: str
    html_path_text: str
    metadata_path: str
    has_html: bool
    html_link_href: str | None
    html_preview: str
    metadata_json: str
    diagnostic_rows: tuple[DebugDiagnosticRowPresentation, ...]


def build_debug_capture_list_presentation(
    *,
    captures: tuple[DebugCaptureSummary, ...],
    flash_message: str | None = None,
    use_24_hour_time: bool,
) -> DebugCaptureListPresentation:
    """把 debug capture summaries 轉成列表頁 view model。"""
    latest_status = "n/a"
    if captures and captures[0].diagnostics:
        latest_status = captures[0].diagnostics[-1].status
    return DebugCaptureListPresentation(
        total_count=len(captures),
        candidate_total=sum(capture.candidate_count or 0 for capture in captures),
        latest_status_badge=_diagnostic_status_badge(latest_status),
        rows=tuple(
            _build_capture_list_row(
                capture,
                use_24_hour_time=use_24_hour_time,
            )
            for capture in captures
        ),
        flash_message=flash_message,
    )


def build_debug_capture_detail_presentation(
    *,
    capture: DebugCaptureDetail,
    use_24_hour_time: bool,
) -> DebugCaptureDetailPresentation:
    """把單筆 debug capture detail 轉成詳情頁 view model。"""
    latest_status = (
        capture.summary.diagnostics[-1].status
        if capture.summary.diagnostics
        else "n/a"
    )
    html_preview = (
        capture.html_content[:5000] if capture.html_content is not None else ""
    )
    html_link_href = (
        f"/debug/captures/{capture.summary.capture_id}/html"
        if capture.summary.html_path is not None
        else None
    )
    return DebugCaptureDetailPresentation(
        capture_id=capture.summary.capture_id,
        captured_at_text=format_datetime_for_display(
            capture.summary.captured_at_utc,
            use_24_hour_time=use_24_hour_time,
        ),
        capture_scope=capture.summary.capture_scope,
        parsed_hotel_name=capture.summary.parsed_hotel_name,
        latest_status_badge=_diagnostic_status_badge(latest_status),
        seed_url=capture.summary.seed_url,
        html_path_text=capture.summary.html_path or "未保存（成功摘要模式）",
        metadata_path=capture.summary.metadata_path,
        has_html=capture.html_content is not None,
        html_link_href=html_link_href,
        html_preview=html_preview,
        metadata_json=capture.metadata_json,
        diagnostic_rows=_build_diagnostic_rows(capture.summary.diagnostics),
    )


def _build_capture_list_row(
    capture: DebugCaptureSummary,
    *,
    use_24_hour_time: bool,
) -> DebugCaptureListRowPresentation:
    """把單筆 capture summary 轉成列表列 presentation。"""
    latest_status = capture.diagnostics[-1].status if capture.diagnostics else "n/a"
    return DebugCaptureListRowPresentation(
        capture_id=capture.capture_id,
        captured_at_text=format_datetime_for_display(
            capture.captured_at_utc,
            use_24_hour_time=use_24_hour_time,
        ),
        parsed_hotel_name=capture.parsed_hotel_name,
        candidate_count_text=(
            str(capture.candidate_count)
            if capture.candidate_count is not None
            else "unknown"
        ),
        latest_status_badge=_diagnostic_status_badge(latest_status),
        seed_url=capture.seed_url,
    )


def _build_diagnostic_rows(
    diagnostics: tuple[LookupDiagnostic, ...],
) -> tuple[DebugDiagnosticRowPresentation, ...]:
    """把 diagnostics 轉成表格列 presentation。"""
    return tuple(
        DebugDiagnosticRowPresentation(
            stage=diagnostic.stage,
            status=diagnostic.status,
            detail_text=(
                f"{diagnostic.detail} （冷卻 {diagnostic.cooldown_seconds:.0f} 秒）"
                if diagnostic.cooldown_seconds is not None
                else diagnostic.detail
            ),
        )
        for diagnostic in diagnostics
    )


def _diagnostic_status_badge(status: str) -> BadgePresentation:
    """依 diagnostic status 粗略決定 badge 顯示語意。"""
    if status == "success":
        return BadgePresentation(status, "success")
    if "error" in status or "failed" in status or "403" in status:
        return BadgePresentation(status, "danger")
    if "empty" in status or "waiting" in status or "cooldown" in status:
        return BadgePresentation(status, "warning")
    return BadgePresentation(status, "muted")
