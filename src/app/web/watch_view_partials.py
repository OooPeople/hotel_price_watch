"""watch list / detail 頁面可替換區塊的 HTML partial renderer。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Iterable

from app.domain import derive_watch_runtime_state, describe_watch_runtime_state
from app.domain.entities import (
    CheckEvent,
    DebugArtifact,
    LatestCheckSnapshot,
    NotificationState,
    RuntimeStateEvent,
    WatchItem,
)
from app.domain.enums import RuntimeStateEventKind, WatchRuntimeState
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import (
    action_row,
    card,
    data_table,
    empty_state_card,
    key_value_grid,
    status_badge,
    submit_button,
    summary_card,
    table_row,
    text_link,
)
from app.web.ui_presenters import (
    availability_badge,
    check_event_kinds_text,
    error_code_text,
    money_text,
    notification_rule_text,
    notification_status_badge,
    runtime_state_badge,
)
from app.web.ui_styles import (
    color_token,
    hero_title_style,
    list_price_style,
    meta_label_style,
    meta_paragraph_style,
    muted_text_style,
    responsive_grid_style,
    stack_style,
    surface_card_style,
    watch_title_style,
)
from app.web.view_formatters import (
    format_datetime_for_display,
    format_datetime_lines_for_display,
)

PRICE_CHART_LEFT = 76
PRICE_CHART_TOP = 34
PRICE_CHART_WIDTH = 532
PRICE_CHART_HEIGHT = 100
PRICE_CHART_BOTTOM = PRICE_CHART_TOP + PRICE_CHART_HEIGHT


def render_runtime_status_section(runtime_status: MonitorRuntimeStatus | None) -> str:
    """在首頁顯示 background monitor runtime 的狀態摘要。"""
    return render_runtime_status_section_with_time_format(
        runtime_status,
        use_24_hour_time=True,
    )


def render_runtime_status_section_with_time_format(
    runtime_status: MonitorRuntimeStatus | None,
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染 background monitor runtime 的狀態摘要。"""
    if runtime_status is None:
        return ""

    running_text = "運行中" if runtime_status.is_running else "未啟動"
    chrome_text = "可附著" if runtime_status.chrome_debuggable else "不可附著"
    last_tick_text = format_datetime_for_display(
        runtime_status.last_tick_at,
        use_24_hour_time=use_24_hour_time,
    )
    last_sync_text = format_datetime_for_display(
        runtime_status.last_watch_sync_at,
        use_24_hour_time=use_24_hour_time,
    )
    runtime_is_healthy = runtime_status.is_running and runtime_status.chrome_debuggable
    status_label = "正常" if runtime_is_healthy else "需注意"
    status_kind = "success" if runtime_is_healthy else "warning"
    return card(
        title="系統狀態",
        extra_style=f"margin-top:20px;background:{color_token('surface_alt')};",
        body=f"""
        <p style="margin:0;">
          背景監視器：{status_badge(label=status_label, kind=status_kind)}
        </p>
        <p style="{meta_paragraph_style()}">執行狀態：{escape(running_text)}</p>
        <p style="{meta_paragraph_style()}">專用 Chrome：{escape(chrome_text)}</p>
        <p style="{meta_paragraph_style()}">已啟用監視：{runtime_status.enabled_watch_count}</p>
        <p style="{meta_paragraph_style()}">目前檢查中：{runtime_status.inflight_watch_count}</p>
        <p style="{meta_paragraph_style()}">最後同步：{escape(last_sync_text)}</p>
        <p style="{meta_paragraph_style(font_size="13px")}">最後 tick：{escape(last_tick_text)}</p>
        """,
    )


