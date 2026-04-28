"""watch item 與 watch draft 的 SQLite repository。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.entities import WatchItem
from app.domain.value_objects import SearchDraft
from app.infrastructure.db.schema import SqliteDatabase
from app.infrastructure.db.sqlite_revision import rows_revision_token
from app.infrastructure.db.sqlite_serializers import (
    date_to_text,
    datetime_to_text,
    text_to_date,
)
from app.infrastructure.db.watch_item_records import row_to_watch_item, save_watch_item


class SqliteWatchItemRepository:
    """負責 `watch_items` 與 `watch_item_drafts` 的持久化。"""

    def __init__(self, database: SqliteDatabase) -> None:
        """建立 watch item repository。"""
        self._database = database

    def save(self, watch_item: WatchItem) -> None:
        """新增或更新 watch item，不把 runtime 狀態混進資料表。"""
        with self._database.connect() as connection:
            save_watch_item(connection, watch_item)

    def get(self, watch_item_id: str) -> WatchItem | None:
        """依 id 載入單一 watch item。"""
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM watch_items WHERE id = ?",
                (watch_item_id,),
            ).fetchone()
        if row is None:
            return None
        return row_to_watch_item(row)

    def list_all(self) -> list[WatchItem]:
        """依建立順序列出所有 watch item。"""
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM watch_items ORDER BY created_at_utc, id",
            ).fetchall()
        return [row_to_watch_item(row) for row in rows]

    def get_collection_revision_token(self) -> str:
        """回傳 watch item 集合目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return rows_revision_token(
                connection,
                """
                SELECT
                    id, site, hotel_id, room_id, plan_id, check_in_date,
                    check_out_date, people_count, room_count, hotel_name,
                    room_name, plan_name, canonical_url, notification_rule_json,
                    scheduler_interval_seconds, enabled, paused_reason,
                    created_at_utc, updated_at_utc
                FROM watch_items
                ORDER BY id
                """,
            )

    def get_revision_token(self, watch_item_id: str) -> str:
        """回傳單一 watch item 定義目前內容的輕量版本 token。"""
        with self._database.connect() as connection:
            return rows_revision_token(
                connection,
                """
                SELECT
                    id, site, hotel_id, room_id, plan_id, check_in_date,
                    check_out_date, people_count, room_count, hotel_name,
                    room_name, plan_name, canonical_url, notification_rule_json,
                    scheduler_interval_seconds, enabled, paused_reason,
                    created_at_utc, updated_at_utc
                FROM watch_items
                WHERE id = ?
                """,
                (watch_item_id,),
            )

    def delete(self, watch_item_id: str) -> None:
        """刪除 watch item，依 foreign key 一併清掉附屬資料。"""
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM watch_items WHERE id = ?",
                (watch_item_id,),
            )

    def save_draft(self, watch_item_id: str, draft: SearchDraft) -> None:
        """分開保存 UI 草稿，避免與正式 watch target 混在一起。"""
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO watch_item_drafts (
                    watch_item_id, seed_url, check_in_date, check_out_date,
                    people_count, room_count, hotel_id, room_id, plan_id,
                    browser_tab_id, browser_page_url, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(watch_item_id) DO UPDATE SET
                    seed_url = excluded.seed_url,
                    check_in_date = excluded.check_in_date,
                    check_out_date = excluded.check_out_date,
                    people_count = excluded.people_count,
                    room_count = excluded.room_count,
                    hotel_id = excluded.hotel_id,
                    room_id = excluded.room_id,
                    plan_id = excluded.plan_id,
                    browser_tab_id = excluded.browser_tab_id,
                    browser_page_url = excluded.browser_page_url,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    watch_item_id,
                    draft.seed_url,
                    date_to_text(draft.check_in_date),
                    date_to_text(draft.check_out_date),
                    draft.people_count,
                    draft.room_count,
                    draft.hotel_id,
                    draft.room_id,
                    draft.plan_id,
                    draft.browser_tab_id,
                    draft.browser_page_url,
                    datetime_to_text(datetime.now(UTC)),
                ),
            )

    def get_draft(self, watch_item_id: str) -> SearchDraft | None:
        """讀出與 watch item 分離保存的 UI 草稿。"""
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM watch_item_drafts WHERE watch_item_id = ?",
                (watch_item_id,),
            ).fetchone()
        if row is None:
            return None
        return SearchDraft(
            seed_url=row["seed_url"],
            check_in_date=text_to_date(row["check_in_date"]),
            check_out_date=text_to_date(row["check_out_date"]),
            people_count=row["people_count"],
            room_count=row["room_count"],
            hotel_id=row["hotel_id"],
            room_id=row["room_id"],
            plan_id=row["plan_id"],
            browser_tab_id=row["browser_tab_id"],
            browser_page_url=row["browser_page_url"],
        )
