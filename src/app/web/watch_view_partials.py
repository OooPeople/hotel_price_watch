"""watch list / detail 頁面可替換區塊的 HTML partial renderer。"""

from __future__ import annotations

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
from app.domain.enums import (
    NotificationLeafKind,
    RuntimeStateEventKind,
    WatchRuntimeState,
)
from app.monitor.runtime import MonitorRuntimeStatus
from app.web.ui_components import (
    action_row,
    card,
    data_table,
    empty_state_card,
    notice_box,
    submit_button,
    table_row,
    text_link,
)
from app.web.view_formatters import format_datetime_for_display


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
    return card(
        title="Background Monitor",
        extra_style="margin-top:20px;",
        body=f"""
        <p style="margin:0;">狀態：{escape(running_text)}</p>
        <p style="margin:0;">Chrome session：{escape(chrome_text)}</p>
        <p style="margin:0;">已啟用 watch：{runtime_status.enabled_watch_count}</p>
        <p style="margin:0;">已註冊排程：{runtime_status.registered_watch_count}</p>
        <p style="margin:0;">執行中 worker：{runtime_status.inflight_watch_count}</p>
        <p style="margin:0;">最後 tick：{escape(last_tick_text)}</p>
        <p style="margin:0;">最後同步 watch：{escape(last_sync_text)}</p>
        """,
    )


def render_watch_list_rows(
    watch_items: Iterable[WatchItem],
    *,
    latest_snapshots_by_watch_id: dict[str, LatestCheckSnapshot | None] | None = None,
) -> str:
    """渲染首頁 watch 列表 tbody 內容，供首屏與局部更新共用。"""
    rows = []
    latest_snapshots_by_watch_id = latest_snapshots_by_watch_id or {}
    for watch_item in watch_items:
        latest_snapshot = latest_snapshots_by_watch_id.get(watch_item.id)
        runtime_state = derive_watch_runtime_state(
            watch_item=watch_item,
            latest_snapshot=latest_snapshot,
        )
        date_range = (
            f"{watch_item.target.check_in_date.isoformat()} - "
            f"{watch_item.target.check_out_date.isoformat()}"
        )
        actions_html = render_watch_action_controls(
            watch_item=watch_item,
            runtime_state=runtime_state,
            show_check_now=False,
        )
        rows.append(
            f"""
            <tr>
              <td>{text_link(href=f"/watches/{watch_item.id}", label=watch_item.hotel_name)}</td>
              <td>{escape(watch_item.room_name)}</td>
              <td>{escape(watch_item.plan_name)}</td>
              <td>{date_range}</td>
              <td>{watch_item.scheduler_interval_seconds}</td>
              <td>{escape(describe_watch_runtime_state(runtime_state))}</td>
              <td>{actions_html}</td>
            </tr>
            """
        )
    return "\n".join(rows) or '<tr><td colspan="7">目前尚無 watch item。</td></tr>'


