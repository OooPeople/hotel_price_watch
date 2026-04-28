"""watch detail hero 與價格摘要 partial renderer。"""

from __future__ import annotations

from datetime import datetime
from html import escape

from app.web.ui_components import card, key_value_grid, status_badge, summary_card
from app.web.ui_styles import hero_title_style, meta_paragraph_style, responsive_grid_style
from app.web.view_formatters import format_datetime_lines_for_display
from app.web.watch_detail_presenters import WatchDetailPresentation


def render_watch_detail_hero_section(
    *,
    presentation: WatchDetailPresentation,
    use_24_hour_time: bool,
) -> str:
    """渲染 watch 詳細頁的 hero summary，讓價格與狀態成為首屏主角。"""
    last_checked_text, last_checked_html = _format_datetime_summary_value(
        presentation.last_checked_at,
        empty_text="尚未檢查",
        use_24_hour_time=use_24_hour_time,
    )
    runtime_badge_html = status_badge(
        label=presentation.runtime_state_badge.label,
        kind=presentation.runtime_state_badge.kind,
    )
    return card(
        body=f"""
        <div class="watch-detail-hero" style="display:grid;gap:10px;">
          <div style="display:grid;gap:8px;min-width:260px;">
            <div>{runtime_badge_html}</div>
            <h2 style="{hero_title_style()}">{escape(presentation.hotel_name)}</h2>
            <p style="{meta_paragraph_style()}">{escape(presentation.room_name)}</p>
          </div>
        </div>
        {key_value_grid((
            ("日期", escape(presentation.date_range_text)),
            ("人數 / 房數", escape(presentation.occupancy_text)),
            ("最後檢查", last_checked_html or escape(last_checked_text)),
        ))}
        """,
    )


def render_watch_price_summary_cards(
    *,
    presentation: WatchDetailPresentation,
    use_24_hour_time: bool = True,
) -> str:
    """渲染 watch 詳細頁的價格與通知摘要卡片。"""
    last_notified_text, last_notified_html = _format_datetime_summary_value(
        presentation.last_notified_at,
        empty_text="尚未通知",
        use_24_hour_time=use_24_hour_time,
    )
    cards_html = "".join(
        (
            summary_card(
                label="目前價格",
                value=presentation.current_price_text,
                helper_text="最近一次解析結果",
            ),
            summary_card(
                label="空房狀態",
                value=presentation.availability_text,
                helper_text="最近一次檢查結果",
            ),
            summary_card(
                label="通知條件",
                value=presentation.notification_rule_text,
                helper_text="可在通知設定中調整",
            ),
            summary_card(
                label="最近通知",
                value=last_notified_text,
                value_html=last_notified_html,
                helper_text="尚未觸發時不會通知",
            ),
        )
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {cards_html}
    </section>
    """


def _format_datetime_summary_value(
    value: datetime | None,
    *,
    empty_text: str,
    use_24_hour_time: bool,
) -> tuple[str, str | None]:
    """把摘要卡片的時間拆成純文字與受控分行 HTML。"""
    if value is None:
        return empty_text, None

    date_text, time_text = format_datetime_lines_for_display(
        value,
        use_24_hour_time=use_24_hour_time,
    )
    html = (
        f'<span style="display:block;white-space:nowrap;">{escape(date_text)}</span>'
        f'<span style="display:block;white-space:nowrap;">{escape(time_text)}</span>'
    )
    return f"{date_text} {time_text}", html
