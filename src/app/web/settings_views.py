"""通知設定頁面的 HTML renderer。"""

from __future__ import annotations

from html import escape

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.entities import WatchItem
from app.web.settings_partials import (
    render_global_settings_editor_form,
    render_global_settings_scripts,
    render_global_settings_summary,
    render_notification_test_result_section,
    render_test_notification_form,
    render_watch_notification_rule_form_body,
    render_watch_notification_rule_scripts,
)
from app.web.settings_presenters import (
    SettingsPageViewModel,
    WatchNotificationRulePresentation,
    build_settings_page_view_model,
    build_watch_notification_rule_presentation,
)
from app.web.ui_components import (
    flash_message as render_flash_message,
)
from app.web.ui_components import (
    form_card,
    page_header,
    page_layout,
)
from app.web.ui_page_sections import page_stack


def render_notification_settings_page(
    *,
    watch_item: WatchItem,
    error_message: str | None = None,
    flash_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> str:
    """渲染單一 watch item 的通知設定頁。"""
    presentation = build_watch_notification_rule_presentation(
        watch_item=watch_item,
        error_message=error_message,
        flash_message=flash_message,
        form_values=form_values,
    )
    return render_notification_settings_page_from_presentation(presentation)


def render_notification_settings_page_from_presentation(
    presentation: WatchNotificationRulePresentation,
) -> str:
    """依單一 watch 通知規則 presentation 渲染通知設定頁。"""
    error_html = render_flash_message(presentation.error_message, kind="error")
    flash_html = render_flash_message(presentation.flash_message)
    return page_layout(
        title=f"通知設定 - {presentation.hotel_name}",
        body=page_stack(
            f"""
          {page_header(
              title="通知設定",
              subtitle=f"{escape(presentation.hotel_name)} / {escape(presentation.room_name)}",
              back_href=f"/watches/{presentation.watch_id}",
              back_label="回監視詳情",
          )}
          {error_html}
          {flash_html}
          {form_card(
              action=f"/watches/{presentation.watch_id}/notification-settings",
              body=render_watch_notification_rule_form_body(
                  selected_kind=presentation.selected_kind,
                  target_price_value=escape(presentation.target_price_value),
              ),
          )}
          {render_watch_notification_rule_scripts()}
        """,
        ),
    )


def render_notification_channel_settings_page(
    *,
    settings: NotificationChannelSettings,
    display_settings: DisplaySettings | None = None,
    error_message: str | None = None,
    flash_message: str | None = None,
    test_result_message: str | None = None,
    form_values: dict[str, str] | None = None,
) -> str:
    """渲染主頁層級的全域設定頁。"""
    display_settings = display_settings or DisplaySettings()
    view_model = build_settings_page_view_model(
        settings=settings,
        display_settings=display_settings,
        error_message=error_message,
        flash_message=flash_message,
        test_result_message=test_result_message,
        form_values=form_values,
    )
    return render_notification_channel_settings_page_from_view_model(view_model)


def render_notification_channel_settings_page_from_view_model(
    view_model: SettingsPageViewModel,
) -> str:
    """依全域設定頁 view model 渲染設定頁。"""
    error_html = render_flash_message(view_model.error_message, kind="error")
    flash_html = render_flash_message(view_model.flash_message)
    test_result_html = render_notification_test_result_section(view_model.test_result)
    settings_summary_html = render_global_settings_summary(view_model.channel_settings)
    return page_layout(
        title="設定",
        body=page_stack(
            f"""
          {page_header(
              title="設定",
              subtitle="集中管理顯示偏好與通知通道；單一監視的通知條件仍在監視詳情頁調整。",
              back_href="/",
              back_label="回列表",
          )}
          {error_html}
          {flash_html}
          {test_result_html}
          {settings_summary_html}
          {render_global_settings_editor_form(view_model.editor)}
          {render_test_notification_form(view_model.test_action)}
          {render_global_settings_scripts()}
        """,
        ),
    )
