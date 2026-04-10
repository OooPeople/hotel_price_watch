# Architecture Plan

## 1. 設計方向

本專案沿用原 userscript 模板的核心觀念，但不照抄瀏覽器腳本結構。

沿用的觀念：

- 設定與 runtime state 分離
- 排程與掃描引擎分離
- 通知模組獨立
- 可觀測的 latest scan / latest notification 狀態
- 可測試的 parser 與 helper

需要重寫的部分：

- DOM selector 與 userscript UI
- Tampermonkey storage
- 依賴頁面生命週期的 observer orchestration

同時，本專案也借鏡 `tickets_hunter` 的方向，但不複製其單一大型腳本結構。

保留的概念：

- configuration-driven
- site-specific implementation
- 設定頁與引擎分離
- 後續可擴站

不沿用的部分：

- 把多站平台邏輯集中在單一主檔
- 以函式命名規則分隔平台而不是套件分層

## 2. 建議目錄

```text
hotel_price_watch/
├─ docs/
├─ fixtures/
├─ src/
│  └─ app/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ bootstrap/
│     ├─ config/
│     ├─ domain/
│     ├─ application/
│     ├─ infrastructure/
│     ├─ monitor/
│     ├─ notifiers/
│     ├─ sites/
│     │  ├─ base.py
│     │  ├─ registry.py
│     │  └─ ikyu/
│     └─ web/
├─ tests/
└─ README.md
```

## 3. 分層與模組責任

### 3.1 `domain`

放純資料模型與核心規則，不依賴框架或外部 IO。

建議內容：

- `entities.py`
- `value_objects.py`
- `events.py`
- `enums.py`
- `notification_rules.py`

核心物件例子：

- `SearchDraft`
- `OfferCandidate`
- `WatchTarget`
- `PriceSnapshot`
- `CheckResult`
- `NotificationDecision`
- `NotificationRule`
- `LatestCheckSnapshot`

重要約束：

- `normalized_price_amount` 固定表示該 `watch target` 在當次條件下的總支付金額
- 每人每晚價格屬於衍生展示值，不作為正式比價基準
- `NotificationRule` 的 domain model 需支援 leaf rule 與 composite node
- V1 UI 雖只提供單一 leaf rule，storage / evaluator 仍需預留 `AND` / `OR` 擴充點

### 3.2 `application`

放 use case / orchestration，不直接碰具體框架細節。

建議內容：

- `create_watch_from_url.py`
- `refresh_candidates.py`
- `run_watch_check.py`
- `enable_disable_watch.py`
- `acknowledge_error.py`

這層負責把 domain、repository、site adapter、notifier 串起來。

### 3.3 `config`

- 載入設定
- 儲存全域設定
- 驗證欄位

### 3.4 `infrastructure`

- `db/`
- `http/`
- `browser/`
- `notifications/`
- `logging/`

這層包裝具體技術實作：

- SQLite / SQLAlchemy
- HTTP client
- Playwright fallback
- Desktop / Discord / `ntfy`
- file lock
- single-instance coordination
- schema migration/versioning

### 3.5 `sites`

站點擴充的核心區塊。

每個網站都實作同一組 adapter 介面。

`sites/base.py` 內建議定義 `SiteAdapter` 抽象介面，至少包含：

- `parse_seed_url()`
- `normalize_search_draft()`
- `fetch_candidates()`
- `resolve_watch_target()`
- `fetch_target_snapshot()`

`sites/registry.py` 負責：

- 註冊支援站點
- 依 URL 判斷使用哪個 adapter

`sites/ikyu/` 內再拆：

- `normalizer.py`
- `parser.py`
- `resolver.py`
- `models.py`
- `client.py`

### 3.6 `monitor`

- 單次檢查流程
- 狀態比對
- 排程
- 錯誤退避
- 喚醒後補掃
- worker queue
- 通知規則評估
- 通知去重

### 3.7 `notifiers`

- desktop notification
- `ntfy`
- Discord

### 3.8 `web`

- 本機 web UI
- 管理頁
- 最近狀態頁
- API router
- HTML template
- static assets

## 4. 持久化模型

持久化模型建議至少拆成：

- `watch_items`
- `latest_check_snapshots`
- `check_events`
- `price_history`
- `notification_states`
- `debug_artifacts`

其中：

