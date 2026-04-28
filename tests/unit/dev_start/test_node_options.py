"""dev_start Node warning suppression 測試。"""

from __future__ import annotations

import os

from app.tools import dev_start


def test_dev_start_suppresses_node_dep0169_warning_for_playwright(monkeypatch) -> None:
    """單一啟動入口應只抑制 DEP0169，避免 Playwright driver warning 干擾終端機。"""
    monkeypatch.delenv("NODE_OPTIONS", raising=False)

    dev_start._ensure_node_dep0169_warning_suppressed()

    assert dev_start.NODE_DEP0169_SUPPRESSION_OPTION in os.environ["NODE_OPTIONS"]

def test_dev_start_preserves_existing_node_options(monkeypatch) -> None:
    """加入 DEP0169 抑制時應保留使用者既有 NODE_OPTIONS。"""
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")

    dev_start._ensure_node_dep0169_warning_suppressed()

    assert os.environ["NODE_OPTIONS"] == (
        f"--max-old-space-size=4096 {dev_start.NODE_DEP0169_SUPPRESSION_OPTION}"
    )
