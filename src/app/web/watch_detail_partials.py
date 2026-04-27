"""watch detail 專用 partial renderer。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

from app.domain import describe_watch_runtime_state
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    RuntimeStateEvent,
)
from app.domain.enums import RuntimeStateEventKind, WatchRuntimeState
from app.web.ui_components import (
    card,
    data_table,
    empty_state_card,
    key_value_grid,
    status_badge,
    summary_card,
    table_row,
)
from app.web.ui_presenters import (
    availability_badge,
    check_event_kinds_text,
    error_code_text,
    money_text,
    notification_status_badge,
)
from app.web.ui_styles import (
    color_token,
    hero_title_style,
    meta_label_style,
    meta_paragraph_style,
    muted_text_style,
    responsive_grid_style,
)
from app.web.view_formatters import format_datetime_for_display, format_datetime_lines_for_display
from app.web.watch_action_partials import render_watch_action_controls
from app.web.watch_detail_presenters import WatchDetailPresentation

__all__ = [
    "render_check_events_section",
    "render_check_events_section_with_time_format",
    "render_debug_artifacts_section",
    "render_debug_artifacts_section_with_time_format",
    "render_price_trend_section_with_time_format",
    "render_runtime_state_events_section",
    "render_runtime_state_events_section_with_time_format",
    "render_watch_action_controls",
    "render_watch_detail_hero_section",
    "render_watch_price_summary_cards",
]

PRICE_CHART_LEFT = 76
PRICE_CHART_TOP = 34
PRICE_CHART_WIDTH = 532
PRICE_CHART_HEIGHT = 100
PRICE_CHART_BOTTOM = PRICE_CHART_TOP + PRICE_CHART_HEIGHT


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


def render_price_trend_section_with_time_format(
    check_events: tuple[CheckEvent, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """渲染 watch 詳細頁的輕量價格趨勢，不引入外部 chart library。"""
    priced_events = _priced_check_events(check_events)
    if not priced_events:
        return empty_state_card(
            title="價格趨勢",
            message="目前尚無可繪製趨勢的價格紀錄。",
        )

    if len(priced_events) == 1:
        only_event = priced_events[0]
        only_price = money_text(only_event.currency, only_event.normalized_price_amount)
        only_time = format_datetime_for_display(
            only_event.checked_at,
            use_24_hour_time=use_24_hour_time,
        )
        return card(
            title="價格趨勢",
            body=f"""
            <p style="{meta_paragraph_style()}">
              目前只有一筆有效價格，累積更多檢查後會顯示趨勢線。
            </p>
            <p><strong>{escape(only_price)}</strong>（{escape(only_time)}）</p>
            """,
        )

    chart_events = priced_events[-20:]
    points = _price_chart_points(chart_events)
    oldest_event = chart_events[0]
    latest_event = chart_events[-1]
    oldest_price = money_text(oldest_event.currency, oldest_event.normalized_price_amount)
    latest_price = money_text(latest_event.currency, latest_event.normalized_price_amount)
    min_price = min(_price_amount(event) for event in chart_events)
    max_price = max(_price_amount(event) for event in chart_events)
    point_markers = _price_chart_markers(
        chart_events,
        points,
        use_24_hour_time=use_24_hour_time,
    )
    chart_axes = _price_chart_axes(
        chart_events,
        min_price=min_price,
        max_price=max_price,
        use_24_hour_time=use_24_hour_time,
    )
    delta_text = _price_delta_text(oldest_event, latest_event)
    chart_style = (
        f"width:100%;height:auto;border:1px solid {color_token('border')};"
        f"background:{color_token('surface_alt')};border-radius:12px;"
    )
    range_text = _price_range_text(
        latest_event.currency,
        min_price=min_price,
        max_price=max_price,
    )
    return card(
        title="價格趨勢",
        body=f"""
        <div style="{responsive_grid_style(min_width="180px", gap="12px")}">
          <div>
            <span style="{meta_label_style()}">最新價格</span>
            <strong>{escape(latest_price)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">本圖變化</span>
            <strong>{escape(delta_text)}</strong>
          </div>
          <div>
            <span style="{meta_label_style()}">圖表範圍</span>
            <strong>{len(chart_events)} 筆有效價格</strong>
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
            起點：{escape(oldest_price)}
            （{escape(format_datetime_for_display(
                oldest_event.checked_at,
                use_24_hour_time=use_24_hour_time,
            ))}）
          </span>
          <span style="{muted_text_style()}">
            {escape(range_text)}
          </span>
        </div>
        """,
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
    if not check_events:
        return empty_state_card(title="檢查歷史", message="目前尚無檢查歷史。")

    rows = []
    for event in sorted(check_events, key=lambda item: item.checked_at, reverse=True)[:20]:
        event_kind_text = check_event_kinds_text(event.event_kinds)
        event_price_text = money_text(
            event.currency,
            event.normalized_price_amount,
        )
        availability_presentation = availability_badge(event.availability)
        notification_presentation = notification_status_badge(event.notification_status)
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            event.checked_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    status_badge(
                        label=availability_presentation.label,
                        kind=availability_presentation.kind,
                    ),
                    escape(event_kind_text),
                    escape(event_price_text),
                    escape(error_code_text(event.error_code)),
                    status_badge(
                        label=notification_presentation.label,
                        kind=notification_presentation.kind,
                    ),
                )
            )
        )

    return card(
        title="檢查歷史",
        body=data_table(
            headers=("時間", "空房狀態", "事件", "價格", "錯誤摘要", "通知結果"),
            rows_html="".join(rows),
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
    if not runtime_state_events:
        return empty_state_card(
            title="狀態事件",
            message="目前尚無暫停、恢復或阻擋相關狀態事件。",
        )

    rows = []
    for event in runtime_state_events[:10]:
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            event.occurred_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    escape(_describe_runtime_state_event_kind(event.event_kind)),
                    escape(_describe_optional_runtime_state(event.from_state)),
                    escape(_describe_optional_runtime_state(event.to_state)),
                    escape(event.detail_text or "無"),
                )
            )
        )
    return card(
        title="狀態事件",
        body=data_table(
            headers=("時間", "事件", "前狀態", "後狀態", "說明"),
            rows_html="".join(rows),
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
    if not debug_artifacts:
        return empty_state_card(
            title="診斷檔案",
            message="目前尚無背景監視診斷紀錄。",
            extra_html=(
                "<p>若要看建立監視 / preview 過程的診斷紀錄，"
                "請到首頁的進階診斷。</p>"
            ),
        )

    rows = []
    for artifact in debug_artifacts[:10]:
        http_status_text = (
            str(artifact.http_status) if artifact.http_status is not None else "無"
        )
        reason_text = _describe_debug_reason(artifact.reason)
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            artifact.captured_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    escape(reason_text),
                    escape(artifact.source_url or "無"),
                    escape(http_status_text),
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
            rows_html="".join(rows),
        )}
        """,
    )

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

