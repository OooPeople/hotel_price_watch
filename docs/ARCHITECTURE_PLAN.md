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
- `PriceHistoryEntry`
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
- Chrome CDP attach / page refresh
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
- `build_preview_from_browser_page()`
- `build_snapshot_from_browser_page()`
- `resolve_watch_target()`

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
- 專用 Chrome 分頁刷新與節流訊號判定

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
- `build_preview_from_browser_page(...) -> tuple[SearchDraft, CandidateBundle]`
- `build_snapshot_from_browser_page(...) -> PriceSnapshot`
- `resolve_watch_target(draft: SearchDraft, selection: CandidateSelection) -> WatchTarget`

建議輸入 / 輸出形狀保持站點無關：

- 輸入只吃 `SearchDraft` / `WatchTarget` 與已附著中的 browser page 內容
- 輸出只回 `CandidateBundle` / `PriceSnapshot`
- 不讓 web UI 或 scheduler 直接依賴 `ikyu` HTML 細節

`PriceSnapshot` 建議最小欄位：

- `display_price_text`
- `normalized_price_amount`
- `currency`
- `availability`
- `source_kind`

`PriceSnapshot` 表示 site adapter 回傳的單次站點快照，不包含 `watch_item_id` 或 `captured_at`。
這些 runtime / persistence 欄位應由 monitor 層在寫入 `price_history` 時補成 `PriceHistoryEntry`。

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

1. UI 由使用者從專用 Chrome 分頁建立 watch item
2. watch item 存進 SQLite
3. scheduler 取出 enabled items
4. monitor 附著專用 Chrome，找到或重建對應目標分頁
5. monitor 主動刷新頁面
6. parser 解析刷新後的價格與可訂狀態
7. compare engine 對比舊狀態
8. rule evaluator 對 `PriceSnapshot` 與歷史狀態做通知判定
9. repository 寫入 `latest_check_snapshots`、`check_events` 與必要的 `price_history`
10. notifier 視事件決定是否通知

### 8.2 為什麼目前改採專用 Chrome 主線

- `ikyu` 真站目前對直接 HTTP 請求有明顯阻擋與風控
- 使用者以專用 Chrome profile 建立真人 session 後，preview 與候選解析已證明可行
- 目前最穩定的做法，是由 monitor 附著該 Chrome session、主動刷新目標頁面後再解析
- `HTTP-first` 仍保留為未來重新評估方向，但不再作為 V1 正式主路徑

### 8.3 Chrome-driven monitor 的風險與限制

- 背景或非焦點分頁可能被 Chrome 節流
- 若分頁被 tab discard、記憶體節省或站方重導，monitor 需能偵測並記錄
- 站方阻擋頁、節流訊號、刷新失敗，都應寫入 `check_events` / debug
- V1 需允許專用 Chrome 縮小至工作列，但不能假設所有背景頁行為都與前景相同

V1 的具體策略先定為：

- `timeout` / 一般刷新失敗：backoff
- `parse_failed` 連續 `3` 次：標記 `degraded`
- 站方阻擋頁：暫停該 watch item，提示人工介入
- 若偵測到 `visibilityState=hidden` 或 `hasFocus=false`，保留節流訊號供歷史與 debug 顯示
- 專用 Chrome 分頁由 monitor 主動刷新，不依賴使用者當前正在看的前景分頁

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
- 專用 Chrome attach / tab listing / page refresh 屬於 V1 自動測試的一部分

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

## 11. Review 後需先收斂的差距

以下差距已在整體性 review 中確認，需在 Milestone 7 前先收斂：

### 11.1 runtime 已初步接線，但仍需穩定化

- monitor scheduler / worker / compare / notify 模組已存在
- 已以 `lifespan` 將 app-level runtime 初步接上
- 已在 `dev_start` 初步接上 port + lock file 的單實例檢查
- Chrome 分頁選取已初步改成 session 內較穩定的 page key
- `ikyu` 分頁比對已先納入 `rm/pln/cid/ppc/rc` 等 query 訊號
- 建立 watch 後會將 `browser_tab_id` 與 `browser_page_url` 存回 draft，供 runtime 輪詢優先沿用
- 已補首頁與 `/health` 的 runtime 狀態摘要，讓 GUI 可直接觀測 monitor 是否在跑與 Chrome session 是否可附著
- 已補 runtime 啟停與 active watch 同步測試，確認 scheduler 只註冊 enabled/unpaused watch，且 runtime 停止後會清空 scheduler 狀態
- 已補多 watch 與 runtime 啟動後新增 watch 的 loop 測試，確認後續 tick 會重新同步 watch 並執行檢查
- 已將 blocked page / throttling / tab discard 整理成 watch 詳細頁可直接判讀的 runtime 訊號摘要
- 已深化 `dev_start` 的既有實例導向：沿用既有實例前會先探測 `/health`，並比對 lock file 與 `/health` 回報的 `instance_id`
- 目前仍需補單實例與既有實例導向體驗整合、背景穩定性驗證與更多 runtime 測試

### 11.2 `SiteAdapter` 契約需改成正式支援 Chrome-driven 主線

目前已完成：

- `SiteAdapter` 已明確定義 browser page preview 的正式介面
- `ChromeTabPreviewService` 不再依賴 `hasattr()` 或 ad-hoc 特例
- `SiteAdapter` 已初步定義 Chrome-driven snapshot 的正式介面

目前仍需收斂：

- 將 Chrome-driven runtime 路徑完整納入同一份正式契約

### 11.3 舊的 target -> URL -> HTML 假設需清除

目前文件已接受 Chrome-driven monitor 主線，但實作內仍殘留：

- target 組 URL 後抓 HTML 的 snapshot 路徑
- Chrome-driven runtime 以外的舊 snapshot 假設

目前已完成：

- form-based preview / create flow 的舊假設已移除

需收斂成：

- 單一路徑：attach Chrome -> 找或重建分頁 -> refresh -> parse
- 若未來重新引入 `HTTP-first`，需明確設計成獨立雙軌，而不是殘留在同一條主線中

### 11.4 全域通知通道設定已初步接到 runtime

目前已完成：

- 設定模型
- SQLite 儲存
- GUI 設定頁
- runtime 對 notifier / dispatcher 的初步接線
- 讓設定能影響 notifier 建立與實際發送
- 設定頁已有測試通知按鈕，會走與正式通知相同的 notifier / dispatcher 路徑
- 已有最小 runtime 測試驗證通知發送與 dispatch 結果寫入

目前尚缺：

- 更完整的 runtime 驗證與觀測
- 長時間執行下的失敗、節流與重試行為驗證

### 11.5 Chrome 背景節流風險仍只做被動偵測

目前已有：

- `possible_throttling` 訊號
- 初步 runtime 寫入 `debug_artifacts`
- preview captures 與 runtime `debug_artifacts` 已在 GUI 上明確分工：
  - preview captures 只用於建立 watch / parser / browser 預覽除錯
  - runtime `debug_artifacts` 只用於背景輪詢期間的節流、blocked page、tab discard 等訊號
- 已補最小的 runtime 失敗 / 恢復測試：
  - `403/blocked page` 會暫停 watch
  - 前次失敗與 degraded 狀態會在下次成功時重置
- Chrome 分頁選取不再依賴易變的 index 型 `tab_id`
- 已先降低同飯店多房型分頁時的抓錯風險

目前尚缺：

- background runtime 的策略反應
- 歷史與 UI 對節流 / tab discard / blocked page 的完整顯示
- 專用 profile 預設是否要關閉高效能 / 記憶體節省策略的正式決策
