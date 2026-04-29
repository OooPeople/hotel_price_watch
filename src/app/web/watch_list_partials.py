"""watch list / dashboard 專用 partial renderer。"""

from __future__ import annotations

from typing import Iterable

from app.domain.entities import LatestCheckSnapshot, PriceHistoryEntry, WatchItem
from app.web.ui_components import empty_state_card
from app.web.ui_presenters import WatchActionSurface
from app.web.watch_action_partials import render_watch_action_controls
from app.web.watch_list_cards import render_watch_card
from app.web.watch_list_presenters import (
    DashboardPageViewModel,
    build_dashboard_page_view_model,
)
from app.web.watch_list_row_helpers import render_presentation_badge_html
from app.web.watch_list_runtime_partials import (
    render_runtime_status_section,
    render_runtime_status_section_from_presentation,
    render_runtime_status_section_with_time_format,
)
from app.web.watch_list_summary_partials import (
    render_dashboard_summary_cards,
    render_dashboard_summary_cards_from_presentation,
)
from app.web.watch_list_table import render_dashboard_list, render_dashboard_list_row

__all__ = [
    "render_dashboard_summary_cards",
    "render_dashboard_summary_cards_from_presentation",
    "render_runtime_status_section",
    "render_runtime_status_section_from_presentation",
    "render_runtime_status_section_with_time_format",
    "render_watch_list_rows",
    "render_watch_list_rows_from_presentation",
]


def render_watch_list_rows(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    recent_price_history_by_watch_id: dict[str, tuple[PriceHistoryEntry, ...]] | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染首頁 watch card 內容，供首屏與局部更新共用。"""
    view_model = build_dashboard_page_view_model(
        watch_items=watch_items,
        latest_snapshots_by_watch_id=latest_snapshots_by_watch_id,
        recent_price_history_by_watch_id=recent_price_history_by_watch_id,
        use_24_hour_time=use_24_hour_time,
    )
    return render_watch_list_rows_from_presentation(view_model)


def render_watch_list_rows_from_presentation(
    view_model: DashboardPageViewModel,
) -> str:
    """依 Dashboard view model 渲染 watch 卡片與清單模式。"""
    cards = []
    list_items = []
    for row in view_model.watch_rows:
        actions_html = render_watch_action_controls(
            watch_item_id=row.watch_id,
            runtime_state=row.runtime_state,
            surface=WatchActionSurface.LIST,
        )
        availability_html = render_presentation_badge_html(row.availability_badge)
        runtime_badge_html = render_presentation_badge_html(row.runtime_state_badge)
        attention_badge_html = render_presentation_badge_html(row.attention_badge)
        cards.append(
            render_watch_card(
                row=row,
                actions_html=actions_html,
                availability_html=availability_html,
                runtime_badge_html=runtime_badge_html,
                attention_badge_html=attention_badge_html,
            )
        )
        list_items.append(
            render_dashboard_list_row(
                row=row,
                actions_html=actions_html,
                availability_html=availability_html,
                runtime_badge_html=runtime_badge_html,
            )
        )
    if cards:
        card_view_html = "\n".join(cards)
        list_view_html = render_dashboard_list("".join(list_items))
        return f"""
        <div data-watch-list-view="cards">
          {card_view_html}
        </div>
        <div data-watch-list-view="list" style="display:none;">
          {list_view_html}
        </div>
        """
    return empty_state_card(
        title="目前尚無監視項目",
        message="請先從專用 Chrome 分頁建立第一個價格監視。",
    )

