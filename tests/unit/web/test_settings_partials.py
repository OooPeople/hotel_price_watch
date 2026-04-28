from __future__ import annotations

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.domain.enums import NotificationLeafKind
from app.web.client_contracts import SETTINGS_DOM_IDS
from app.web.settings_partials import (
    render_global_settings_editor_form,
    render_global_settings_scripts,
    render_global_settings_summary,
    render_notification_test_result_section,
    render_test_notification_form,
    render_watch_notification_rule_form_body,
)
from app.web.settings_presenters import (
    SettingsTestActionPresentation,
    build_notification_channel_settings_presentation,
    build_settings_editor_presentation,
    parse_settings_test_result_message,
)


def test_settings_partials_render_watch_notification_rule_contract() -> None:
    """單一 watch 通知規則 partial 應共用 settings DOM contract。"""
    html = render_watch_notification_rule_form_body(
        selected_kind=NotificationLeafKind.ANY_DROP,
        target_price_value="20000",
    )

    assert SETTINGS_DOM_IDS.notification_rule_kind in html
    assert SETTINGS_DOM_IDS.notification_target_price_wrapper in html
    assert 'value="20000"' in html
    assert "目標價欄位會被忽略" in html


def test_settings_partials_render_global_settings_sections() -> None:
    """全域設定 partial 應渲染摘要、編輯區與共用 client scripts。"""
    presentation = build_notification_channel_settings_presentation(
        settings=NotificationChannelSettings(
            desktop_enabled=True,
            ntfy_enabled=True,
            ntfy_server_url="https://ntfy.example.com",
            ntfy_topic="hotel-watch",
            discord_enabled=False,
            discord_webhook_url=None,
        ),
        display_settings=DisplaySettings(use_24_hour_time=True),
    )

    summary_html = render_global_settings_summary(presentation)
    editor_html = render_global_settings_editor_form(
        build_settings_editor_presentation(presentation)
    )
    scripts_html = render_global_settings_scripts()

    assert "設定摘要" in summary_html
    assert "hotel-watch" in summary_html
    assert SETTINGS_DOM_IDS.global_settings_form in editor_html
    assert SETTINGS_DOM_IDS.global_ntfy_settings in editor_html
    assert SETTINGS_DOM_IDS.global_ntfy_settings in scripts_html
    assert "beforeunload" in scripts_html


def test_settings_partials_render_test_notification_result() -> None:
    """測試通知結果 partial 應保留結構化摘要文案。"""
    html = render_notification_test_result_section(
        parse_settings_test_result_message(
            "測試通知結果：sent=desktop；"
            "throttled=none；"
            "failed=discord；"
            "details=discord: HTTP Error 400"
        )
    )

    assert "成功通道：desktop" in html
    assert "失敗通道：discord" in html
    assert "失敗原因：discord: HTTP Error 400" in html


def test_settings_partials_render_test_notification_action() -> None:
    """測試通知表單應由 action presentation 提供表單 action 與文案。"""
    html = render_test_notification_form(
        SettingsTestActionPresentation(
            action="/settings/test-notification",
            title="測試通知",
            body="發送測試訊息。",
            submit_label="發送測試通知",
        )
    )

    assert 'action="/settings/test-notification"' in html
    assert "發送測試訊息。" in html