def _priced_check_events(check_events: tuple[CheckEvent, ...]) -> tuple[CheckEvent, ...]:
    """取出可用於價格趨勢的檢查事件，並依時間由舊到新排序。"""
    return tuple(
        sorted(
            (
                event
                for event in check_events
                if event.normalized_price_amount is not None
            ),
            key=lambda event: event.checked_at,
        )
    )


def _price_amount(event: CheckEvent) -> Decimal:
    """取得已確認存在的價格數值，供趨勢圖計算座標使用。"""
    if event.normalized_price_amount is None:
        raise ValueError("priced check event must carry normalized_price_amount")
    return event.normalized_price_amount


def _price_chart_points(chart_events: tuple[CheckEvent, ...]) -> str:
    """將價格事件轉成 SVG polyline points。"""
    prices = [_price_amount(event) for event in chart_events]
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
    chart_events: tuple[CheckEvent, ...],
    *,
    min_price: Decimal,
    max_price: Decimal,
    use_24_hour_time: bool,
) -> str:
    """渲染價格趨勢圖的輕量 X/Y 軸與端點標籤。"""
    oldest_event = chart_events[0]
    latest_event = chart_events[-1]
    axis_color = color_token("border_strong")
    label_color = color_token("muted")
    min_label = money_text(latest_event.currency, min_price)
    max_label = money_text(latest_event.currency, max_price)
    oldest_label = _format_chart_axis_time(
        oldest_event.checked_at,
        use_24_hour_time=use_24_hour_time,
    )
    latest_label = _format_chart_axis_time(
        latest_event.checked_at,
        use_24_hour_time=use_24_hour_time,
    )
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


