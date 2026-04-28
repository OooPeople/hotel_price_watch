"""設定頁 partial renderer 的相容 re-export。"""

from __future__ import annotations

from app.web.settings_global_partials import (
    render_global_settings_editor_form,
    render_global_settings_scripts,
    render_global_settings_summary,
)
from app.web.settings_rule_partials import (
    render_watch_notification_rule_form_body,
    render_watch_notification_rule_scripts,
)
from app.web.settings_test_partials import (
    render_notification_test_result_section,
    render_test_notification_form,
)

__all__ = [
    "render_global_settings_editor_form",
    "render_global_settings_scripts",
    "render_global_settings_summary",
    "render_notification_test_result_section",
    "render_test_notification_form",
    "render_watch_notification_rule_form_body",
    "render_watch_notification_rule_scripts",
]
