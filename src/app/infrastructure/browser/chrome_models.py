"""Chrome CDP browser capture 使用的資料模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChromeTabSummary:
    """表示目前可附著的 Chrome 分頁摘要。"""

    tab_id: str
    title: str
    url: str
    visibility_state: str | None
    has_focus: bool | None
    was_discarded: bool | None = None

    @property
    def possible_throttling(self) -> bool:
        """以頁面可見性與焦點狀態推估背景節流風險。"""
        return (
            self.visibility_state == "hidden"
            or self.has_focus is False
            or self.was_discarded is True
        )


@dataclass(frozen=True, slots=True)
class ChromeTabCapture:
    """表示從特定 Chrome 分頁抓回的內容與分頁摘要。"""

    tab: ChromeTabSummary
    html: str
