from __future__ import annotations

import threading
from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.config.models import NotificationChannelSettings
from app.domain.entities import PriceSnapshot, WatchItem
from app.domain.enums import Availability, SourceKind
from app.domain.value_objects import SearchDraft, WatchTarget
from app.infrastructure.browser.chrome_cdp_fetcher import ChromeTabCapture, ChromeTabSummary
from app.infrastructure.db import SqliteWatchItemRepository
from app.monitor.runtime import ChromeDrivenMonitorRuntime
from app.notifiers.base import Notifier
from app.notifiers.models import NotificationMessage
from app.sites.base import CandidateSelection, SiteAdapter
from app.sites.ikyu.client import _build_target_page_url
from app.sites.ikyu.page_guards import IkyuBlockedPageError


class _FakeChromeFetcher:
    """提供 monitor runtime 測試用的假 Chrome capture fetcher。"""

    def __init__(self) -> None:
        """記錄啟動恢復分頁時的輸入，方便驗證 runtime 行為。"""
        self.ensure_calls: list[tuple[str, str | None, str | None, tuple[str, ...]]] = []

    def is_debuggable_chrome_running(self) -> bool:
        """回傳測試用的可附著狀態。"""
        return True

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy=None,
    ) -> ChromeTabSummary:
        """模擬 runtime 啟動時重建或找回既有 watch 分頁。"""
        del page_strategy
        self.ensure_calls.append(
            (
                expected_url,
                fallback_url,
                preferred_tab_id,
                excluded_tab_ids,
            )
        )
        return ChromeTabSummary(
            tab_id=preferred_tab_id or f"restored-tab-{len(self.ensure_calls)}",
            title="Dormy Inn",
            url=fallback_url or expected_url,
            visibility_state="visible",
            has_focus=True,
        )

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """回傳固定 HTML，模擬成功刷新指定 URL 的 Chrome 分頁。"""
        del fallback_url, preferred_tab_id, page_strategy
        return ChromeTabCapture(
            tab=ChromeTabSummary(
                tab_id="tab-1",
                title="Dormy Inn",
                url=expected_url,
                visibility_state="visible",
                has_focus=True,
            ),
            html="<html><body>browser snapshot</body></html>",
        )

    def capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy=None,
        reload: bool = False,
    ) -> ChromeTabCapture:
        """依是否 reload 模擬正式檢查或啟動恢復後直接擷取。"""
        if reload:
            del excluded_tab_ids
            return self.refresh_capture_for_url(
                expected_url=expected_url,
                fallback_url=fallback_url,
                preferred_tab_id=preferred_tab_id,
                page_strategy=page_strategy,
            )
        summary = self.ensure_tab_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
            excluded_tab_ids=excluded_tab_ids,
            page_strategy=page_strategy,
        )
        return ChromeTabCapture(
            tab=summary,
            html="<html><body>browser snapshot</body></html>",
        )


class _ThrottledChromeFetcher(_FakeChromeFetcher):
    """模擬分頁被瀏覽器節流或 discarded 的 Chrome fetcher。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """回傳 hidden / not_focused 分頁狀態，模擬可能被節流的頁面。"""
        del fallback_url, preferred_tab_id, page_strategy
        return ChromeTabCapture(
            tab=ChromeTabSummary(
                tab_id="tab-1",
                title="Dormy Inn",
                url=expected_url,
                visibility_state="hidden",
                has_focus=False,
            ),
            html="<html><body>browser snapshot</body></html>",
        )


class _DiscardedChromeFetcher(_FakeChromeFetcher):
    """模擬 Chrome 回傳 was_discarded 分頁狀態的 fetcher。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """回傳 `was_discarded` 分頁狀態，模擬已被 Chrome 丟棄的頁面。"""
        del fallback_url, preferred_tab_id, page_strategy
        return ChromeTabCapture(
            tab=ChromeTabSummary(
                tab_id="tab-1",
                title="Dormy Inn",
                url=expected_url,
                visibility_state="visible",
                has_focus=True,
                was_discarded=True,
            ),
            html="<html><body>browser snapshot</body></html>",
        )


class _RecordingChromeFetcher(_FakeChromeFetcher):
    """記錄 runtime refresh 時傳入的 preferred tab 與 fallback URL。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None, str | None]] = []

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """記錄 runtime refresh 實際傳入的 URL 與 preferred tab。"""
        del page_strategy
        self.calls.append((expected_url, fallback_url, preferred_tab_id))
        return super().refresh_capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
        )


class _ForbiddenChromeFetcher(_FakeChromeFetcher):
    """模擬 Chrome 分頁在刷新時被站方以 403 阻擋。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """直接拋出含 403 訊號的例外，驗證 runtime 會進入暫停流程。"""
        del expected_url, fallback_url, preferred_tab_id, page_strategy
        raise IkyuBlockedPageError("ikyu 已回傳阻擋頁面。")