- `watch_items` 只保存使用者設定、`watch_target` 與通知規則
- `latest_check_snapshots` 保存最新執行狀態與 backoff / degraded
- `check_events` 保存每次檢查的整理後事件歷史，包含成功、失敗、availability 變化與通知結果
- `price_history` 保存每次成功解析出的價格快照
- `notification_states` 保存去重與上次通知狀態
- `debug_artifacts` 保存解析失敗時的 HTML / hydration 摘要

`currency` 應視為 snapshot 屬性，不作為 `WatchTarget` identity 的正式欄位。

`watch_items` 不應保存以下 runtime 欄位：

- 最新價格
- `display_price_text`
- `last_seen_availability`
- `last_checked_at`
- `last_error_code`
- `last_notified_at`

## 5. Site Adapter 設計

這是本專案可擴站的關鍵。

### 5.1 原則

- UI 不直接依賴 `ikyu` parser 細節
- monitor engine 不直接依賴站點 HTML 結構
- 新增網站時，優先新增一個新 adapter，而不是修改監看核心

### 5.2 推薦資料流

1. web UI 收到 seed URL
2. registry 選出 site adapter
3. adapter 解析 `SearchDraft`
4. application service 呼叫 adapter 取候選項
5. 使用者確認後，由 adapter 產生 `WatchTarget`
6. monitor engine 之後只吃 `WatchTarget`

### 5.3 為什麼這比直接存 URL 更好

- URL 只是輸入，不是穩定領域模型
- 使用者在 UI 改日期後，URL 已經不是唯一資料來源
- 未來不同網站 query 格式不同，不能要求核心層直接理解所有網站 URL

### 5.4 最小契約

每個 site adapter 至少要有以下輸入 / 輸出契約：

- `match_url(url: str) -> bool`
- `parse_seed_url(url: str) -> SearchDraft`
- `normalize_search_draft(draft: SearchDraft) -> SearchDraft`
- `fetch_candidates(draft: SearchDraft) -> CandidateBundle`
- `resolve_watch_target(draft: SearchDraft, selection: CandidateSelection) -> WatchTarget`
- `fetch_target_snapshot(target: WatchTarget) -> PriceSnapshot`

建議輸入 / 輸出形狀保持站點無關：

- 輸入只吃 `SearchDraft` / `WatchTarget`
- 輸出只回 `CandidateBundle` / `PriceSnapshot`
- 不讓 web UI 或 scheduler 直接依賴 `ikyu` HTML 細節

`PriceSnapshot` 建議最小欄位：

- `display_price_text`
- `normalized_price_amount`
- `currency`
- `availability`
- `captured_at`
- `source_kind`

`availability` 在 V1 固定使用：

- `available`
- `sold_out`
- `unknown`
- `parse_error`
- `target_missing`

## 6. Local Web UI 與背景引擎的邊界

### 6.1 建議做法

- `FastAPI` 僅提供本機 UI 與 API
- 背景引擎由 app startup 時建立
- `lifespan` 管理啟停
- 長時間監看 loop 使用 `asyncio` task 與 queue
- 啟動時先做固定 port 檢查
- 再做 lock file 檢查，確保 scheduler 只會有一份

### 6.2 不建議做法

- 把長時間監看放在 request handler 裡
- 把主 scheduler 當成 FastAPI `BackgroundTasks`
- 每次 request 都新建共享 runtime

### 6.3 單實例策略

V1 採三段式保護：

- 固定 port 檢查
- lock file
- PID 驗證

建議行為：

1. 啟動時先檢查本機管理介面 port 是否已被既有實例占用
2. 再讀取 lock file，內容至少保存 `pid`、`started_at_utc`、`instance_id`
3. 若 lock file 存在，需驗證 PID 是否仍存活，且是否對應本 app runtime
4. 若既有實例存在，新的啟動流程不再建立第二份 monitor runtime
5. 若 lock file 存在但 PID 已不存在，視為 stale lock，啟動時自動清理
6. 若 port 被無關程序占用，應顯示明確錯誤，不嘗試搶占或強制覆蓋
7. 正常關閉時移除 lock file；非正常關閉則由下次啟動時的 PID 驗證處理 recovery
8. 若偵測到既有實例，可直接導向現有 UI，而不是啟動新 scheduler

## 7. 函式出入口與責任邊界

### 7.1 Web 層

責任：

- 接收 HTTP request
- 驗證表單輸入
- 呼叫 application service
- 回傳 HTML 或 JSON
- 呈現由總價推導出的每人每晚價格

不負責：

- 直接抓網站
- 直接操作資料庫 transaction 細節
- 直接決定通知邏輯

### 7.2 Application 層

責任：

