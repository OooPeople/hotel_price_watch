"""watch list / detail client script renderer 的相容 re-export。"""

from __future__ import annotations

from app.web.watch_detail_client_scripts import render_watch_detail_polling_script
from app.web.watch_list_client_scripts import render_watch_list_polling_script

__all__ = [
    "render_watch_detail_polling_script",
    "render_watch_list_polling_script",
]