class _TimeoutChromeFetcher(_FakeChromeFetcher):
    """模擬專用 Chrome 分頁刷新逾時。"""

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """直接拋出逾時錯誤，驗證 runtime 會映射成 network_timeout。"""
        del expected_url, fallback_url, preferred_tab_id, page_strategy
        raise TimeoutError("refresh timed out")


class _BlockingChromeFetcher(_FakeChromeFetcher):
    """模擬長時間刷新，驗證同一 watch 的檢查會共用同一個 inflight task。"""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """在外部釋放前暫停刷新流程，模擬已在進行中的背景檢查。"""
        del page_strategy
        self.call_count += 1
        self.started.set()
        self.release.wait(timeout=2)
        return super().refresh_capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
        )


class _PausingChromeFetcher(_FakeChromeFetcher):
    """在刷新途中暫停 watch，模擬使用者於 in-flight check 期間操作控制面。"""

    def __init__(
        self,
        *,
        watch_repository: SqliteWatchItemRepository,
        watch_item_id: str,
    ) -> None:
        super().__init__()
        self._watch_repository = watch_repository
        self._watch_item_id = watch_item_id

    def refresh_capture_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        page_strategy=None,
    ) -> ChromeTabCapture:
        """先暫停 watch，再回傳正常 capture，驗證 runtime 會丟棄結果。"""
        del page_strategy
        watch_item = self._watch_repository.get(self._watch_item_id)
        assert watch_item is not None
        self._watch_repository.save(
            replace(watch_item, enabled=True, paused_reason="manually_paused")
        )
        return super().refresh_capture_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
        )


class _PausingOnGetWatchRepository:
    """在第 N 次讀取 watch 時暫停它，模擬後段 control state 變更。"""

    def __init__(
        self,
        repository: SqliteWatchItemRepository,
        *,
        watch_item_id: str,
        pause_on_get_call: int,
    ) -> None:
        """建立會代理原 repository 的測試替身。"""
        self._repository = repository
        self._watch_item_id = watch_item_id
        self._pause_on_get_call = pause_on_get_call
        self.get_call_count = 0

    def __getattr__(self, name: str):
        """未覆寫的方法直接委派給原 repository。"""
        return getattr(self._repository, name)

    def get(self, watch_item_id: str) -> WatchItem | None:
        """在指定讀取次數先暫停 watch，再回傳目前狀態。"""
        self.get_call_count += 1
        if watch_item_id == self._watch_item_id and (
            self.get_call_count == self._pause_on_get_call
        ):
            watch_item = self._repository.get(watch_item_id)
            assert watch_item is not None
            self._repository.save(
                replace(watch_item, enabled=True, paused_reason="manually_paused")
            )
        return self._repository.get(watch_item_id)


class _FailingRestoreChromeFetcher(_FakeChromeFetcher):
    """模擬啟動恢復階段某個分頁建立失敗。"""

    def __init__(self) -> None:
        super().__init__()
        self.failed_once = False

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy=None,
    ) -> ChromeTabSummary:
        """第一次恢復失敗，後續仍允許其它 watch 繼續恢復。"""
        del page_strategy
        self.ensure_calls.append(
            (
                expected_url,
                fallback_url,
                preferred_tab_id,
                excluded_tab_ids,
            )
        )
        if not self.failed_once:
            self.failed_once = True
            raise RuntimeError("restore failed")
        return super().ensure_tab_for_url(
            expected_url=expected_url,
            fallback_url=fallback_url,
            preferred_tab_id=preferred_tab_id,
        )


class _BlockingRestoreChromeFetcher(_FakeChromeFetcher):
    """模擬啟動恢復分頁時站台載入很慢的 Chrome fetcher。"""

    def __init__(self) -> None:
        """建立可由測試控制釋放時機的阻塞 fetcher。"""
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def ensure_tab_for_url(
        self,
        *,
        expected_url: str,
        fallback_url: str | None = None,
        preferred_tab_id: str | None = None,
        excluded_tab_ids: tuple[str, ...] = (),
        page_strategy=None,
    ) -> ChromeTabSummary:
        """等測試釋放後才回傳分頁摘要，用來驗證 start 不會被卡住。"""
        del page_strategy
        self.ensure_calls.append(
            (
                expected_url,
                fallback_url,
                preferred_tab_id,
                excluded_tab_ids,
            )
        )
        self.started.set()
        self.release.wait(timeout=5)
        return ChromeTabSummary(
            tab_id=preferred_tab_id or "restored-tab-blocking",
            title="Dormy Inn",
            url=fallback_url or expected_url,
            visibility_state="visible",
            has_focus=True,
        )


class _RecordingNotifier:
    """記錄 dispatcher 實際送出的通知訊息。"""

    channel_name = "desktop"

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> None:
        """保存 dispatch 傳入的通知訊息。"""
        self.messages.append(message)