- 串接 repository、site adapter、notifier
- 執行 use case
- 決定流程順序
- 呼叫通知規則 evaluator

不負責：

- 寫死 HTML selector
- 保存具體 ORM 寫法
- 暴露 framework-specific 型別給 domain

### 7.3 Site Adapter 層

責任：

- 站點 URL 解析
- HTML / hydration 解析
- 站點候選項查詢
- 站點 snapshot 抓取

不負責：

- 排程
- watch item CRUD
- 通知節流

### 7.4 Repository 層

責任：

- watch item、history、snapshot、debug artifact 的持久化

不負責：

- 站點解析
- 事件判定

### 7.5 Monitor 層

責任：

- 排程
- 併發控制
- backoff
- 補掃
- 單次檢查執行
- degraded 狀態管理
- 錯誤升級路徑

不負責：

- web 畫面
- site-specific parser 細節

## 8. 核心資料流與 fallback 策略

### 8.1 核心資料流

1. UI 建立 watch item
2. watch item 存進 SQLite
3. scheduler 取出 enabled items
4. `ikyu` client 抓 HTML
5. parser 解析價格與可訂狀態
6. compare engine 對比舊狀態
7. rule evaluator 對 `PriceSnapshot` 與歷史狀態做通知判定
8. repository 寫入 `latest_check_snapshots`、`check_events` 與必要的 `price_history`
9. notifier 視事件決定是否通知

### 8.2 為什麼先用 HTTP-first

- `ikyu` 目前可從 HTML 與 hydration 資料取得核心價格資訊
- HTTP 模式較省資源，也更適合長時間背景執行
- GUI 與監看引擎可完全分離，不受瀏覽器 tab 凍結影響
- 即使之後加入 browser fallback，也應是 adapter 內部替補機制，而不是主路徑

### 8.3 Browser fallback 觸發條件

只有以下情況才需要考慮：

- 直接 HTML 已拿不到目標價格
- 目標頁需要互動後才會顯示資料
- parser 長期因站點變動失效

即使加入 browser fallback，也應保持：

- 與核心 watch item 模型共用
- 與通知模組共用
- 可單獨關閉

V1 的具體策略先定為：

- `timeout` / 一般 network error：backoff，仍維持 HTTP-first
- `parse_failed` 連續 `3` 次：標記 `degraded`
- `429`：長 backoff，視為 rate-limited
- `403`：暫停該 watch item，提示人工介入
- V1 不自動啟 browser fallback，只保留架構介面

## 9. 測試策略

### 9.1 目標

- parser 與 helper 必須可測試
- `smoke test` 以 parser fixture tests 為核心
- fixture 必須可脫網重跑

### 9.2 測試目錄建議

- `tests/unit/`
  - domain value object、notification rule evaluator、純函式 helper
- `tests/sites/ikyu/`
  - URL normalizer、seed URL parser、candidate resolver、price parser fixture tests
- `tests/integration/`
  - repository、SQLite schema、application use case 的輕量整合測試

### 9.3 Fixture 原則

- `fixtures/ikyu/` 保存可脫網重跑的 HTML / hydration 樣本
- fixture 檔名需能看出情境，例如 `available_*`、`sold_out_*`、`target_missing_*`
- 若 fixture 需要額外斷言資料，可搭配同名 `.json` 或 `.yaml` 期望值檔
- fixture 需先去除不必要或敏感 query，再納入版本控制

### 9.4 測試邊界原則

- parser 測試直接驗證 site adapter 契約，不透過 web UI
- domain / notification rule 測試不得依賴資料庫或網路
- integration test 可碰 SQLite，但不直接對外打 `ikyu`
- browser fallback 不列入 V1 自動測試主路徑

## 10. 參考方向

本架構規劃參考以下方向，最終結論為綜合推論：

- FastAPI 官方的多檔案應用拆分與 `APIRouter`
- FastAPI 官方的 `lifespan` 啟停模型
- Python 官方 `asyncio` 對 IO-bound 與 task/queue 的定位
- Python 官方 `abc` 對抽象介面的支持
- SQLAlchemy 官方對短生命週期 `Session` 與 transaction 邊界的建議
- Pydantic Settings 官方對型別化設定模型的做法

這些資料支持的結論是：

- 本機 web UI 與背景引擎應同 process、不同層
- 長時間監看應由 app-level runtime 管理
- site adapter 應用抽象介面隔離站點差異
- config、domain、infrastructure 應分層，避免未來擴站時耦合惡化
