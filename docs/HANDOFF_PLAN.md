# Handoff Plan

本文件給新的對話窗快速接手使用，只回答四件事：

- 專案目前已可實際使用到哪裡
- 目前正式主線的行為是什麼
- 還有哪些風險尚未收斂
- 下一步應該先做什麼

若切換到新的對話窗，建議閱讀順序：

1. `docs/V1_SPEC.md`
2. `docs/ARCHITECTURE_PLAN.md`
3. `docs/TASK_BREAKDOWN.md`
4. `docs/HANDOFF_PLAN.md`

## 1. 目前可用能力

- `uv run python -m app.tools.dev_start`
  - 單一啟動命令
  - 會先檢查可附著的專用 Chrome，必要時先喚醒 profile，再啟動 GUI
- 專用 Chrome profile + CDP attach
- 從目前專用 Chrome 分頁選擇 `ikyu` 頁面建立 watch
- Chrome 分頁清單會在清單頁直接標示已建立的精確 watch
- watch 列表、刪除、啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- 手動控制與立即檢查已透過 watch lifecycle coordinator 收斂到單一入口
- 單一 watch 的通知規則設定
- 全域通知通道設定頁與測試通知
- 首頁與 watch 詳細頁的局部 polling 更新
- watch 詳細頁、歷史與 runtime 訊號摘要
- debug captures 列表 / 詳細頁 / 清空
- background runtime 已接線，能依排程刷新頁面、寫入歷史並發送通知
- GUI 目前狀態已統一透過正式 `WatchRuntimeState` 解讀
- blocked / paused / resumed / recovered transition 已寫入正式 `runtime_state_events`

## 2. 目前正式主線的行為

### 2.1 建立 watch

1. 專用 Chrome 開啟 `ikyu` 分頁
2. GUI 列出可附著分頁
3. 使用者選定分頁
4. adapter 從 browser page 建立 preview
5. 使用者確認候選與通知規則
6. 建立 `watch_item`

補充：

- 分頁清單的既有 watch 判斷不再由 `tab_id` 主導，而是以：
  - `watch target identity`
  - `browser_page_url`
  - query-aware matching
  為主
- `tab_id` 只保留成當次 session 的短期操作鍵

### 2.2 runtime 啟動與分頁恢復

- runtime 會在 app `lifespan` 啟動時接線
- 啟動後會低速恢復 `enabled` 且未 `paused` 的 watch 分頁
- 同一輪恢復內，已分配給前一個 watch 的分頁不會再被下一個 watch 重用
- 若之後輪詢時發現缺頁，仍會按需補建

### 2.3 背景檢查

- scheduler 只同步 `enabled` 且未 `paused` 的 watch
- 背景排程與 `check-now` 共用 per-watch 互斥
- in-flight check 在送通知與寫入結果前會重新確認控制狀態；若中途被 pause / disable，該次結果會被丟棄
- 單次 check 以單一 transaction 寫入：
  - `latest_check_snapshots`
  - `check_events`
  - `price_history`
  - `notification_states`
  - `runtime_state_events`
  - `debug_artifacts`
- SQLite 已啟用：
  - `WAL`
  - `busy_timeout`
  - 歷史查詢 index

### 2.4 通知與事件判定

- notifier 通道目前有：
  - desktop
  - `ntfy`
  - Discord webhook
- dispatcher 在設定不變時會重用，不會每次重新建立
- 通道節流狀態已持久化，可跨 runtime 重啟保留
- 外部 HTTP notifier 已補顯式 timeout
- 全域通知設定已補 server-side URL 驗證，只接受合法 `http/https`

### 2.5 watch 狀態語意

- `watch_item.enabled` 與 `paused_reason` 不再由各頁面自行拼湊解讀
- GUI 與操作按鈕統一透過 `WatchRuntimeState` 判斷
- `runtime_state_events` 會正式記錄 blocked / paused / resumed / recovered 等 transition
- 目前正式狀態至少包含：
  - `ACTIVE`
  - `BACKOFF_ACTIVE`
  - `DEGRADED_ACTIVE`
  - `RECOVER_PENDING`
  - `MANUALLY_PAUSED`
  - `MANUALLY_DISABLED`
  - `PAUSED_BLOCKED_403`
  - `PAUSED_OTHER`
- `RECOVER_PENDING` 目前表示：
  - watch 已恢復執行
  - 但最近一次錯誤仍是 `http_403`
  - 尚未有新的成功檢查證明它真的恢復正常

`恢復可訂` 的正式規則目前是：

- 會往前回溯最近一次明確的 availability
- 忽略中間的：
  - `unknown`
  - `parse_error`
  - `target_missing`
- 只有 **`sold_out -> available`** 才算 `became_available`

這一點已修正，避免把中間的 network error / unknown 誤判成「恢復可訂」。

## 3. 已驗證過的高風險路徑

以下路徑已有測試覆蓋，不再是主 blocker：