def _format_chart_axis_time(value: datetime, *, use_24_hour_time: bool) -> str:
    """產生趨勢圖座標軸使用的短時間標籤。"""
    local_value = value.astimezone()
    if use_24_hour_time:
        return f"{local_value.month}/{local_value.day} {local_value:%H:%M}"

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return f"{local_value.month}/{local_value.day} {period_text} {hour:02d}:{local_value:%M}"


def _price_chart_markers(
    chart_events: tuple[CheckEvent, ...],
    points: str,
    *,
    use_24_hour_time: bool,
) -> str:
    """渲染 SVG 上的價格節點，hover 時顯示時間與價格。"""
    point_values = [point.split(",") for point in points.split()]
    markers: list[str] = []
    for event, (x, y) in zip(chart_events, point_values, strict=True):
        point_time = _format_chart_axis_time(
            event.checked_at,
            use_24_hour_time=use_24_hour_time,
        )
        point_price = money_text(event.currency, event.normalized_price_amount)
        markers.append(
            f"""
            <circle cx="{escape(x)}" cy="{escape(y)}" r="4" fill="{color_token('primary')}">
              <title>{escape(point_time)} · {escape(point_price)}</title>
            </circle>
            """
        )
    return "".join(markers)


def _price_delta_text(oldest_event: CheckEvent, latest_event: CheckEvent) -> str:
    """計算趨勢圖區間內最新價格相對起點的變化文案。"""
    delta = _price_amount(latest_event) - _price_amount(oldest_event)
    if delta == 0:
        return "持平"
    direction = "下降" if delta < 0 else "上升"
    return f"{direction} {money_text(latest_event.currency, abs(delta))}"


def _price_range_text(
    currency: str,
    *,
    min_price: Decimal,
    max_price: Decimal,
) -> str:
    """產生趨勢圖價格範圍文案，單一價格時避免顯示假範圍。"""
    if min_price == max_price:
        return f"價格：{money_text(currency, min_price)}"
    return f"區間：{money_text(currency, min_price)} - {money_text(currency, max_price)}"


def _describe_debug_reason(reason: str) -> str:
    """把 runtime debug artifact 的原因轉成較易讀的中文。"""
    mapping = {
        "possible_throttling": "可能節流",
        "page_was_discarded": "分頁被瀏覽器暫停",
        "http_403": "站方阻擋",
        "parse_failed": "解析失敗",
        "target_missing": "目標房型方案消失",
        "network_timeout": "網路逾時",
        "network_error": "網路錯誤",
    }
    return mapping.get(reason, reason)


def _describe_runtime_state_event_kind(event_kind: RuntimeStateEventKind) -> str:
    """把 runtime 狀態事件類型轉成較易讀的中文。"""
    mapping = {
        RuntimeStateEventKind.MANUAL_ENABLE: "人工啟用",
        RuntimeStateEventKind.MANUAL_DISABLE: "人工停用",
        RuntimeStateEventKind.MANUAL_PAUSE: "人工暫停",
        RuntimeStateEventKind.MANUAL_RESUME: "人工恢復",
        RuntimeStateEventKind.PAUSE_DUE_TO_BLOCKING: "因站方阻擋而暫停",
        RuntimeStateEventKind.PAUSE_DUE_TO_HTTP_403: "因站方阻擋而暫停",
        RuntimeStateEventKind.ENTERED_BACKOFF: "進入退避",
        RuntimeStateEventKind.CLEARED_BACKOFF: "解除退避",
        RuntimeStateEventKind.ENTERED_DEGRADED: "進入降級運作",
        RuntimeStateEventKind.CLEARED_DEGRADED: "解除降級",
        RuntimeStateEventKind.RECOVERED_AFTER_SUCCESS: "成功恢復",
    }
    return mapping[event_kind]


def _describe_optional_runtime_state(state: WatchRuntimeState | None) -> str:
    """把可選 runtime 狀態轉成顯示文字。"""
    if state is None:
        return "無"
    return describe_watch_runtime_state(state)

