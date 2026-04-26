"""新增監視流程的短期 preview cache。"""

from __future__ import annotations

from collections import OrderedDict
from uuid import uuid4

from app.application.watch_editor import WatchCreationPreview


class WatchCreationPreviewCache:
    """保存剛完成的 watch creation preview，避免建立時重抓同一分頁。"""

    def __init__(self, *, max_size: int = 20) -> None:
        """建立固定容量的短期 preview cache。"""
        self._max_size = max_size
        self._items: OrderedDict[str, WatchCreationPreview] = OrderedDict()

    def store(self, preview: WatchCreationPreview) -> str:
        """保存 preview 並回傳表單可攜帶的 cache key。"""
        while len(self._items) >= self._max_size:
            self._items.popitem(last=False)
        cache_key = uuid4().hex
        self._items[cache_key] = preview
        return cache_key

    def get(self, cache_key: str | None) -> WatchCreationPreview | None:
        """依 key 讀出 preview；不存在或 key 空白時回傳 `None`。"""
        if cache_key is None:
            return None
        preview = self._items.get(cache_key)
        if preview is not None:
            self._items.move_to_end(cache_key)
        return preview

    def discard(self, cache_key: str | None) -> None:
        """移除已完成建立或不再需要的 preview cache。"""
        if cache_key is None:
            return
        self._items.pop(cache_key, None)

    def clear(self) -> None:
        """清空 cache，供測試或 app lifecycle 重設使用。"""
        self._items.clear()
