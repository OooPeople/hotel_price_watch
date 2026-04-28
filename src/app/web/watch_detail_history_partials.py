"""watch detail 歷史、狀態事件與診斷 partial renderer。"""

from __future__ import annotations

from html import escape

from app.domain.entities import CheckEvent, DebugArtifact, RuntimeStateEvent
from app.web.ui_components import card, data_table, empty_state_card, status_badge, table_row
from app.web.watch_detail_presenters import (
    CheckEventRowPresentation,
    DebugArtifactRowPresentation,
    RuntimeStateEventRowPresentation,
    build_check_event_row_presentations,
    build_debug_artifact_row_presentations,
    build_runtime_state_event_row_presentations,
)


def render_check_events_section(check_events: tuple[CheckEvent, ...]) -> str:
    """渲染檢查歷史與錯誤摘要。"""
    return render_check_events_section_with_time_format(
        check_events,
        use_24_hour_time=True,
    )


def render_check_events_section_with_time_format(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染檢查歷史與錯誤摘要。"""
    return render_check_events_section_from_presentation(
        build_check_event_row_presentations(
            check_events,
            use_24_hour_time=use_24_hour_time,
        )
    )


def render_check_events_section_from_presentation(
    rows: tuple[CheckEventRowPresentation, ...],
) -> str:
    """依檢查歷史 presentation 渲染表格。"""
    if not rows:
        return empty_state_card(title="檢查歷史", message="目前尚無檢查歷史。")

    row_html = []
    for row in rows:
        row_html.append(
            table_row(
                (
                    escape(row.checked_at_text),
                    status_badge(
                        label=row.availability_badge.label,
                        kind=row.availability_badge.kind,
                    ),
                    escape(row.event_kind_text),
                    escape(row.price_text),
                    escape(row.error_text),
                    status_badge(
                        label=row.notification_badge.label,
                        kind=row.notification_badge.kind,
                    ),
                )
            )
        )

    return card(
        title="檢查歷史",
        body=data_table(
            headers=("時間", "空房狀態", "事件", "價格", "錯誤摘要", "通知結果"),
            rows_html="".join(row_html),
        ),
    )


def render_runtime_state_events_section(
    runtime_state_events: tuple[RuntimeStateEvent, ...],
) -> str:
    """渲染 watch 狀態轉移事件摘要，避免只靠檢查事件推論狀態變化。"""
    return render_runtime_state_events_section_with_time_format(
        runtime_state_events,
        use_24_hour_time=True,
    )


def render_runtime_state_events_section_with_time_format(
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染 watch 狀態轉移事件摘要。"""
    return render_runtime_state_events_section_from_presentation(
        build_runtime_state_event_row_presentations(
            runtime_state_events,
            use_24_hour_time=use_24_hour_time,
        )
    )


def render_runtime_state_events_section_from_presentation(
    rows: tuple[RuntimeStateEventRowPresentation, ...],
) -> str:
    """依 runtime state event presentation 渲染狀態事件表格。"""
    if not rows:
        return empty_state_card(
            title="狀態事件",
            message="目前尚無暫停、恢復或阻擋相關狀態事件。",
        )

    row_html = []
    for row in rows:
        row_html.append(
            table_row(
                (
                    escape(row.occurred_at_text),
                    escape(row.event_kind_text),
                    escape(row.from_state_text),
                    escape(row.to_state_text),
                    escape(row.detail_text),
                )
            )
        )
    return card(
        title="狀態事件",
        body=data_table(
            headers=("時間", "事件", "前狀態", "後狀態", "說明"),
            rows_html="".join(row_html),
        ),
    )


def render_debug_artifacts_section(debug_artifacts: tuple[DebugArtifact, ...]) -> str:
    """渲染與單一 watch item 關聯的診斷檔案摘要。"""
    return render_debug_artifacts_section_with_time_format(
        debug_artifacts,
        use_24_hour_time=True,
    )


def render_debug_artifacts_section_with_time_format(
    debug_artifacts: tuple[DebugArtifact, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染與單一 watch item 關聯的診斷檔案摘要。"""
    return render_debug_artifacts_section_from_presentation(
        build_debug_artifact_row_presentations(
            debug_artifacts,
            use_24_hour_time=use_24_hour_time,
        )
    )


def render_debug_artifacts_section_from_presentation(
    rows: tuple[DebugArtifactRowPresentation, ...],
) -> str:
    """依 debug artifact presentation 渲染診斷檔案表格。"""
    if not rows:
        return empty_state_card(
            title="診斷檔案",
            message="目前尚無背景監視診斷紀錄。",
            extra_html=(
                "<p>若要看建立監視 / preview 過程的診斷紀錄，"
                "請到首頁的進階診斷。</p>"
            ),
        )

    row_html = []
    for row in rows:
        row_html.append(
            table_row(
                (
                    escape(row.captured_at_text),
                    escape(row.reason_text),
                    escape(row.source_url_text),
                    escape(row.http_status_text),
                )
            )
        )

    return card(
        title="診斷檔案",
        body=f"""
        <p>
          這裡顯示背景監視期間保存的診斷紀錄，例如站方阻擋、
          可能節流或分頁被瀏覽器暫停。
        </p>
        <p>建立監視或解析問題請到首頁的進階診斷查看。</p>
        {data_table(
            headers=("時間", "原因", "來源頁面", "頁面狀態"),
            rows_html="".join(row_html),
        )}
        """,
    )
