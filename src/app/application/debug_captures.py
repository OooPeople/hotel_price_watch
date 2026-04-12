"""提供 GUI 使用的 preview debug capture 讀取邏輯。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.sites.base import LookupDiagnostic

DEBUG_CAPTURE_PREFIX = "ikyu_preview_"
DEBUG_CAPTURE_META_SUFFIX = "_meta.json"


@dataclass(frozen=True, slots=True)
class DebugCaptureSummary:
    """表示單筆 preview debug capture 的摘要資訊。"""

    capture_id: str
    capture_scope: str
    captured_at_utc: datetime | None
    seed_url: str
    parsed_hotel_name: str
    diagnostics: tuple[LookupDiagnostic, ...]
    html_path: str | None
    metadata_path: str
    candidate_count: int | None


@dataclass(frozen=True, slots=True)
class DebugCaptureDetail:
    """表示單筆 preview debug capture 的完整內容。"""

    summary: DebugCaptureSummary
    html_content: str | None
    metadata_json: str


@dataclass(frozen=True, slots=True)
class DebugCaptureClearResult:
    """表示清空 debug captures 後的刪除結果摘要。"""

    removed_count: int
    failed_paths: tuple[str, ...]


def list_debug_captures(debug_dir: str | Path = Path("debug")) -> tuple[DebugCaptureSummary, ...]:
    """列出目前 debug 目錄內所有可辨識的 preview capture。"""
    debug_path = Path(debug_dir)
    if not debug_path.exists():
        return ()

    summaries: list[DebugCaptureSummary] = []
    for meta_path in sorted(debug_path.glob(f"{DEBUG_CAPTURE_PREFIX}*{DEBUG_CAPTURE_META_SUFFIX}")):
        capture_id = _capture_id_from_meta_path(meta_path)
        if capture_id is None or capture_id == "last":
            continue
        summary = _load_capture_summary(meta_path)
        if summary is not None:
            summaries.append(summary)

    summaries.sort(
        key=lambda summary: (
            summary.captured_at_utc is not None,
            summary.captured_at_utc or datetime.min,
        ),
        reverse=True,
    )
    return tuple(summaries)


def load_latest_debug_capture(
    debug_dir: str | Path = Path("debug"),
) -> DebugCaptureDetail | None:
    """讀取最新一筆 preview debug capture。"""
    captures = list_debug_captures(debug_dir)
    if not captures:
        return None
    return load_debug_capture(captures[0].capture_id, debug_dir)


def load_debug_capture(
    capture_id: str,
    debug_dir: str | Path = Path("debug"),
) -> DebugCaptureDetail | None:
    """依 capture id 讀取指定的 preview debug capture。"""
    debug_path = Path(debug_dir)
    meta_path = debug_path / f"{capture_id}_meta.json"
    if not meta_path.exists():
        return None

    summary = _load_capture_summary(meta_path)
    if summary is None:
        return None

    html_content: str | None = None
    if summary.html_path is not None:
        html_path = Path(summary.html_path)
        if html_path.exists():
            html_content = html_path.read_text(encoding="utf-8")

    return DebugCaptureDetail(
        summary=summary,
        html_content=html_content,
        metadata_json=Path(summary.metadata_path).read_text(encoding="utf-8"),
    )


def clear_debug_captures(
    debug_dir: str | Path = Path("debug"),
) -> DebugCaptureClearResult:
    """清空目前 debug 目錄內所有 preview capture 檔案。"""
    debug_path = Path(debug_dir)
    if not debug_path.exists():
        return DebugCaptureClearResult(removed_count=0, failed_paths=())

    removed_count = 0
    failed_paths: list[str] = []
    patterns = (
        f"{DEBUG_CAPTURE_PREFIX}*.html",
        f"{DEBUG_CAPTURE_PREFIX}*{DEBUG_CAPTURE_META_SUFFIX}",
        f"{DEBUG_CAPTURE_PREFIX}last.html",
        f"{DEBUG_CAPTURE_PREFIX}last_meta.json",
    )
    for pattern in patterns:
        for file_path in debug_path.glob(pattern):
            try:
                file_path.unlink()
                removed_count += 1
            except OSError:
                failed_paths.append(str(file_path))
    return DebugCaptureClearResult(
        removed_count=removed_count,
        failed_paths=tuple(failed_paths),
    )


def _load_capture_summary(meta_path: Path) -> DebugCaptureSummary | None:
    """從 metadata 檔載入摘要，若格式不符則忽略該 capture。"""
    try:
        raw_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    html_path = raw_metadata.get("html_path")
    metadata_path = raw_metadata.get("metadata_path")
    seed_url = raw_metadata.get("seed_url")
    if html_path is not None and not isinstance(html_path, str):
        return None
    if not isinstance(metadata_path, str) or not isinstance(
        seed_url, str
    ):
        return None

    capture_id = _capture_id_from_meta_path(meta_path)
    if capture_id is None:
        return None

    return DebugCaptureSummary(
        capture_id=capture_id,
        capture_scope=str(raw_metadata.get("capture_scope", "preview")),
        captured_at_utc=_parse_optional_datetime(raw_metadata.get("captured_at_utc")),
        seed_url=seed_url,
        parsed_hotel_name=str(raw_metadata.get("parsed_hotel_name", "unknown hotel")),
        diagnostics=_parse_diagnostics(raw_metadata.get("diagnostics", [])),
        html_path=html_path,
        metadata_path=metadata_path,
        candidate_count=(
            int(raw_metadata["candidate_count"])
            if isinstance(raw_metadata.get("candidate_count"), int)
            else None
        ),
    )


def _capture_id_from_meta_path(meta_path: Path) -> str | None:
    """從 metadata 檔名推回 capture id。"""
    file_name = meta_path.name
    if not file_name.endswith(DEBUG_CAPTURE_META_SUFFIX):
        return None
    return file_name[: -len(DEBUG_CAPTURE_META_SUFFIX)]


def _parse_optional_datetime(raw_value: object) -> datetime | None:
    """把 metadata 內的 ISO 時間字串轉成 datetime。"""
    if not isinstance(raw_value, str) or not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def _parse_diagnostics(raw_items: object) -> tuple[LookupDiagnostic, ...]:
    """把 metadata 內的 diagnostics JSON 轉成 domain 共用模型。"""
    if not isinstance(raw_items, list):
        return ()

    diagnostics: list[LookupDiagnostic] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        stage = raw_item.get("stage")
        status = raw_item.get("status")
        detail = raw_item.get("detail")
        if not isinstance(stage, str) or not isinstance(status, str) or not isinstance(
            detail, str
        ):
            continue
        cooldown_seconds = raw_item.get("cooldown_seconds")
        diagnostics.append(
            LookupDiagnostic(
                stage=stage,
                status=status,
                detail=detail,
                cooldown_seconds=(
                    float(cooldown_seconds)
                    if isinstance(cooldown_seconds, (int, float))
                    else None
                ),
            )
        )
    return tuple(diagnostics)
