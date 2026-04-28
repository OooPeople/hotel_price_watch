"""watch detail 價格趨勢圖 partial renderer。"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.domain.entities import CheckEvent
from app.web.ui_components import card, empty_state_card
from app.web.ui_styles import (
    color_token,
    meta_label_style,
    meta_paragraph_style,
    muted_text_style,
    responsive_grid_style,
)
from app.web.watch_detail_presenters import (
    PriceTrendPointPresentation,
    PriceTrendPresentation,
    build_price_trend_presentation,
)

PRICE_CHART_LEFT = 76
PRICE_CHART_TOP = 34
PRICE_CHART_WIDTH = 532
PRICE_CHART_HEIGHT = 100
PRICE_CHART_BOTTOM = PRICE_CHART_TOP + PRICE_CHART_HEIGHT


def render_price_trend_section_with_time_format(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """渲染 watch 詳細頁的輕量價格趨勢，不引入外部 chart library。"""
    return render_price_trend_section_from_presentation(
        build_price_trend_presentation(
            check_events,
            use_24_hour_time=use_24_hour_time,
        )
    )


def render_price_trend_section_from_presentation(
    presentation: PriceTrendPresentation,
) -> str:
    """依價格趨勢 presentation 渲染詳情頁趨勢圖。"""
    if not presentation.points:
        return empty_state_card(
            title="價格趨勢",
            message="目前尚無可繪製趨勢的價格紀錄。",
        )

    if len(presentation.points) == 1:
        only_point = presentation.points[0]
        return card(
            title="價格趨勢",
            body=f"""
            <p style="{meta_paragraph_style()}">
              目前只有一筆有效價格，累積更多檢查後會顯示趨勢線。
            </p>
            <p><strong>{escape(only_point.price_text)}</strong>（{escape(only_point.checked_at_text)}）</p>
            """,
        )

    chart_points = presentation.points
    points = _price_chart_points(chart_points)
    oldest_point = chart_points[0]
    point_markers = _price_chart_markers(
        chart_points,
        points,
    )
    chart_axes = _price_chart_axes(
        chart_points,
    )
    chart_style = (
        f"width:100%;height:auto;border:1px solid {color_token('border')};"
        f"background:{color_token('surface_alt')};border-radius:12px;"
    )
    return card(
        title="價格趨勢",
        body=f"""
        <div style="{responsive_grid_style(min_width="180px", gap="12px")}">
          <div>
            <span style="{meta_label_style()}">最新價格</span>
            <strong>{escape(presentation.latest_price_text)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">本圖變化</span>
            <strong>{escape(presentation.delta_text)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">圖表範圍</span>
            <strong>{len(chart_points)} 筆有效價格</strong>
          </div>
        </div>
        <svg viewBox="0 0 640 190" role="img" aria-label="價格趨勢圖" style="{chart_style}">
          {chart_axes}
          <polyline
            fill="none"
            stroke="{color_token('primary')}"
            stroke-width="4"
            stroke-linecap="round"
            stroke-linejoin="round"
            points="{escape(points)}"
          />
          {point_markers}
        </svg>
        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;">
          <span style="{muted_text_style()}">
            起點：{escape(oldest_point.price_text)}
            （{escape(oldest_point.checked_at_text)}）
          </span>
          <span style="{muted_text_style()}">
            {escape(presentation.range_text)}
          </span>
        </div>
        """,
    )


def _price_chart_points(chart_events: tuple[PriceTrendPointPresentation, ...]) -> str:
    """將價格事件轉成 SVG polyline points。"""
    prices = [event.amount for event in chart_events]
    min_price = min(prices)
    max_price = max(prices)
    price_span = max_price - min_price
    denominator = max(len(chart_events) - 1, 1)
    points: list[str] = []
    for index, price in enumerate(prices):
        x = PRICE_CHART_LEFT + (PRICE_CHART_WIDTH * index / denominator)
        normalized = 0.5 if price_span == 0 else float((price - min_price) / price_span)
        y = PRICE_CHART_TOP + PRICE_CHART_HEIGHT - (PRICE_CHART_HEIGHT * normalized)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _price_chart_axes(
    chart_events: tuple[PriceTrendPointPresentation, ...],
) -> str:
    """渲染價格趨勢圖的輕量 X/Y 軸與端點標籤。"""
    oldest_point = chart_events[0]
    latest_point = chart_events[-1]
    axis_color = color_token("border_strong")
    label_color = color_token("muted")
    min_price = min(point.amount for point in chart_events)
    max_price = max(point.amount for point in chart_events)
    min_label = _price_label(latest_point.currency, min_price)
    max_label = _price_label(latest_point.currency, max_price)
    oldest_label = oldest_point.axis_time_text
    latest_label = latest_point.axis_time_text
    if min_price == max_price:
        flat_label_y = PRICE_CHART_TOP + (PRICE_CHART_HEIGHT / 2) + 4
        price_label_html = f"""
    <text x="{PRICE_CHART_LEFT - 8}" y="{flat_label_y:.1f}" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(max_label)}</text>
        """
    else:
        price_label_html = f"""
    <text x="{PRICE_CHART_LEFT - 8}" y="{PRICE_CHART_TOP + 5}" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(max_label)}</text>
    <text x="{PRICE_CHART_LEFT - 8}" y="{PRICE_CHART_BOTTOM + 4}" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(min_label)}</text>
        """
    return f"""
    <line
      x1="{PRICE_CHART_LEFT}" y1="{PRICE_CHART_BOTTOM}"
      x2="{PRICE_CHART_LEFT + PRICE_CHART_WIDTH}" y2="{PRICE_CHART_BOTTOM}"
      stroke="{axis_color}" stroke-width="1"
    />
    <line
      x1="{PRICE_CHART_LEFT}" y1="{PRICE_CHART_TOP}"
      x2="{PRICE_CHART_LEFT}" y2="{PRICE_CHART_BOTTOM}"
      stroke="{axis_color}" stroke-width="1"
    />
    {price_label_html}
    <text x="{PRICE_CHART_LEFT}" y="166" text-anchor="start"
      font-size="12" fill="{label_color}">{escape(oldest_label)}</text>
    <text x="{PRICE_CHART_LEFT + PRICE_CHART_WIDTH}" y="166" text-anchor="end"
      font-size="12" fill="{label_color}">{escape(latest_label)}</text>
    """


def _price_chart_markers(
    chart_events: tuple[PriceTrendPointPresentation, ...],
    points: str,
) -> str:
    """渲染 SVG 上的價格節點，hover 時顯示時間與價格。"""
    point_values = [point.split(",") for point in points.split()]
    markers: list[str] = []
    for event, (x, y) in zip(chart_events, point_values, strict=True):
        markers.append(
            f"""
            <circle cx="{escape(x)}" cy="{escape(y)}" r="4" fill="{color_token('primary')}">
              <title>{escape(event.axis_time_text)} · {escape(event.price_text)}</title>
            </circle>
            """
        )
    return "".join(markers)


def _price_label(currency: str, amount: Decimal) -> str:
    """產生 SVG 軸標籤使用的價格文字，避免 partial 依賴 domain event。"""
    from app.web.ui_presenters import money_text

    return money_text(currency, amount)
