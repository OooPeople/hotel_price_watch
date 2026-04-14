# Architecture Plan

本文件只描述三件事：

- 專案的分層方式
- Chrome-driven 主線下的核心資料流
- 目前仍需收斂的架構缺口

## 1. 設計方向

本專案目前採用：

- 專用 Chrome profile + CDP attach
- 以 browser page 為正式資料來源
- GUI、runtime、通知、儲存分層處理

不再把 `HTTP-first` 視為 V1 正式主線。

核心原則：

- 設定與 runtime state 分離
- 站點解析與監看核心分離
- runtime 與 GUI 使用同一份正式 `SiteAdapter` 契約
- watch 最新狀態、歷史、通知狀態、debug 摘要分離保存

## 2. 建議目錄

```text
hotel_price_watch/
├─ docs/
├─ fixtures/
├─ src/
│  └─ app/
│     ├─ bootstrap/
│     ├─ application/
│     ├─ config/
│     ├─ domain/
│     ├─ infrastructure/
│     ├─ monitor/
│     ├─ notifiers/
│     ├─ sites/
│     ├─ tools/
│     ├─ web/
│     └─ main.py
├─ tests/
└─ README.md
```

## 3. 分層與責任

### 3.1 `domain`

放純資料模型與核心規則，不依賴框架或外部 IO。

典型內容：

- `entities.py`
- `value_objects.py`
- `enums.py`
- `notification_rules.py`

### 3.2 `application`

放 use case 與 orchestration，不直接碰具體框架細節。

典型責任：

- 建立 watch
- 選擇 Chrome 分頁預覽
- 管理全域設定
- 讀取 debug captures

### 3.3 `config`

放全域設定模型與 validation。

### 3.4 `infrastructure`

包裝外部技術實作：

- SQLite
- Chrome CDP attach
- 桌面通知 / `ntfy` / Discord
- file lock

### 3.5 `sites`

放站點 adapter 與 parser。

V1 目前只有 `ikyu`，但核心仍以 adapter 契約隔離站點細節。

### 3.6 `monitor`

放背景檢查主線：

- scheduler
- runtime
- backoff
- sleep 恢復補掃
- 狀態比對
- 通知觸發

### 3.7 `notifiers`

放通知內容格式化、dispatcher、節流與各通道 sender。

### 3.8 `web`

放本機管理介面與頁面 render helper。

## 4. 持久化模型

持久化至少分成：

- `watch_items`
- `latest_check_snapshots`
- `check_events`
- `price_history`
- `notification_states`
- `notification_throttle_states`
- `debug_artifacts`
- `notification_channel_settings`

原則：

- `watch_items` 只放使用者設定與 `watch_target`
- `latest_check_snapshots` 放最新檢查摘要與 runtime 狀態
- `check_events` 放每次檢查的整理後歷史
- `price_history` 只放成功價格點
- `notification_states` / `notification_throttle_states` 分別管理通知去重與通道冷卻
- `debug_artifacts` 放 runtime 與 parser 的診斷訊號

## 5. `SiteAdapter` 契約

V1 正式主線下，`SiteAdapter` 只需要支援 browser-driven 路徑。

最小契約：

- `match_url(url: str) -> bool`
- `parse_seed_url(url: str) -> SearchDraft`
- `normalize_search_draft(draft: SearchDraft) -> SearchDraft`
- `fetch_candidates(draft: SearchDraft) -> CandidateBundle`
- `build_preview_from_browser_page(...) -> tuple[SearchDraft, CandidateBundle]`
- `build_snapshot_from_browser_page(...) -> PriceSnapshot`
- `resolve_watch_target(draft: SearchDraft, selection: CandidateSelection) -> WatchTarget`

原則：

- web 與 monitor 都只吃 adapter 輸出的站點無關模型
- 不讓 runtime 回頭依賴站點 HTML 細節
- 不再保留 `target -> URL -> HTML` 的正式雙軌

## 6. GUI 與 runtime 的邊界

### GUI 負責

- 列出可附著的 Chrome 分頁
- 建立 / 編輯 / 刪除 watch
- 顯示最近狀態、歷史與 debug 摘要
- 以輕量 polling 局部更新首頁與 watch 詳細頁
- 管理全域通知設定

### runtime 負責

- 定期刷新頁面
- 解析 snapshot
- 寫入最新狀態與歷史
- 觸發通知
- 管理 backoff、degraded、sleep 恢復補掃

### 不建議做法

- 讓 GUI 自己持有 parser 或 monitor 細節
- 讓 runtime 直接依賴 HTML 組裝或 web state
- 讓通知 sender 直接依賴 watch UI 欄位

## 7. 核心資料流

### 建立 watch

1. 專用 Chrome 開啟 `ikyu` 分頁
2. GUI 列出可附著分頁
3. 使用者選定分頁
4. adapter 從 browser page 建立 preview
5. 使用者確認候選與通知規則
6. 建立 `watch_item`
7. 若 target 已存在既有 watch，UI 在分頁清單或 preview 階段直接阻止重複建立

### 背景監看

1. runtime 依 scheduler 選出該跑的 watch
2. runtime 啟動時先低速恢復 enabled 且未 paused 的 watch 分頁，且同一輪恢復內不重用已分配給其他 watch 的 tab
3. 檢查時依 `browser_page_url`、target identity 與 query-aware matching 找回或補建分頁；`tab_id` 只作為當次 session 的操作鍵
4. 刷新頁面並建立 snapshot
5. 單一 transaction 寫入最新狀態、歷史、通知狀態與 debug 摘要
6. 依通知規則與通道設定發送通知

## 8. 測試策略

至少維持以下層次：

- parser / normalizer 單元測試
- runtime 單元測試
- SQLite integration test
- web route / 主要操作測試
- notifier transport 測試

原則：

- parser 先改 fixture 與測試，再改正式邏輯
- runtime 的高風險路徑必須有測試：
  - blocked page
  - throttling
  - sleep 恢復補掃
  - 同一 watch 互斥
  - transaction rollback

## 9. 目前仍需收斂的差距

### 9.1 runtime 已可用，但仍需長時間穩定性驗證

目前缺口：

- 多 tick / 長時間 / 重試路徑的更完整驗證
- 長時間 blocked page / recover 的狀態呈現檢查

目前已補：

- 通知通道冷卻跨 runtime 重啟保留
- 單一通知通道失敗不會中止整次 check
- 連續 timeout 會遞增 backoff，且 backoff 後成功會清掉 failure 狀態

### 9.2 `main.py` 與 `web/views.py` 偏大

目前功能可用，但應逐步拆分：

- `main.py` -> app 建立 + router 模組
- `web/views.py` -> 依頁面類型拆 render helper

### 9.3 `ChromeCdpHtmlFetcher` 偏大

應逐步把：

- profile 啟動
- attach
- tab matching
- capture 與訊號判定

拆成較清楚的責任區塊。

### 9.4 state ownership 仍需持續守住

後續若新增功能，需避免：

- 把 runtime 欄位塞回 `watch_item`
- 讓最新狀態、通知狀態、debug 摘要互相重疊