def render_latest_snapshot_section(
    *,
    watch_item: WatchItem,
    latest_snapshot: LatestCheckSnapshot | None,
    notification_state: NotificationState | None,
    debug_artifacts: tuple[DebugArtifact, ...],
    use_24_hour_time: bool = True,
) -> str:
    """渲染單一 watch item 的最近一次摘要與通知狀態。"""
    if latest_snapshot is None:
        return empty_state_card(title="最近摘要", message="目前尚無任何檢查結果。")

    runtime_signal_html = _render_runtime_signal_summary(
        debug_artifacts,
        use_24_hour_time=use_24_hour_time,
    )
    latest_price = _format_optional_money(
        latest_snapshot.currency,
        latest_snapshot.normalized_price_amount,
    )
    last_notified_price = (
        _format_optional_money(
            latest_snapshot.currency,
            notification_state.last_notified_price,
        )
        if notification_state is not None
        else "unknown"
    )
    last_notified_availability = (
        notification_state.last_notified_availability.value
        if notification_state and notification_state.last_notified_availability
        else "none"
    )
    last_notified_at = (
        format_datetime_for_display(
            notification_state.last_notified_at,
            use_24_hour_time=use_24_hour_time,
        )
        if notification_state and notification_state.last_notified_at
        else "none"
    )
    return card(
        title="最近摘要",
        body=f"""
        <p>最近檢查：{escape(format_datetime_for_display(
            latest_snapshot.checked_at,
            use_24_hour_time=use_24_hour_time,
        ))}</p>
        <p>Availability：{escape(latest_snapshot.availability.value)}</p>
        <p>最近價格：{escape(latest_price)}</p>
        <p>連續失敗次數：{latest_snapshot.consecutive_failures}</p>
        <p>最後錯誤：{escape(latest_snapshot.last_error_code or "none")}</p>
        <p>目前是否 degraded：{"是" if latest_snapshot.is_degraded else "否"}</p>
        <p>最近通知價格：{escape(last_notified_price)}</p>
        <p>
          最近通知 availability：
          {escape(last_notified_availability)}
        </p>
        <p>
          最近通知時間：
          {escape(last_notified_at)}
        </p>
        <p>
          目前設定的通知規則：
          {escape(_describe_notification_rule(watch_item))}
        </p>
        {runtime_signal_html}
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
        event_kind_text = ", ".join(event.event_kinds) or "checked"
        event_price_text = _format_optional_money(
            event.currency,
            event.normalized_price_amount,
        )
        rows.append(
            table_row(
                (
                    escape(
                        format_datetime_for_display(
                            event.checked_at,
                            use_24_hour_time=use_24_hour_time,
                        )
                    ),
                    escape(event.availability.value),
                    escape(event_kind_text),
                    escape(event_price_text),
                    escape(event.error_code or "none"),
                    escape(event.notification_status.value),
                )
            )
        )

    return card(
        title="檢查歷史",
        body=data_table(
            headers=("時間", "Availability", "事件", "價格", "錯誤", "通知結果"),
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
            message="目前尚無 blocked / paused / resumed / recovered 相關狀態事件。",
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
                    escape(event.detail_text or "none"),
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
    """渲染與單一 watch item 關聯的 debug artifact 摘要。"""
    return render_debug_artifacts_section_with_time_format(
        debug_artifacts,
        use_24_hour_time=True,
    )


def render_debug_artifacts_section_with_time_format(
    debug_artifacts: tuple[DebugArtifact, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """依顯示設定渲染與單一 watch item 關聯的 debug artifact 摘要。"""
    if not debug_artifacts:
        return empty_state_card(
            title="Debug Artifacts",
            message="目前尚無 background runtime debug artifact。",
            extra_html=(
                "<p>若要看建立 watch / preview 過程的 debug capture，"
                "請到首頁的 Debug 區。</p>"
            ),
        )

    rows = []
    for artifact in debug_artifacts[:10]:
        http_status_text = (
            str(artifact.http_status) if artifact.http_status is not None else "none"
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
                    escape(artifact.source_url or "none"),
                    escape(http_status_text),
                )
            )
        )

    return card(
        title="Debug Artifacts",
        body=f"""
        <p>
          這裡只顯示 background runtime 寫入的 debug artifact，
          例如節流、blocked page、tab discard。
        </p>
        <p>preview / parser 問題請到首頁的 Debug 區查看 preview captures。</p>
        {data_table(
            headers=("時間", "原因", "來源 URL", "HTTP 狀態"),
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
        WatchRuntimeState.BACKOFF_ACTIVE,
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
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="disable",
                label="停用",
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
        actions.append(
            _render_watch_action_form(
                watch_item_id=watch_item.id,
                action="disable",
                label="停用",
                button_kind="secondary",
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
    """在首頁啟用輕量 polling，只更新 runtime 摘要與 watch 列表。"""
    return """
    <script>
      (() => {
        const runtimeContainer = document.getElementById("runtime-status-section");
        const tableBody = document.getElementById("watch-list-table-body");
        if (!runtimeContainer || !tableBody) {
          return;
        }

        const refresh = async () => {
          try {
            const response = await fetch("/fragments/watch-list", {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            const payload = await response.json();
            runtimeContainer.innerHTML = payload.runtime_html;
            tableBody.innerHTML = payload.table_body_html;
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        window.setInterval(refresh, 15000);
      })();
    </script>
    """


def render_watch_detail_polling_script(watch_item_id: str) -> str:
    """在 watch 詳細頁啟用輕量 polling，只更新摘要、歷史與 debug 區塊。"""
    return f"""
    <script>
      (() => {{
        const latestSection = document.getElementById("watch-detail-latest-section");
        const checkEventsSection = document.getElementById(
          "watch-detail-check-events-section"
        );
        const runtimeStateEventsSection = document.getElementById(
          "watch-detail-runtime-state-events-section"
        );
        const debugArtifactsSection = document.getElementById(
          "watch-detail-debug-artifacts-section"
        );
        if (
          !latestSection ||
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
            latestSection.innerHTML = payload.latest_section_html;
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


def _render_runtime_signal_summary(
    debug_artifacts: tuple[DebugArtifact, ...],
    *,
    use_24_hour_time: bool,
) -> str:
    """整理最近的 runtime 訊號，讓 watch 詳細頁可快速判讀背景狀態。"""
    if not debug_artifacts:
        return notice_box(
            body=(
                "<strong>最近 runtime 訊號：</strong> "
                "目前沒有 blocked page、節流或 tab discard 紀錄。"
            )
        )

    recent_artifacts = debug_artifacts[:10]
    counts: dict[str, int] = {}
    for artifact in recent_artifacts:
        counts[artifact.reason] = counts.get(artifact.reason, 0) + 1

    latest_artifact = recent_artifacts[0]
    latest_reason = _describe_debug_reason(latest_artifact.reason)
    latest_at = format_datetime_for_display(
        latest_artifact.captured_at,
        use_24_hour_time=use_24_hour_time,
    )
    summary_parts = [
        f"{_describe_debug_reason(reason)} {count} 次"
        for reason, count in sorted(counts.items())
    ]
    summary_text = "；".join(summary_parts)
    return notice_box(
        body=f"""
        <strong>最近 runtime 訊號：</strong>
        最近一次為 {escape(latest_reason)}（{escape(latest_at)}）。
        <span>{escape(summary_text)}</span>
        """,
    )


def _format_decimal_for_display(amount) -> str:
    """把 Decimal 數字格式化成較適合 GUI 顯示的文字。"""
    if amount == amount.to_integral():
        return str(amount.quantize(Decimal("1")))
    return format(amount.normalize(), "f")


def _format_optional_money(currency: str | None, amount: Decimal | None) -> str:
    """把可選價格欄位整理成較易讀的文字。"""
    if amount is None:
        return "none"
    amount_text = _format_decimal_for_display(amount)
    return f"{currency or ''} {amount_text}".strip()


def _describe_notification_rule(watch_item: WatchItem) -> str:
    """把 V1 單規則通知條件整理成摘要文字。"""
    rule = watch_item.notification_rule
    if getattr(rule, "kind", None) == NotificationLeafKind.ANY_DROP:
        return "價格下降"
    target_price = getattr(rule, "target_price", None)
    if getattr(rule, "kind", None) == NotificationLeafKind.BELOW_TARGET_PRICE:
        return f"低於目標價 {target_price}" if target_price is not None else "低於目標價"
    return "複合規則"


def _describe_debug_reason(reason: str) -> str:
    """把 runtime debug artifact 的原因轉成較易讀的中文。"""
    mapping = {
        "possible_throttling": "可能節流",
        "page_was_discarded": "分頁曾被瀏覽器丟棄",
        "http_403": "站方阻擋頁 / 403",
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
        return "none"
    return describe_watch_runtime_state(state)
