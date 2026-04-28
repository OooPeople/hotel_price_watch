"""Watch Detail 頁面的 page-level client script entrypoint。"""

from __future__ import annotations

from app.web.watch_detail_client_scripts import render_watch_detail_polling_script


def render_watch_detail_page_scripts(
    watch_item_id: str,
    *,
    initial_fragment_version: str | None = None,
) -> str:
    """渲染 Watch Detail 頁目前所有 client behavior。"""
    return render_watch_detail_polling_script(
        watch_item_id,
        initial_fragment_version=initial_fragment_version,
    )