def render_dashboard_summary_cards(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    runtime_status: MonitorRuntimeStatus | None = None,
    use_24_hour_time: bool,
) -> str:
    """渲染首頁摘要卡片，讓首屏先呈現產品資訊而非 runtime 細節。"""
    watch_items_tuple = tuple(watch_items)
    latest_snapshots_by_watch_id = latest_snapshots_by_watch_id or {}
    attention_count = sum(
        1
        for watch_item in watch_items_tuple
        if _watch_needs_attention(latest_snapshots_by_watch_id.get(watch_item.id))
    )
    active_count = (
        runtime_status.enabled_watch_count
        if runtime_status is not None
        else sum(1 for watch_item in watch_items_tuple if watch_item.enabled)
    )
    latest_checked_at = max(
        (
            snapshot.checked_at
            for snapshot in latest_snapshots_by_watch_id.values()
            if snapshot is not None
        ),
        default=None,
    )
    latest_sync_text, latest_sync_html = _format_datetime_summary_value(
        latest_checked_at,
        empty_text="none",
        use_24_hour_time=use_24_hour_time,
    )
    chrome_text = (
        "已連線"
        if runtime_status is not None and runtime_status.chrome_debuggable
        else "未確認"
    )
    cards_html = "".join(
        (
            summary_card(
                label="啟用中的監視",
                value=str(active_count),
                helper_text=f"共 {len(watch_items_tuple)} 個監視",
            ),
            summary_card(
                label="需要注意",
                value=str(attention_count),
                helper_text="解析、阻擋或降級狀態",
            ),
            summary_card(
                label="最近檢查",
                value=latest_sync_text,
                value_html=latest_sync_html,
                helper_text="依使用者時間格式顯示",
            ),
            summary_card(
                label="專用 Chrome",
                value=chrome_text,
                helper_text="背景監看依賴此 session",
            ),
        )
    )
    summary_grid_style = responsive_grid_style(min_width="180px", gap="14px")
    return f"""
    <section style="{summary_grid_style}">
      {cards_html}
    </section>
    """