class _FailingNotifier:
    """模擬單一通知通道失敗，驗證 runtime 不會因此中止。"""

    def __init__(self, channel_name: str, message: str = "forced failure") -> None:
        self.channel_name = channel_name
        self._message = message

    def send(self, message: NotificationMessage) -> None:
        """固定拋出錯誤，模擬外部通知通道失敗。"""
        del message
        raise RuntimeError(self._message)


class _PausingNotifier(_RecordingNotifier):
    """送出通知時暫停 watch，模擬 dispatch 期間的手動控制命令。"""

    def __init__(
        self,
        *,
        watch_repository: SqliteWatchItemRepository,
        watch_item_id: str,
    ) -> None:
        """建立會在 send 時改變 control state 的 notifier。"""
        super().__init__()
        self._watch_repository = watch_repository
        self._watch_item_id = watch_item_id

    def send(self, message: NotificationMessage) -> None:
        """先記錄通知，再暫停 watch。"""
        super().send(message)
        watch_item = self._watch_repository.get(self._watch_item_id)
        assert watch_item is not None
        self._watch_repository.save(
            replace(watch_item, enabled=True, paused_reason="manually_paused")
        )


async def _wait_for_startup_restore(runtime: ChromeDrivenMonitorRuntime) -> None:
    """等待 runtime 背景啟動恢復任務完成，供測試檢查 restore 副作用。"""
    task = runtime._startup_restore_task
    if task is not None:
        await task


class _CountingNotifierFactory:
    """記錄 notifier factory 呼叫次數，驗證 dispatcher 快取是否生效。"""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(
        self,
        settings: NotificationChannelSettings,
    ) -> tuple[Notifier, ...]:
        """依設定建立最小 notifier 集合。"""
        self.call_count += 1
        if not settings.desktop_enabled:
            return ()
        return (_RecordingNotifier(),)


class _FakeRuntimeAdapter(SiteAdapter):
    """提供 Chrome-driven runtime 測試使用的最小 site adapter。"""

    site_name = "ikyu"

    def match_url(self, url: str) -> bool:
        """判斷測試 adapter 是否支援指定 `ikyu` URL。"""
        return "ikyu.com" in url

    def parse_seed_url(self, url: str) -> SearchDraft:
        """將 seed URL 轉成 runtime 測試用的 search draft。"""
        return SearchDraft(
            seed_url=url,
            hotel_id="00082173",
            room_id="10191605",
            plan_id="11035620",
            check_in_date=date(2026, 9, 18),
            check_out_date=date(2026, 9, 19),
            people_count=2,
            room_count=1,
        )

    def normalize_search_draft(self, draft: SearchDraft) -> SearchDraft:
        """測試 adapter 不額外改寫 search draft。"""
        return draft

    def fetch_candidates(self, draft: SearchDraft):
        """本 runtime 測試不使用候選查詢。"""
        raise NotImplementedError

    def build_preview_from_browser_page(self, *, page_url: str, html: str, diagnostics=()):
        """本 runtime 測試不使用 browser preview。"""
        raise NotImplementedError

    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        """依 browser HTML 建立 runtime 檢查用價格快照。"""
        return PriceSnapshot(
            display_price_text="JPY 22990",
            normalized_price_amount=Decimal("22990"),
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        )

    def build_browser_operation_url(
        self,
        *,
        watch_item: WatchItem,
        draft: SearchDraft | None,
    ) -> str:
        """測試 adapter 也使用正式 target URL，對齊 IKYU runtime 行為。"""
        del draft
        return _build_target_page_url(watch_item.target)

    def resolve_watch_target(
        self,
        draft: SearchDraft,
        selection: CandidateSelection,
    ) -> WatchTarget:
        """本 runtime 測試不使用 watch editor target 解析。"""
        del draft, selection
        raise NotImplementedError


class _AmountByPlanRuntimeAdapter(_FakeRuntimeAdapter):
    """依 plan_id 回傳不同價格，方便驗證多筆 watch 的背景檢查結果。"""

    def build_snapshot_from_browser_page(
        self,
        *,
        page_url: str,
        html: str,
        target: WatchTarget,
    ) -> PriceSnapshot:
        """依不同 plan_id 產生不同 snapshot，確認 runtime 不會互相污染。"""
        del page_url, html
        amount_by_plan = {
            "11035620": Decimal("22990"),
            "11035621": Decimal("24800"),
        }
        amount = amount_by_plan.get(target.plan_id, Decimal("20000"))
        return PriceSnapshot(
            display_price_text=f"JPY {amount}",
            normalized_price_amount=amount,
            currency="JPY",
            availability=Availability.AVAILABLE,
            source_kind=SourceKind.BROWSER,
        )


def _build_notifiers_for_test(
    settings: NotificationChannelSettings,
    notifier: Notifier,
) -> tuple[Notifier, ...]:
    """建立測試用 notifier 集合，固定回傳外部傳入的 notifier。"""
    del settings
    return (notifier,)
