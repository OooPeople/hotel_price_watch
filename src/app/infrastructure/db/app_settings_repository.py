"""全域 app settings 的 SQLite repository。"""

from __future__ import annotations

from app.config.models import DisplaySettings, NotificationChannelSettings
from app.infrastructure.db.schema import SqliteDatabase
from app.infrastructure.db.sqlite_revision import rows_revision_token


class SqliteAppSettingsRepository:
    """負責全域設定的持久化，與 watch / runtime 狀態分離。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立 app settings repository。"""
        self._database = database

    def get_notification_channel_settings(self) -> NotificationChannelSettings:
        """讀出全域通知通道設定；若尚未保存則回預設值。"""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM notification_channel_settings
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return NotificationChannelSettings()
        return NotificationChannelSettings(
            desktop_enabled=bool(row["desktop_enabled"]),
            ntfy_enabled=bool(row["ntfy_enabled"]),
            ntfy_server_url=row["ntfy_server_url"],
            ntfy_topic=row["ntfy_topic"],
            discord_enabled=bool(row["discord_enabled"]),
            discord_webhook_url=row["discord_webhook_url"],
        )

    def save_notification_channel_settings(
        self,
        settings: NotificationChannelSettings,
    ) -> NotificationChannelSettings:
        """保存全域通知通道設定。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_channel_settings (
                    singleton_id, desktop_enabled, ntfy_enabled,
                    ntfy_server_url, ntfy_topic, discord_enabled,
                    discord_webhook_url, updated_at_utc
                ) VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    desktop_enabled = excluded.desktop_enabled,
                    ntfy_enabled = excluded.ntfy_enabled,
                    ntfy_server_url = excluded.ntfy_server_url,
                    ntfy_topic = excluded.ntfy_topic,
                    discord_enabled = excluded.discord_enabled,
                    discord_webhook_url = excluded.discord_webhook_url,
                    updated_at_utc = CURRENT_TIMESTAMP
                """,
                (
                    int(settings.desktop_enabled),
                    int(settings.ntfy_enabled),
                    settings.ntfy_server_url,
                    settings.ntfy_topic,
                    int(settings.discord_enabled),
                    settings.discord_webhook_url,
                ),
            )
        return settings

    def get_display_settings(self) -> DisplaySettings:
        """讀出 GUI 顯示設定；若尚未保存則回預設值。"""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM display_settings
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return DisplaySettings()
        return DisplaySettings(
            use_24_hour_time=bool(row["use_24_hour_time"]),
        )

    def get_display_settings_revision_token(self) -> str:
        """回傳會影響 GUI 時間格式的顯示設定版本 token。"""
        with self._database.connect() as connection:
            return rows_revision_token(
                connection,
                """
                SELECT use_24_hour_time, updated_at_utc
                FROM display_settings
                WHERE singleton_id = 1
                """,
            )

    def save_display_settings(self, settings: DisplaySettings) -> DisplaySettings:
        """保存 GUI 顯示設定。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO display_settings (
                    singleton_id, use_24_hour_time, updated_at_utc
                ) VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    use_24_hour_time = excluded.use_24_hour_time,
                    updated_at_utc = CURRENT_TIMESTAMP
                """,
                (int(settings.use_24_hour_time),),
            )
        return settings
