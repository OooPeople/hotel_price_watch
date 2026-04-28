"""dev_start 測試專用 pytest fixture。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_dev_start_database(monkeypatch, tmp_path) -> None:
    """讓 dev_start 測試固定使用測試資料庫，避免讀到本機真實監視資料。"""
    monkeypatch.setenv(
        "HOTEL_PRICE_WATCH_DB_PATH",
        str(tmp_path / "hotel_price_watch.db"),
    )