def render_watch_list_rows(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染首頁 watch card 內容，供首屏與局部更新共用。"""
    cards = []
    list_rows = []
    latest_snapshots_by_watch_id = latest_snapshots_by_watch_id or {}
    sorted_watch_items = sorted(
        tuple(watch_items),
        key=lambda item: _watch_card_sort_key(
            item,
            latest_snapshots_by_watch_id.get(item.id),
        ),
    )
    for watch_item in sorted_watch_items:
        latest_snapshot = latest_snapshots_by_watch_id.get(watch_item.id)
        runtime_state = derive_watch_runtime_state(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
        )
        runtime_presentation = runtime_state_badge(runtime_state)
        date_range = _format_date_range_text(watch_item)
        date_range_list_html = _format_date_range_list_html(watch_item)
        occupancy_text = _format_occupancy_text(watch_item)
        latest_price = (
            money_text(
                latest_snapshot.currency,
                latest_snapshot.normalized_price_amount,
            )
            if latest_snapshot is not None
            else "尚未檢查"
        )
        availability_html = ""
        error_text = "無"
        if latest_snapshot is not None:
            availability_presentation = availability_badge(latest_snapshot.availability)
            availability_html = status_badge(
                label=availability_presentation.label,
                kind=availability_presentation.kind,
            )
            error_text = error_code_text(latest_snapshot.last_error_code)
        actions_html = render_watch_card_action_controls(
            watch_item=watch_item,
            runtime_state=runtime_state,
        )
        last_checked_text = (
            format_datetime_for_display(
                latest_snapshot.checked_at,
                use_24_hour_time=use_24_hour_time,
            )
            if latest_snapshot is not None
            else "尚未檢查"
        )
        last_checked_list_text = (
            _format_short_datetime_for_list(
                latest_snapshot.checked_at,
                use_24_hour_time=use_24_hour_time,
            )
            if latest_snapshot is not None
            else "尚未檢查"
        )
        notification_rule_summary = notification_rule_text(watch_item)
        article_style = surface_card_style(gap="16px", padding="18px")
        card_header_style = (
            "display:flex;justify-content:space-between;gap:16px;"
            "align-items:flex-start;"
        )
        content_grid_style = responsive_grid_style(min_width="260px", gap="16px")
        monitoring_panel_style = (
            f"display:grid;gap:10px;padding:14px;background:{color_token('surface_alt')};"
            f"border:1px solid {color_token('border')};border-radius:12px;"
        )
        metric_grid_style = responsive_grid_style(min_width="130px", gap="10px")
        card_footer_style = (
            "display:flex;justify-content:space-between;gap:14px;align-items:center;"
            "flex-wrap:wrap;"
        )
        watch_link_html = text_link(
            href=f"/watches/{watch_item.id}",
            label=watch_item.hotel_name,
        )
        cards.append(
            f"""
            <article style="{article_style}">
              <div class="watch-card-header" style="{card_header_style}">
                <div style="{stack_style(gap="xs")}">
                  <h3 style="{watch_title_style()}">
                    {text_link(href=f"/watches/{watch_item.id}", label=watch_item.hotel_name)}
                  </h3>
                </div>
                {status_badge(label=runtime_presentation.label, kind=runtime_presentation.kind)}
              </div>
              <div style="{content_grid_style}">
                <div style="{stack_style(gap="sm")}">
                  <span style="{meta_label_style()}">房間資訊</span>
                  <strong>{escape(watch_item.room_name)}</strong>
                  <span style="{muted_text_style()}">{escape(date_range)}</span>
                  <span style="{muted_text_style()}">{escape(occupancy_text)}</span>
                </div>
                <div style="{monitoring_panel_style}">
                  <div>
                    <span style="{meta_label_style()}">目前價格</span>
                    <strong style="{list_price_style()}">{escape(latest_price)}</strong>
                  </div>
                  <div style="{metric_grid_style}">
                    <div>
                      <span style="{meta_label_style()}">空房狀態</span>
                      {availability_html or '<strong>尚未檢查</strong>'}
                    </div>
                    <div>
                      <span style="{meta_label_style()}">通知條件</span>
                      <strong>{escape(notification_rule_summary)}</strong>
                    </div>
                  </div>
                  <span style="{muted_text_style(font_size="13px")}">
                    最後檢查：{escape(last_checked_text)}，錯誤摘要：{escape(error_text)}
                  </span>
                </div>
              </div>
              <div class="watch-card-footer" style="{card_footer_style}">
                <span style="{muted_text_style()}">點進詳情可查看價格趨勢與檢查歷史。</span>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                  {text_link(href=f"/watches/{watch_item.id}", label="查看詳情")}
                  {actions_html}
                </div>
              </div>
            </article>
            """
        )
        list_rows.append(
            table_row(
                (
                    (
                        f"{watch_link_html}"
                        f"<br><span style=\"{muted_text_style(font_size='13px')}\">"
                        f"{escape(watch_item.room_name)}<br>{escape(occupancy_text)}</span>"
                    ),
                    date_range_list_html,
                    (
                        f'<strong style="{list_price_style()}white-space:nowrap;">'
                        f"{escape(latest_price)}</strong>"
                    ),
                    availability_html or "<strong>尚未檢查</strong>",
                    f'<span style="white-space:nowrap;">{escape(notification_rule_summary)}</span>',
                    f'<span style="white-space:nowrap;">{escape(last_checked_list_text)}</span>',
                    (
                        f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">'
                        f"{text_link(href=f'/watches/{watch_item.id}', label='查看詳情')}"
                        f"{actions_html}</div>"
                    ),
                )
            )
        )
    if cards:
        card_view_html = "\n".join(cards)
        list_view_html = data_table(
            headers=("監視", "日期", "價格", "空房", "通知條件", "最後檢查", "操作"),
            rows_html="".join(list_rows),
        )
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


def render_watch_detail_hero_section(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    use_24_hour_time: bool,
) -> str:
    """渲染 watch 詳細頁的 hero summary，讓價格與狀態成為首屏主角。"""
    runtime_state = derive_watch_runtime_state(
        watch_item=watch_item,
        latest_snapshot=latest_snapshot,
    )
    runtime_presentation = runtime_state_badge(runtime_state)
    date_range = (
        f"{watch_item.target.check_in_date.isoformat()} - "
        f"{watch_item.target.check_out_date.isoformat()}"
    )
    last_checked_text, last_checked_html = _format_datetime_summary_value(
        latest_snapshot.checked_at if latest_snapshot is not None else None,
        empty_text="尚未檢查",
        use_24_hour_time=use_24_hour_time,
    )
    runtime_badge_html = status_badge(
        label=runtime_presentation.label,
        kind=runtime_presentation.kind,
    )
    occupancy_text = _format_occupancy_text(watch_item)
    return card(
        body=f"""
        <div class="watch-detail-hero" style="display:grid;gap:10px;">
          <div style="display:grid;gap:8px;min-width:260px;">
            <div>{runtime_badge_html}</div>
            <h2 style="{hero_title_style()}">{escape(watch_item.hotel_name)}</h2>
            <p style="{meta_paragraph_style()}">{escape(watch_item.room_name)}</p>
          </div>
        </div>
        {key_value_grid((
            ("日期", escape(date_range)),
            ("人數 / 房數", occupancy_text),
            ("最後檢查", last_checked_html or escape(last_checked_text)),
        ))}
        """,
    )


def render_watch_price_summary_cards(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    notification_state: NotificationState | None,
    use_24_hour_time: bool = True,
) -> str:
    """渲染 watch 詳細頁的價格與通知摘要卡片。"""
    current_price = (
        money_text(
            latest_snapshot.currency,
            latest_snapshot.normalized_price_amount,
        )
        if latest_snapshot is not None
        else "尚未檢查"
    )
    availability_text = (
        availability_badge(latest_snapshot.availability).label
        if latest_snapshot is not None
        else "尚未檢查"
    )
    last_notified_text, last_notified_html = _format_datetime_summary_value(
        notification_state.last_notified_at
        if notification_state is not None
        else None,
        empty_text="尚未通知",
        use_24_hour_time=use_24_hour_time,
    )
    cards_html = "".join(
        (
            summary_card(
                label="目前價格",
                value=current_price,
                helper_text="最近一次解析結果",
            ),
            summary_card(
                label="空房狀態",
                value=availability_text,
                helper_text="最近一次檢查結果",
            ),
            summary_card(
                label="通知條件",
                value=notification_rule_text(watch_item),
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


def render_watch_action_controls(
    *,
    watch_item: WatchItem,
    runtime_state: WatchRuntimeState,
    show_check_now: bool,
) -> str:
    """依 watch 狀態渲染可用的啟用、暫停、停用與立即檢查操作。"""
    actions: list[str] = []
    if runtime_state in {
        WatchRuntimeState.ACTIVE,
        WatchRuntimeState.DEGRADED_ACTIVE,
        WatchRuntimeState.RECOVER_PENDING,
    }:
        if show_check_now:
            actions.append(
                _render_watch_action_form(
                    watch_item_id=watch_item.id,
                    action="check-now",
                    label="立即檢查",
                    button_kind="primary",
                )
            )
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="pause",
                label="暫停",
                button_kind="secondary",
            )
        )
    elif runtime_state is WatchRuntimeState.BACKOFF_ACTIVE:
        if show_check_now:
            actions.append(
                _render_watch_action_form(
                    watch_item_id=watch_item.id,
                    action="check-now",
                    label="立即檢查",
                    button_kind="primary",
                )
            )
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="pause",
                label="暫停",
                button_kind="secondary",
            )
        )
    elif runtime_state in {
        WatchRuntimeState.MANUALLY_PAUSED,
        WatchRuntimeState.PAUSED_BLOCKED,
        WatchRuntimeState.PAUSED_BLOCKED_403,
        WatchRuntimeState.PAUSED_OTHER,
    }:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="resume",
                label="恢復",
                button_kind="primary",
            )
        )
    else:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="enable",
                label="啟用",
                button_kind="primary",
            )
        )
    actions.append(
        _render_watch_action_form(
            watch_item_id=watch_item.id,
            action="delete",
            label="刪除",
            button_kind="danger",
        )
    )
    return action_row(body="".join(actions))


def render_watch_card_action_controls(
    *,
    watch_item: WatchItem,
    runtime_state: WatchRuntimeState,
) -> str:
    """渲染首頁 watch card 的主要操作。"""
    actions: list[str] = []

    if runtime_state in {
        WatchRuntimeState.ACTIVE,
        WatchRuntimeState.BACKOFF_ACTIVE,
        WatchRuntimeState.DEGRADED_ACTIVE,
        WatchRuntimeState.RECOVER_PENDING,
    }:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="pause",
                label="暫停",
                button_kind="secondary",
            )
        )
    elif runtime_state in {
        WatchRuntimeState.MANUALLY_PAUSED,
        WatchRuntimeState.PAUSED_BLOCKED,
        WatchRuntimeState.PAUSED_BLOCKED_403,
        WatchRuntimeState.PAUSED_OTHER,
    }:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="resume",
                label="恢復",
                button_kind="primary",
            )
        )
    else:
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="enable",
                label="啟用",
                button_kind="primary",
            )
        )

    actions.append(
        _render_watch_action_form(
            watch_item_id=watch_item.id,
            action="delete",
            label="刪除",
            button_kind="danger",
        )
    )

    return action_row(body="".join(actions))


def render_watch_list_polling_script() -> str:
    """在首頁啟用輕量 polling，同步更新 summary、runtime 與 watch 列表。"""
    return """
    <script>
      (() => {
        const summaryContainer = document.getElementById("dashboard-summary-section");
        const runtimeContainer = document.getElementById("runtime-status-section");
        const tableBody = document.getElementById("watch-list-table-body");
        const viewModeButtons = document.querySelectorAll("[data-watch-view-mode-button]");
        if (!summaryContainer || !runtimeContainer || !tableBody) {
          return;
        }
        const storageKey = "hotelPriceWatch.watchListViewMode";

        const applyViewMode = (mode) => {
          const safeMode = mode === "list" ? "list" : "cards";
          document.querySelectorAll("[data-watch-list-view]").forEach((element) => {
            element.style.display =
              element.dataset.watchListView === safeMode ? "" : "none";
          });
          viewModeButtons.forEach((button) => {
            button.classList.toggle(
              "is-active",
              button.dataset.watchViewModeButton === safeMode
            );
          });
        };

        const currentViewMode = () =>
          window.localStorage.getItem(storageKey) === "list" ? "list" : "cards";

        viewModeButtons.forEach((button) => {
          button.addEventListener("click", () => {
            const mode = button.dataset.watchViewModeButton === "list" ? "list" : "cards";
            window.localStorage.setItem(storageKey, mode);
            applyViewMode(mode);
          });
        });
        applyViewMode(currentViewMode());

        const refresh = async () => {
          try {
            const response = await fetch("/fragments/watch-list", {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            const payload = await response.json();
            summaryContainer.innerHTML = payload.summary_html;
            runtimeContainer.innerHTML = payload.runtime_html;
            tableBody.innerHTML = payload.table_body_html;
            applyViewMode(currentViewMode());
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        window.setInterval(refresh, 15000);
      })();
    </script>
    """


def render_watch_detail_polling_script(watch_item_id: str) -> str:
    """在 watch 詳細頁啟用輕量 polling，同步更新會變動的資訊區塊。"""
    return f"""
    <script>
      (() => {{
        const heroSection = document.getElementById("watch-detail-hero-section");
        const checkEventsSection = document.getElementById(
          "watch-detail-check-events-section"
        );
        const priceSummarySection = document.getElementById(
          "watch-detail-price-summary-section"
        );
        const priceTrendSection = document.getElementById(
          "watch-detail-price-trend-section"
        );
        const runtimeStateEventsSection = document.getElementById(
          "watch-detail-runtime-state-events-section"
        );
        const debugArtifactsSection = document.getElementById(
          "watch-detail-debug-artifacts-section"
        );
        if (
          !heroSection ||
          !priceSummarySection ||
          !priceTrendSection ||
          !runtimeStateEventsSection ||
          !checkEventsSection ||
          !debugArtifactsSection
        ) {{
          return;
        }}

        const refresh = async () => {{
          try {{
            const response = await fetch("/watches/{escape(watch_item_id)}/fragments", {{
              headers: {{ "X-Requested-With": "fetch" }},
            }});
            if (!response.ok) {{
              return;
            }}
            const payload = await response.json();
            heroSection.innerHTML = payload.hero_section_html;
            priceSummarySection.innerHTML = payload.price_summary_section_html;
            priceTrendSection.innerHTML = payload.price_trend_section_html;
            runtimeStateEventsSection.innerHTML = payload.runtime_state_events_section_html;
            checkEventsSection.innerHTML = payload.check_events_section_html;
            debugArtifactsSection.innerHTML = payload.debug_artifacts_section_html;
          }} catch {{
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }}
        }};

        window.setInterval(refresh, 10000);
      }})();
    </script>
    """


def _render_watch_action_form(
    *,
    watch_item_id: str,
    action: str,
    label: str,
    button_kind: str,
) -> str:
    """渲染單一 watch 操作按鈕表單。"""
    return f"""
    <form
      action="/watches/{escape(watch_item_id)}/{escape(action)}"
      method="post"
      style="margin:0;"
    >
      {submit_button(label=label, kind=button_kind)}
    </form>
    """


def _watch_needs_attention(snapshot: LatestCheckSnapshot | None) -> bool:
    """判斷首頁摘要是否應把 watch 計入需注意項目。"""
    if snapshot is None:
        return False
    return bool(snapshot.last_error_code or snapshot.is_degraded)


def _format_occupancy_text(watch_item: WatchItem) -> str:
    """把 watch target 的入住人數與房數轉成首頁與詳情頁共用文案。"""
    return f"{watch_item.target.people_count} 人 / {watch_item.target.room_count} 房"


def _format_date_range_text(watch_item: WatchItem) -> str:
    """把 watch target 的日期與晚數整理成使用者容易掃描的文案。"""
    date_text = _format_date_range_core(watch_item)
    return f"{date_text}，{watch_item.target.nights} 晚"


def _format_date_range_list_html(watch_item: WatchItem) -> str:
    """把清單模式日期分成日期區間與晚數兩行，降低欄寬壓力。"""
    date_text = _format_date_range_core(watch_item)
    nights_text = f"{watch_item.target.nights} 晚"
    return (
        f'<span style="white-space:nowrap;">{escape(date_text)}</span>'
        f"<br><span style=\"{muted_text_style(font_size='13px')}\">"
        f"{escape(nights_text)}</span>"
    )


def _format_date_range_core(watch_item: WatchItem) -> str:
    """產生不含晚數的精簡日期區間，跨年時才顯示年份。"""
    check_in = watch_item.target.check_in_date
    check_out = watch_item.target.check_out_date
    if check_in.year == check_out.year:
        return f"{check_in.month}/{check_in.day} - {check_out.month}/{check_out.day}"
    return (
        f"{check_in.year}/{check_in.month}/{check_in.day} - "
        f"{check_out.year}/{check_out.month}/{check_out.day}"
    )


def _format_short_datetime_for_list(
    value: datetime,
    *,
    use_24_hour_time: bool,
) -> str:
    """產生清單欄位使用的短時間格式，避免年份佔用過多欄寬。"""
    local_value = value.astimezone()
    if use_24_hour_time:
        return f"{local_value.month}/{local_value.day} {local_value:%H:%M}"

    period_text = "上午" if local_value.hour < 12 else "下午"
    hour = local_value.hour % 12 or 12
    return f"{local_value.month}/{local_value.day} {period_text} {hour:02d}:{local_value:%M}"


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


def _watch_card_sort_key(
    watch_item: WatchItem,
    snapshot: LatestCheckSnapshot | None,
) -> tuple[int, float, str]:
    """回傳首頁 watch card 排序鍵，讓需注意項目優先顯示。"""
    attention_rank = 0 if _watch_needs_attention(snapshot) else 1
    checked_rank = -(snapshot.checked_at.timestamp()) if snapshot is not None else 0.0
    return (attention_rank, checked_rank, watch_item.hotel_name)


def _availability_badge_html(snapshot: LatestCheckSnapshot | None) -> str:
    """把 latest snapshot 的空房狀態轉成 badge，缺值時回傳尚未檢查。"""
    if snapshot is None:
        return "<strong>尚未檢查</strong>"
    availability_presentation = availability_badge(snapshot.availability)
    return status_badge(
        label=availability_presentation.label,
        kind=availability_presentation.kind,
    )


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
