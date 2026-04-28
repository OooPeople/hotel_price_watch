from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.domain.value_objects import SearchDraft
from app.monitor.runtime_outcomes import WatchCheckOutcome
from app.monitor.startup_restore import (
    BrowserAssignmentRestorer,
    resolve_watch_preferred_tab_id,
)
from app.sites.registry import SiteRegistry
from tests.unit.monitor_runtime.helpers import (
    _build_runtime_draft,
    _build_runtime_watch_item,
    _FakeRuntimeAdapter,
)


def test_startup_restore_claims_tabs_and_marks_scheduler_completion() -> None:
    """啟動恢復應依序排除已認領分頁，並把成功檢查回寫 scheduler。"""
    first_watch = _build_runtime_watch_item("watch-restore-1")
    second_watch = replace(
        _build_runtime_watch_item("watch-restore-2"),
        canonical_url=first_watch.canonical_url.replace("11035620", "11035621"),
    )
    draft_reader = _FakeDraftReader(
        {
            first_watch.id: replace(
                _build_runtime_draft(first_watch.canonical_url),
                browser_tab_id=" tab-hint-1 ",
            ),
            second_watch.id: _build_runtime_draft(second_watch.canonical_url),
        }
    )
    site_registry = SiteRegistry()
    site_registry.register(_FakeRuntimeAdapter())
    scheduler = _FakeStartupScheduler()
    check_runner = _FakeStartupCheckRunner(
        (
            WatchCheckOutcome(persisted=True, tab_id="tab-1", tab_url=first_watch.canonical_url),
            WatchCheckOutcome(
                persisted=True,
                tab_id="tab-2",
                tab_url=second_watch.canonical_url,
                backoff_until=datetime(2026, 4, 13, 10, 5, tzinfo=UTC),
            ),
        )
    )
    restorer = BrowserAssignmentRestorer(
        draft_reader=draft_reader,
        site_registry=site_registry,
        scheduler=scheduler,
        check_runner=check_runner,
        stop_event=_NeverStoppedEvent(),
        restore_delay_seconds=0,
        now=lambda: datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
    )

    import asyncio

    asyncio.run(
        restorer.restore_active_watch_tabs(
            {
                first_watch.id: first_watch,
                second_watch.id: second_watch,
            }
        )
    )

    assert check_runner.calls == [
        ("watch-restore-1", False, ()),
        ("watch-restore-2", False, ("tab-1",)),
    ]
    assert scheduler.completed == [
        ("watch-restore-1", datetime(2026, 4, 13, 10, 0, tzinfo=UTC), None),
        (
            "watch-restore-2",
            datetime(2026, 4, 13, 10, 0, tzinfo=UTC),
            datetime(2026, 4, 13, 10, 5, tzinfo=UTC),
        ),
    ]


def test_resolve_watch_preferred_tab_id_ignores_blank_values() -> None:
    """分頁 hint 解析應清掉空白，空字串不可參與 tab matching。"""
    assert resolve_watch_preferred_tab_id(None) is None
    assert (
        resolve_watch_preferred_tab_id(
            replace(_build_runtime_draft("https://www.ikyu.com/"), browser_tab_id="  ")
        )
        is None
    )
    assert (
        resolve_watch_preferred_tab_id(
            replace(_build_runtime_draft("https://www.ikyu.com/"), browser_tab_id=" tab-1 ")
        )
        == "tab-1"
    )


class _FakeDraftReader:
    """提供啟動恢復測試用的 draft reader。"""

    def __init__(self, drafts: dict[str, SearchDraft]) -> None:
        self._drafts = drafts

    def get_draft(self, watch_item_id: str) -> SearchDraft | None:
        """依 watch id 回傳測試指定的 draft。"""
        return self._drafts.get(watch_item_id)


class _FakeStartupScheduler:
    """記錄啟動恢復流程回寫 scheduler 的參數。"""

    def __init__(self) -> None:
        self.completed: list[tuple[str, datetime, datetime | None]] = []

    def mark_check_completed(
        self,
        *,
        watch_item_id: str,
        completed_at: datetime,
        backoff_until: datetime | None = None,
    ) -> None:
        """記錄單次啟動恢復完成事件。"""
        self.completed.append((watch_item_id, completed_at, backoff_until))


class _FakeStartupCheckRunner:
    """依序回傳啟動恢復測試指定的 check outcome。"""

    def __init__(self, outcomes: tuple[WatchCheckOutcome, ...]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, bool, tuple[str, ...]]] = []

    async def __call__(
        self,
        watch_item_id: str,
        *,
        reload_page: bool,
        excluded_tab_ids: tuple[str, ...],
    ) -> WatchCheckOutcome:
        """記錄單次恢復呼叫並回傳下一個 outcome。"""
        self.calls.append((watch_item_id, reload_page, excluded_tab_ids))
        return self._outcomes.pop(0)


class _NeverStoppedEvent:
    """模擬未被停止的 asyncio event。"""

    def is_set(self) -> bool:
        """啟動恢復測試中永遠回傳未停止。"""
        return False