- 同一 watch 的執行互斥
- 單次 check 的 transaction 一致性
- SQLite 的 `WAL` / `busy_timeout` / history index
- 鏈式 migration
- 通知節流狀態持久化
- dispatcher 在設定未變時重用
- notifier HTTP timeout
- `WatchItem` 的非法 `enabled/paused_reason` 組合已被拒絕
- blocked / paused / resumed / recovered transition 已有正式事件模型與持久化
- state-changing POST 的本機 `Origin/Referer` 驗證
- 通知通道冷卻跨 runtime 重啟保留
- 單一通知通道失敗不會中止整次 check
- 連續 timeout 會遞增 backoff
- backoff 後成功檢查會清掉 failure 狀態
- 睡眠恢復後補掃會尊重 backoff 視窗
- 403 暫停後手動恢復，成功檢查會清掉錯誤狀態
- 啟動恢復時多個 watch 不會共用同一個分頁依序跳轉
- 手動控制與 `check-now` 已走 lifecycle coordinator
- in-flight check 中途被 pause / disable 時不會繼續寫入新結果或發通知
- preview cooldown 已改成 site-scoped，未來新增第二站時不會因單站被阻擋而冷卻所有站點 preview
- preview debug capture 已補 `site_name` metadata 與 site filter，reader 不再只能辨識 `ikyu_preview_*`
- `ikyu` browser page matching 已集中到 `sites/ikyu/browser_matching.py`
- watch target identity 已改為具名 `WatchTargetIdentity` value object

## 4. 目前主要風險

### 4.1 runtime 已可用，但仍缺長時間穩定性驗證

目前仍需補強：

- 更完整的多 tick / 長時間 / 重試路徑驗證
- 長時間 blocked page / recover 的歷史與狀態呈現檢查
- 長時間背景運作下，首頁與詳細頁的 runtime 摘要是否仍準確

### 4.2 第二站前仍需收斂 site-boundary

目前 `ikyu` 專屬邏輯仍存在於部分 generic 層：

- web 層 existing-watch match helper

補充：

- preview cooldown 已先改成 site-scoped
- preview debug capture reader 已支援 site filter，但 browser strategy 仍需在第二站前收斂
- browser page matching 規則已集中到站點模組，但 `ChromeCdpHtmlFetcher` 仍以 `ikyu` 為單站假設

第二站前應先把這些行為移往 site capability / browser strategy，而不是直接拆 `main.py` 或 `views.py`。

### 4.3 `main.py` 與 `web/views.py` 偏大

- `main.py` 目前混合 route、來源驗證與部分 web orchestration
- `web/views.py` 目前承載過多 HTML 組裝責任

這不是第一層正確性風險，但已值得安排拆分。

### 4.4 `ChromeCdpHtmlFetcher` 偏大

目前它同時處理：

- Chrome attach
- 分頁列舉
- 分頁比對
- capture 與節流訊號
- profile 啟動 / 附著輔助

功能上已可用，但後續再擴容易變成大型維護點。

### 4.5 state ownership 仍需持續守住

目前 `watch_item`、`latest_check_snapshot`、`notification_state`、`debug_artifacts` 已分離，但仍需注意：

- 不要把 runtime 欄位重新塞回 `watch_item`
- 不要讓通知狀態、最新狀態、debug 摘要彼此重疊
- 若之後補更完整的 blocked / recover transition history，應優先擴充事件模型，而不是再增加零散旗標

### 4.6 schema 版本已升到 6

目前 schema 已包含：

- `notification_throttle_states`
- `runtime_state_events`

若接手時看到舊資料庫，需注意初始化流程會執行：

- `5 -> 6` migration
- 舊版 `enabled/paused_reason` 正規化

## 5. 下一步建議順序

### Step 1: 補長時間運作、節流與重試驗證

建議先補：

- 多 tick、跨 sleep / resume、backoff 期間的 runtime 測試
- 長時間 blocked page / recover 的歷史與狀態驗證
- runtime 狀態摘要與 watch 詳細頁是否能準確反映問題

建議切入：

- `src/app/monitor/runtime.py`
- `tests/unit/test_monitor_runtime.py`
- `src/app/web/views.py`
- `tests/unit/test_web_app.py`

### Step 2: 拆 `main.py`

建議方向：

- 拆成數個 router 模組
- 保留 `main.py` 只做 app 建立、lifespan、router 掛載
- browser matching 與 target identity 已先收斂，可避免拆 router 時混入站點比對規則重構

建議切入：

- `src/app/main.py`
- `src/app/web/`

### Step 3: 拆 `web/views.py`

建議方向：

- 依頁面類型拆分 render helper
- 先拆 watch list / watch detail / settings / debug pages

建議切入：

- `src/app/web/views.py`

### Step 4: 收斂 `ChromeCdpHtmlFetcher`

建議方向：

- 將 profile / attach / tab matching / capture 訊號分成較清楚的小模組
- 保留目前已驗證過的 query-aware matching 與最低分門檻

建議切入：

- `src/app/infrastructure/browser/chrome_cdp_fetcher.py`

### Step 5: 整理 state ownership

建議方向：

- 再確認 `watch_item`、`latest_check_snapshot`、`notification_state`、`debug_artifact` 的責任邊界
- 避免之後新功能直接跨層疊加欄位

## 6. 交接注意事項

- V1 正式主線是 Chrome-driven，不再把 `HTTP-first` 當成正式路徑
- 建立 watch 的正式入口是「從目前專用 Chrome 頁面抓取」
- `TASK_BREAKDOWN.md` 只維持精簡進度，不再塞過細背景
- 若下一個對話要再做 review，先以目前文件為準，不要把舊 review 全部當成仍未處理
