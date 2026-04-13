# hotel_price_watch — 代碼審查報告

> 審查範圍：`src/`、`tests/`、`docs/`、`fixtures/`  
> Schema 版本：v4  
> 審查日期：2026-04-13

本文件聚焦於**尚可加強**與**有潛在風險**的部分。已落地且運作正常的功能（Parser / Fixture tests、Domain 層、SQLite persistence、SiteAdapter 抽象介面、通知規則 evaluator）不在本文重複描述。

---

## 目錄

1. [Critical — Background Monitor Runtime 穩定化](#1-critical--background-monitor-runtime-穩定化)
2. [High — Chrome 分頁識別策略](#2-high--chrome-分頁識別策略)
3. [High — 錯誤映射依賴字串比對](#3-high--錯誤映射依賴字串比對)
4. [High — GUI 缺少啟用/暫停/手動立即檢查操作](#4-high--gui-缺少啟用暫停手動立即檢查操作)
5. [Medium — 通知節流狀態不持久化](#5-medium--通知節流狀態不持久化)
6. [Medium — `NotificationDispatcher` 每次 dispatch 重新建立](#6-medium--notificationdispatcher-每次-dispatch-重新建立)
7. [Medium — Playwright 同步 API 用於 asyncio 環境](#7-medium--playwright-同步-api-用於-asyncio-環境)
8. [Medium — `dev_start` 開發模式 reload 導致 lock file 被誤刪](#8-medium--dev_start-開發模式-reload-導致-lock-file-被誤刪)
9. [Medium — `pid_matches_app` 永遠為 `True`，單實例驗證有漏洞](#9-medium--pid_matches_app-永遠為-true單實例驗證有漏洞)
10. [Medium — 電腦睡眠補掃邏輯僅有純函式，未接到 runtime](#10-medium--電腦睡眠補掃邏輯僅有純函式未接到-runtime)
11. [Medium — Schema migration 只支援線性升級路徑](#11-medium--schema-migration-只支援線性升級路徑)
12. [Low — `views.py` 純字串拼接 HTML，維護成本高](#12-low--viewspy-純字串拼接-html維護成本高)
13. [Low — `main.py` 單檔過長，缺 `APIRouter` 分層](#13-low--mainpy-單檔過長缺-apirouter-分層)
14. [Low — 敏感設定明文存於 SQLite](#14-low--敏感設定明文存於-sqlite)
15. [Low — 歷史頁無圖表，只有表格](#15-low--歷史頁無圖表只有表格)
16. [Low — `ikyu` 阻擋頁識別僅靠 title 與 meta 字串比對](#16-low--ikyu-阻擋頁識別僅靠-title-與-meta-字串比對)
17. [測試覆蓋缺口摘要](#17-測試覆蓋缺口摘要)
18. [建議優先處理順序](#18-建議優先處理順序)

---

## 1. Critical — Background Monitor Runtime 穩定化

### 問題描述

Monitor runtime 透過 `lifespan` 啟動，`ChromeDrivenMonitorRuntime.start()` 會建立 `asyncio.Task` 跑輪詢迴圈，此部分程式碼已存在。但目前有幾個子問題尚未收斂，讓整個 runtime 還不算「穩定可長時間運作」的狀態。

### 子問題 A：`_run_loop` 不捕捉頂層 exception

若 `_run_loop` 內部未被 `try/except` 保護的路徑拋出非預期例外，整個 loop task 會靜默結束，`_loop_task.done()` 會回傳 `True`，但 `is_running` 的計算邏輯：

```python
is_running=self._loop_task is not None and not self._loop_task.done(),
```

此時就會回傳 `False`，但 GUI 上不會有任何主動提示，使用者只能在 `/health` 看到 `"status": "degraded"`，很容易被忽略。

**建議**：在 `_run_loop` 最外層加 `try/except Exception as exc`，記錄 traceback 並寫入可觀測狀態，必要時嘗試自動重啟。

### 子問題 B：`_inflight_tasks` 在 `stop()` 時依賴取消，未等待乾淨結束

```python
for task in inflight_tasks:
    task.cancel()
for task in inflight_tasks:
    with suppress(asyncio.CancelledError):
        await task
```

這段取消邏輯在 `asyncio.to_thread()` 中跑的 `refresh_capture_for_url`（同步 Playwright 呼叫）無法被 `CancelledError` 中斷，因為它是在 thread 中執行。實際上 `stop()` 只能讓 asyncio task 標記取消，但 Playwright 的 blocking 呼叫仍會繼續跑完，`stop()` 返回後 Playwright thread 可能還在進行頁面刷新。

**風險**：app 關閉後仍有背景 thread 附著 Chrome、修改 DB 狀態，若 SQLite 連線沒有正確關閉，下次啟動有機率遇到鎖定問題。

**建議**：考慮為 `ChromeCdpHtmlFetcher` 加入取消旗標（`threading.Event`），在 stop 時設旗，讓長時間的 Playwright 操作能提早放棄。

### 子問題 C：`_sync_watch_definitions` 與 DB 查詢在每個 tick 執行

`_run_loop` 每個 tick 都會呼叫 `_sync_watch_definitions`，後者會 `list_all()` 從 DB 撈出全部 watch item 再做 diff。若 watch item 數量增加，這個 pattern 效率偏低，且在高頻 tick（`tick_seconds=1.0`）下會對 SQLite 產生持續讀取壓力。

**建議**：watch 的 CRUD 操作後，透過 event 或 flag 通知 runtime 重新同步，而非每 tick 都全量讀取。

---

## 2. High — Chrome 分頁識別策略

### 問題描述

`refresh_capture_for_url()` 的頁面選取邏輯分三層：
1. `preferred_tab_id`（從 `watch_item_drafts.browser_tab_id` 讀出）
2. URL 比對（`_find_best_page`，使用評分系統）
3. 找不到時 `new_page().goto()`

**問題一：`preferred_tab_id` 不穩定**

`tab_id` 是 Playwright 的 `page.url` hash 加上時間戳組合（或類似機制），這個值在 Chrome 重啟、分頁重新整理、或使用者手動關掉再開後都會失效。一旦 `preferred_tab_id` 失效，fallback 到 URL 比對。

**問題二：URL 評分系統有誤判空間**

```python
if current_signature.room_id is not None and current_signature.room_id == expected_signature.room_id:
    score += 25
if current_signature.plan_id is not None and current_signature.plan_id == expected_signature.plan_id:
    score += 25
```

若使用者在同一個 Chrome session 中開了同一間飯店、不同日期的多個分頁，`room_id` 和 `plan_id` 相符，`check_in` 不符只扣 8 分，仍然可能選到錯誤分頁（滿分 100，錯誤分頁可能得到 50+ 分）。

**問題三：`_find_best_page` 選出最高分後沒有設最低門檻**

目前選出分數最高的頁面就直接使用，即使最高分只有 1（代表只有 domain 相符）也會被選中，然後刷新後解析，可能抓到不相關的 ikyu 頁面。

**建議**：
- 為 `_find_best_page` 加入最低分門檻（例如 ≥ 30 才視為有效比對）
- 若比對失敗，應寫入 `debug_artifact` 並標記為 `UNKNOWN`，不應靜默地刷新任何 ikyu 分頁
- 長期方向：考慮在建立 watch 時讓使用者確認分頁，並用 CDP level 的 `targetId`（比 page URL hash 更穩定的識別子）儲存

---

## 3. High — 錯誤映射依賴字串比對

### 問題描述

```python
def _map_runtime_exception_to_error_code(exc: Exception) -> CheckErrorCode:
    message = str(exc)
    if "阻擋頁面" in message or "403" in message:
        return CheckErrorCode.FORBIDDEN_403
    if "timeout" in message.lower() or "逾時" in message:
        return CheckErrorCode.NETWORK_TIMEOUT
    return CheckErrorCode.NETWORK_ERROR
```

這個函式依賴例外的字串訊息來判斷錯誤類型，有幾個問題：

1. `"403"` 是過度寬泛的比對，任何訊息中帶有 `403` 字樣（例如 `"room plan 403-B is unavailable"`）都會被誤判為 FORBIDDEN
2. `"阻擋頁面"` 是 `IkyuBlockedPageError` 的中文訊息，若未來訊息改版（或有多語系）就會失效
3. Playwright 的 timeout 例外是 `playwright.sync_api.Error`，有明確的型別，應用 `isinstance` 而非字串

**建議**：
- 讓 `IkyuBlockedPageError` 繼承一個有明確語意的 base class（例如 `BlockedPageError`），在 `except` 中直接捕捉型別
- 對 Playwright `Error`、`TimeoutError` 分開 `except`
- 對 `_map_runtime_exception_to_error_code` 補充 `isinstance` 路徑

```python
# 建議改成
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout

except PlaywrightTimeout:
    error_code = CheckErrorCode.NETWORK_TIMEOUT
except IkyuBlockedPageError:
    error_code = CheckErrorCode.FORBIDDEN_403
except PlaywrightError:
    error_code = CheckErrorCode.NETWORK_ERROR
```

---

## 4. High — GUI 缺少啟用/暫停/手動立即檢查操作

### 問題描述

`V1_SPEC.md` 第 8.1 節明確列出 GUI V1 至少需要：

> - 啟用 / 暫停
> - 手動立即檢查

但審查 `main.py` 全部 route 後，確認目前**只有以下 watch 操作 route**：
- `GET /watches/new` — 新增頁面
- `GET /watches/chrome-tabs` — 分頁選取
- `POST /watches/chrome-tabs/preview` — preview
- `POST /watches/preview` — preview（URL 入口）
- `POST /watches` — 建立
- `GET /watches/{id}` — 詳細頁
- `GET /watches/{id}/notification-settings` — 通知設定頁
- `POST /watches/{id}/notification-settings` — 更新通知設定
- `POST /watches/{id}/delete` — 刪除

**以下 route 完全缺失**：
- `POST /watches/{id}/enable` 或 `POST /watches/{id}/toggle-enabled`
- `POST /watches/{id}/pause` / `POST /watches/{id}/unpause`
- `POST /watches/{id}/check-now`（手動立即觸發一次檢查）

這意味著使用者目前無法從 UI 暫停一個在背景輪詢的 watch（只能刪除），也無法在不等排程的情況下立即確認一個 watch 的當前價格。

`WatchItem` 資料模型有 `enabled` 和 `paused_reason` 欄位，repository 也有對應的 `save()` 可以更新，但整條 HTTP → service → repository 的路徑尚未接通。

**建議**：補上以下 route（都是簡單的 POST → update → redirect）：

```
POST /watches/{id}/enable      → watch.enabled = True,  paused_reason = None
POST /watches/{id}/disable     → watch.enabled = False
POST /watches/{id}/check-now   → runtime.reschedule_now(id) 或直接 run_watch_check_once()
```

---

## 5. Medium — 通知節流狀態不持久化

### 問題描述

```python
class InMemoryNotificationThrottle:
    def __init__(self) -> None:
        self._last_sent_at_by_channel_key: dict[tuple[str, str], datetime] = {}
```

`InMemoryNotificationThrottle` 的狀態完全存在記憶體，app 重啟後歸零。

目前 runtime 的 cooldown 設定：
```python
cooldown_seconds_by_channel={
    "desktop": 60,
    "ntfy": 300,
    "discord": 300,
}
```

**風險場景**：使用者因電腦重啟/更新導致 app 重啟，重啟後若在 300 秒冷卻期內 scheduler 再次偵測到符合通知條件（例如 ntfy 剛在重啟前 5 分鐘送過），會再次送出通知，造成重複推送。

更嚴重的是 `NotificationState`（domain 層的去重狀態）是持久化在 SQLite 的，但 throttle 不是，造成兩層去重機制在重啟後不一致。

**建議**：將 `_last_sent_at_by_channel_key` 的狀態加入 `notification_states` 表的欄位（或獨立的 `notification_throttle_states` 表），在 `mark_delivered` 時同時寫 DB，啟動時從 DB 載入。

---

## 6. Medium — `NotificationDispatcher` 每次 dispatch 重新建立

### 問題描述

```python
def _dispatch_notification(self, watch_item, check_result, notification_decision, attempted_at):
    settings = self._app_settings_service.get_notification_channel_settings()
    enabled_notifiers = self._notifier_factory(settings)
    if not enabled_notifiers:
        return None

    dispatcher = NotificationDispatcher(
        notifiers=tuple(enabled_notifiers),
        throttle=self._notification_throttle,   # ← 共用
        cooldown_seconds_by_channel={...},
    )
    ...
```

每次有 watch 需要通知時，都會：
1. 從 DB 讀一次 `notification_channel_settings`（`get_notification_channel_settings()`）
2. 建立新的 notifier 物件清單
3. 建立新的 `NotificationDispatcher` 物件

只有 `_notification_throttle` 是共用的。

**問題**：
- 每次通知都觸發一次 SQLite 讀取
- 多個 watch item 同時觸發通知時（`max_workers=2`），可能同時建立兩個 `NotificationDispatcher`，雖然共用同一個 throttle，但 DB 讀取的 settings 可能在兩個呼叫之間被使用者修改，造成同一批通知使用不同設定

**建議**：在 runtime 啟動時建立一份 `NotificationDispatcher`，設定改變時重建，而不是每次 dispatch 都建立。可以用一個 `_dispatcher: NotificationDispatcher | None` 欄位搭配失效旗標來管理。

---

## 7. Medium — Playwright 同步 API 用於 asyncio 環境

### 問題描述

```python
def _connect_playwright_browser(self):
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(self.cdp_endpoint)
        return browser, playwright
    except ...:
        playwright.stop()
        raise
```

`ChromeCdpHtmlFetcher` 全程使用 `playwright.sync_api`，在 `asyncio` 環境中透過 `asyncio.to_thread()` 包裝執行。

**問題**：

1. 每次呼叫 `_connect_playwright_browser()` 都會 `sync_playwright().start()`，這會建立一個新的 Playwright 管理 process（或 subprocess context），再 `playwright.stop()` 銷毀它。每次 `refresh_capture_for_url` 都需要完整的 start/connect/stop 週期，overhead 顯著。

2. `sync_playwright()` 在 asyncio event loop 中用 `asyncio.to_thread` 包裝時，Playwright 的內部 event loop 與 asyncio 的 event loop 是隔離的，但 Playwright 的 `sync_api` 本身會建立自己的 event loop（`asyncio.new_event_loop()`）。如果 asyncio worker thread 的數量超出預期，可能造成 Playwright 的 nested event loop 問題。

3. 目前 `max_workers=2` 讓最多兩個 watch 同時跑，但兩個並行的 `asyncio.to_thread` 呼叫都會同時執行 `sync_playwright().start()`，各自建立獨立的 playwright context，但卻連到同一個 Chrome CDP endpoint（`http://127.0.0.1:9222`）。Playwright 對同一 CDP endpoint 的多重連線行為沒有明確保證，可能造成分頁狀態衝突。

**建議**：考慮遷移到 `playwright.async_api` 並在 runtime 層維護一個長存的 `Browser` 物件，讓多個 watch 共用同一個 browser context，僅對個別 page 操作使用獨立的 async task。

---

## 8. Medium — `dev_start` 開發模式 reload 導致 lock file 被誤刪

### 問題描述

```python
try:
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,   # 預設 True
    )
finally:
    remove_lock_record(lock_path)
```

`HOTEL_PRICE_WATCH_RELOAD` 預設為 `"1"`，即開發模式預設啟用 reload。

**問題**：`uvicorn --reload` 會啟動一個 supervisor process，再 fork 出 worker process。當 worker 因為 code change 被重啟時，原本的 worker process 結束，`finally` 區塊會執行 `remove_lock_record(lock_path)`，刪掉 lock file。但此時 supervisor（父 process）還在，port 仍然被占用。

下次使用者若又執行 `dev_start`，`port_in_use=True` 且 `lock_record=None`（因為 lock file 被刪），進入 `ERROR_PORT_CONFLICT`，會拋出錯誤，要求使用者確認 port 是否被其他程式占用，而實際上是自己的 supervisor 在跑。

**建議**：
- 生產模式關閉 reload（`HOTEL_PRICE_WATCH_RELOAD=0`）
- 或在 lock file 中額外儲存 supervisor PID，讓 `_pid_exists` 驗證 supervisor 而非 worker
- 最簡單的短期解法：在 finally 區塊中只在 `uvicorn.run` 是非 reload 模式時才刪 lock

---

## 9. Medium — `pid_matches_app` 永遠為 `True`，單實例驗證有漏洞

### 問題描述

```python
pid_exists = _pid_exists(lock_record.pid) if lock_record is not None else None
pid_matches_app = True if lock_record is not None and pid_exists else None
```

`pid_matches_app` 的邏輯只檢查「PID 是否存在」，存在就直接視為「是本 app 的 process」。但 PID 在 OS 是可以被回收再用的，一個 `lock_record.pid = 12345` 的 lock file 留下後，若恰好有另一個完全不相關的程式剛好拿到 PID 12345，`pid_matches_app` 就會是 `True`，`decide_single_instance_startup` 會回傳 `REUSE_EXISTING`，然後去探測 `/health`。

雖然後面還有 `/health` 探測與 `instance_id` 比對作為第二道防線，但 `pid_matches_app=True` 的錯誤假設仍會讓 `decide_single_instance_startup` 走到 `REUSE_EXISTING` 而不是 `ERROR_PORT_CONFLICT`，導致邏輯路徑不一致。

真正的 PID 驗證應該要確認「這個 PID 的 process 名稱/command line 是否為本 app」，例如透過 `psutil.Process(pid).cmdline()` 檢查。

**建議**：
```python
# 使用 psutil 確認 process 確實是本 app
import psutil

def _pid_belongs_to_app(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline())
        return "hotel_price_watch" in cmdline or "app.tools.dev_start" in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
```

---

## 10. Medium — 電腦睡眠補掃邏輯僅有純函式，未接到 runtime

### 問題描述

`policies.py` 中有：

```python
def should_trigger_wakeup_rescan(
    *,
    resumed_at: datetime,
    last_checked_at: datetime | None,
    backoff_until: datetime | None,
) -> bool:
```

這個函式的邏輯是正確的，但**在整個 `src/app/` 中，除了 `tests/` 外，沒有任何地方呼叫這個函式**。

V1 Spec 第 7 節明確要求：
> 電腦從睡眠恢復後應盡快補掃一次

但 runtime 的 `_run_loop` 沒有接上任何睡眠偵測機制：
- 沒有監聽 Windows 的 `WM_POWERBROADCAST`（PBT_APMRESUMEAUTOMATIC / PBT_APMSUSPEND）
- 沒有比較 `last_tick_at` 與 `_utcnow()` 的差距來推斷睡眠中斷

在 `asyncio.sleep(tick_seconds)` 的迴圈中，若電腦睡眠，tick 會暫停，醒來後從上次 tick 繼續，不會自動補觸發。

**建議**：在 `_run_loop` 每次 tick 時比對與上次 tick 的實際時間差，若超過 `tick_seconds * N`（例如 5 倍），推定為剛從睡眠恢復，並對所有 enabled watch 呼叫 `scheduler.reschedule_now()`。

```python
now = _utcnow()
if self._last_tick_at is not None:
    gap = (now - self._last_tick_at).total_seconds()
    if gap > self._tick_seconds * 5:
        # 推定為剛從睡眠恢復，補掃所有 watch
        self._trigger_wakeup_rescan(now)
```

---

## 11. Medium — Schema migration 只支援線性升級路徑

### 問題描述

```python
def _migrate_schema_if_supported(connection: sqlite3.Connection) -> None:
    current_value = row["value"]
    if current_value == "2" and CURRENT_SCHEMA_VERSION >= 3:
        current_value = "3"
    if current_value == "3" and CURRENT_SCHEMA_VERSION == 4:
        connection.execute("ALTER TABLE watch_item_drafts ADD COLUMN browser_tab_id TEXT")
        connection.execute("ALTER TABLE watch_item_drafts ADD COLUMN browser_page_url TEXT")
        current_value = "4"
```

**問題一：只能從 v2 升級，不能從 v1 或跨版本升級**

若有人用非常舊的 v1 資料庫（或 v1 建立的結構沒有 `metadata` 表），`row` 為 `None` 時直接 `return`，接著 `_validate_existing_schema_version` 會因為讀不到版本而拋出 `SchemaVersionMismatchError`，而不是做 migration。

**問題二：migration 沒有 transaction 保護**

```python
connection.execute("ALTER TABLE watch_item_drafts ADD COLUMN browser_tab_id TEXT")
connection.execute("ALTER TABLE watch_item_drafts ADD COLUMN browser_page_url TEXT")
connection.execute("UPDATE metadata SET value = ? ...", ("4",))
```

這三個操作不在同一個 `BEGIN TRANSACTION` 中。若中間執行失敗（例如磁碟空間不足），`metadata` 的版本號可能已更新但欄位尚未加上，或欄位已加但版本號未更新，導致下次啟動時 schema 狀態不一致。

**建議**：
- 在 migration 函式中明確使用 `connection.execute("BEGIN")` / `connection.execute("COMMIT")` 包裝
- 補齊 v1 → v4 的直接升級路徑，或至少在 v1 時給出明確的使用者錯誤訊息

---

## 12. Low — `views.py` 純字串拼接 HTML，維護成本高

### 問題描述

`views.py` 目前 1396 行，全部是 Python 函式回傳 f-string 拼接的 HTML 字串：

```python
def _render_price_history_section(price_history: tuple[PriceHistoryEntry, ...]) -> str:
    if not price_history:
        return "<p>尚無價格歷史。</p>"
    rows = ""
    for entry in price_history[-20:]:
        rows += f"""
            <tr>
              <td>{escape(entry.captured_at.strftime(...))}</td>
              ...
            </tr>
        """
    return f"<table>...</table>"
```

**問題**：
1. **可讀性低**：HTML 結構與 Python 邏輯混在一起，找一個 UI 元素需要在長串 f-string 裡搜尋
2. **測試方式原始**：`test_web_app.py` 透過比對 HTML 字串來驗證 UI，例如 `assert "已建立" in response.text`，這種測試脆弱，任何格式調整都可能破壞測試
3. **難以加入動態功能**：若要加入排序、篩選、折疊等動態 UI，全部都要用 JavaScript 字串塞進 HTML 字串裡，可讀性極差
4. **`html.escape()` 的呼叫一致性**：目前有些地方有 escape，有些地方直接用 f-string 拼 user 輸入，若未來擴充 URL 入口或備注欄位，有 XSS 風險

**建議**：引入 [Jinja2](https://jinja.palletsprojects.com/)（FastAPI 本身支援 `Jinja2Templates`），將 HTML 移到 `templates/` 目錄下，Python 層只負責傳資料物件。這個重構不需要一次做完，可以逐頁遷移。

---

## 13. Low — `main.py` 單檔過長，缺 `APIRouter` 分層

### 問題描述

`main.py` 目前約 500 行，包含所有 route handler（watch CRUD、通知設定、debug captures）以及若干輔助函式（`_read_form_data`、`_parse_candidate_key`、`_safe_preview` 等）。

所有 route 都直接定義在 `create_app()` 內部的閉包中，這讓：
1. `create_app()` 函式本身的行數過長，難以閱覽整體結構
2. 測試時若要只測試部分 route 的行為，需要初始化整個 app
3. 日後加入新頁面（例如統計頁、多站管理頁）會讓這個檔案更長

**建議**：用 `APIRouter` 依功能域拆分：

```python
# web/routers/watches.py
router = APIRouter(prefix="/watches", tags=["watches"])

@router.get("/{watch_item_id}")
def watch_detail_page(...): ...

# web/routers/settings.py
router = APIRouter(prefix="/settings", tags=["settings"])

# main.py
app.include_router(watches_router)
app.include_router(settings_router)
app.include_router(debug_router)
```

---

## 14. Low — 敏感設定明文存於 SQLite

### 問題描述

Discord webhook URL 與 ntfy server URL 直接以純文字存在 SQLite 的 `app_settings` 資料表：

```sql
key TEXT PRIMARY KEY,
value TEXT NOT NULL
```

`discord_webhook_url` 是可以直接用來向你的 Discord channel 發送任意訊息的憑證，若資料庫檔案（預設為 `data/hotel_price_watch.db`）被意外分享或備份上傳，webhook 就會洩漏。

**建議**：
- 短期：文件中明確說明 `data/` 目錄不應納入版本控制，在 `.gitignore` 中確保 `data/*.db` 已排除（目前的 `.gitignore` 需確認）
- 中期：使用 Windows Credential Manager（`keyring` 套件）儲存 webhook URL 等憑證，DB 中只存一個 key reference
- 至少：在 GUI 的設定頁顯示「此資訊儲存於本機，請勿將資料庫檔案分享給他人」提示

---

## 15. Low — 歷史頁無圖表，只有表格

### 問題描述

`_render_price_history_section` 目前只渲染一個純 HTML 表格（最近 20 筆）：

```python
for entry in price_history[-20:]:
    rows += f"<tr><td>...</td>...</tr>"
```

V1 Spec 第 8.1 節：
> 歷史頁 V1 先以表格呈現，圖表列入後續版本。

這是符合 spec 的，但實際使用上，若想看價格趨勢（例如價格過去兩週是漲是跌），需要自己看表格心算。尤其當追蹤多個日期或等待長時間的降價，表格可讀性遠不及折線圖。

**建議**：可用純前端方案（`<canvas>` + Chart.js CDN）在不修改後端的情況下加入簡易折線圖，不需要新增任何 API route。

---

## 16. Low — `ikyu` 阻擋頁識別僅靠 title 與 meta 字串比對

### 問題描述

```python
blocked_title_markers = [
    "アクセスしようとしたページは表示できませんでした".lower(),
    "access denied",
    "forbidden",
]
blocked_body_markers = [
    'meta name="robots" content="noindex"',
    'meta name="robots" content="nofollow"',
]
```

**問題**：
1. `noindex` 和 `nofollow` 是 `robots` 的合法 meta，正常飯店房型頁面也可能同時有這兩個，容易誤判
2. ikyu 未來若改變阻擋頁面的結構（改用 JavaScript redirect、改變 title 文字），這段邏輯就會失效，且失敗是靜默的（只是沒有觸發 `IkyuBlockedPageError`，直接進 parser 解析阻擋頁的 HTML，然後得到 `PARSE_ERROR` 或 `TARGET_MISSING`，難以區分是正常解析失敗還是被擋）

**建議**：
- 把 `noindex + nofollow` 同時出現的條件拿掉，或改成更具體的 ikyu 特定識別（例如特定 CSS class 或 JSON-LD 缺失）
- 在 parser 層加入「這頁連基本飯店資訊都沒有」的偵測，作為阻擋頁的備份判斷

---

## 17. 測試覆蓋缺口摘要

| 項目 | 現況 | 缺口 |
|------|------|------|
| Parser fixture tests | ✅ 完整，4 類情境 | — |
| Domain notification engine | ✅ 完整 | — |
| Monitor scheduler 純邏輯 | ✅ 覆蓋 | — |
| Monitor runtime 啟停 | ✅ 初步 | 缺長時間迴圈穩定性、`_run_loop` 崩潰後恢復 |
| Chrome tab 識別 | ⚠️ 部分 | 缺同一飯店多分頁的誤判情境、tab_id 失效 fallback |
| 通知 runtime 發送 | ⚠️ 最小 | 缺重啟後 throttle 狀態歸零的重複發送測試 |
| 單實例整合 e2e | ⚠️ 部分 | 缺 reload 模式下 lock file 被刪的場景 |
| enable/pause/manual-check route | ❌ 缺路由 | 完全沒有 |
| 睡眠補掃 | ❌ 未接 | `should_trigger_wakeup_rescan` 只有純函式測試，runtime 未呼叫 |
| `_map_runtime_exception_to_error_code` | ❌ 無測試 | 字串比對邏輯完全沒有測試 |
| Schema migration v1→v4 直接路徑 | ❌ 未覆蓋 | 只測了正常啟動，無 v1 資料庫升級測試 |

---

## 18. 建議優先處理順序

以下以 **影響範圍 × 實作難度** 排列：

### 第一優先（影響正確性，應在正式使用前修復）

1. **[#3] 錯誤映射改用型別判斷**：修改量小，風險高，10 分鐘可完成
2. **[#4] 補 enable/pause/manual-check route**：直接接既有 service/repository，無需新依賴
3. **[#9] `pid_matches_app` 補充 `psutil` 驗證**：加一個 dependency，避免 stale lock 誤判

### 第二優先（影響長時間穩定性）

4. **[#1A] `_run_loop` 加頂層 exception 捕捉**
5. **[#10] 接上睡眠補掃邏輯**：在 `_run_loop` 比較 tick 間隔，呼叫已有的 `should_trigger_wakeup_rescan`
6. **[#5] 通知節流狀態持久化**：加 2 欄到 `notification_states` 表，補 migration
7. **[#8] `dev_start` reload 模式下的 lock file 管理**

### 第三優先（架構改善，可漸進進行）

8. **[#2] Chrome 分頁識別加最低分門檻**
9. **[#6] `NotificationDispatcher` 改為長存共用**
10. **[#11] Schema migration 加 transaction 保護**
11. **[#12] `views.py` 引入 Jinja2**（可逐頁遷移）
12. **[#13] `main.py` 拆 `APIRouter`**

### 長期方向（V2+ 才需要考慮）

- **[#7] Playwright 遷移到 async API + 長存 browser context**
- **[#14] 憑證改存 Windows Credential Manager**
- **[#15] 歷史頁加折線圖**
