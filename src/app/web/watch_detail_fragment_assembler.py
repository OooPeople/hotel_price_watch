"""Watch Detail fragment section registry 與 HTML assembler。"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    RuntimeStateEvent,
    WatchItem,
)
from app.web.watch_detail_history_partials import (
    render_check_events_section_from_presentation,
    render_debug_artifacts_section_from_presentation,
    render_runtime_state_events_section_from_presentation,
)
from app.web.watch_detail_presenters import (
    WatchDetailPageViewModel,
    build_watch_detail_page_view_model,
)
from app.web.watch_detail_summary_partials import (
    render_watch_detail_hero_section,
    render_watch_price_summary_cards,
)
from app.web.watch_detail_trend_partials import (
    render_price_trend_section_from_presentation,
)
from app.web.watch_fragment_contracts import WATCH_DETAIL_FRAGMENT_SECTIONS

DetailSectionRenderer = Callable[[WatchDetailPageViewModel, bool], str]


def render_watch_detail_sections(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    check_events: tuple[CheckEvent, ...],
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
    runtime_state_events: tuple[RuntimeStateEvent, ...],
    use_24_hour_time: bool = True,
) -> dict[str, str]:
    """依 detail context 建立 polling payload 使用的 section HTML。"""
    view_model = build_watch_detail_page_view_model(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
        check_events=check_events,
        notification_state=notification_state,
        debug_artifacts=debug_artifacts,
        runtime_state_events=runtime_state_events,
        use_24_hour_time=use_24_hour_time,
    )
    return render_watch_detail_sections_from_view_model(
        view_model,
        use_24_hour_time=use_24_hour_time,
    )


def render_watch_detail_sections_from_view_model(
    view_model: WatchDetailPageViewModel,
    *,
    use_24_hour_time: bool,
) -> dict[str, str]:
    """依 section registry 組出 detail fragment payload 的 HTML map。"""
    renderers = _detail_section_renderers()
    return {
        section.payload_key: renderers[section.name](view_model, use_24_hour_time)
        for section in WATCH_DETAIL_FRAGMENT_SECTIONS
    }


def _detail_section_renderers() -> dict[str, DetailSectionRenderer]:
    """集中定義 detail section name 與 renderer 的對應關係。"""
    return {
        "hero": _render_hero_section,
        "price_summary": _render_price_summary_section,
        "price_trend": _render_price_trend_section,
        "check_events": _render_check_events_section,
        "runtime_state_events": _render_runtime_state_events_section,
        "debug_artifacts": _render_debug_artifacts_section,
    }


def _render_hero_section(
    view_model: WatchDetailPageViewModel,
    use_24_hour_time: bool,
) -> str:
    """渲染 detail hero section。"""
    return render_watch_detail_hero_section(
        presentation=view_model.summary,
        use_24_hour_time=use_24_hour_time,
    )


def _render_price_summary_section(
    view_model: WatchDetailPageViewModel,
    use_24_hour_time: bool,
) -> str:
    """渲染 detail price summary section。"""
    return render_watch_price_summary_cards(
        presentation=view_model.summary,
        use_24_hour_time=use_24_hour_time,
    )


def _render_price_trend_section(
    view_model: WatchDetailPageViewModel,
    use_24_hour_time: bool,
) -> str:
    """渲染 detail price trend section。"""
    return render_price_trend_section_from_presentation(view_model.price_trend)


def _render_check_events_section(
    view_model: WatchDetailPageViewModel,
    use_24_hour_time: bool,
) -> str:
    """渲染 detail check event history section。"""
    return render_check_events_section_from_presentation(view_model.check_event_rows)


def _render_runtime_state_events_section(
    view_model: WatchDetailPageViewModel,
    use_24_hour_time: bool,
) -> str:
    """渲染 detail runtime state event section。"""
    return render_runtime_state_events_section_from_presentation(
        view_model.runtime_state_event_rows,
    )


def _render_debug_artifacts_section(
    view_model: WatchDetailPageViewModel,
    use_24_hour_time: bool,
) -> str:
    """渲染 detail debug artifacts section。"""
    return render_debug_artifacts_section_from_presentation(
        view_model.debug_artifact_rows,
    )
