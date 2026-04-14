# V1 Spec

本文件描述 V1 要做什麼，不描述實作細節。

## 0. 目前實作現況

目前已可實際操作：

- 專用 Chrome profile + CDP attach
- 從專用 Chrome 分頁建立 watch
- 顯示飯店、房型、價格與每人每晚衍生值
- watch 列表、刪除、通知規則設定
- watch 的啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- 全域通知通道設定與測試通知
- debug captures、watch 詳細頁、歷史與 runtime 訊號摘要
- background runtime 已接線並能實際寫入歷史與發送通知

目前仍待收斂：

- background runtime 的長時間穩定性驗證
- 結構整理，例如 `main.py`、`web/views.py`、`ChromeCdpHtmlFetcher`

## 1. 目標

建立一個可在 Windows 背景運作的 `ikyu` 價格監看器。

V1 只追求：

- 精確監看指定 `room-plan`
- 由專用 Chrome 穩定刷新並重新解析價格
- 有歷史、有通知、有本機管理介面

## 2. 範圍與非目標

### 2.1 V1 範圍

- 只支援 `ikyu`
- 只支援精確 `room-plan` 監看
- 正式建立入口為「從目前專用 Chrome 頁面抓取」
- 以 Chrome-driven monitor 為正式主線
- 支援本機 GUI、歷史、debug 與通知

### 2.2 非目標

- 不做自動訂房
- 不做自動登入
- 不做整館最低價追蹤
- 不做多站平台化框架
- 不做雲端同步與多人後台

## 3. 核心使用流程

1. 使用者啟動專用 Chrome profile。
2. 在專用 Chrome 中打開 `ikyu` 飯店頁或方案頁。
3. GUI 列出目前可附著的 `ikyu` 分頁。
4. 使用者選擇分頁，系統建立 preview。
5. 使用者確認候選方案、通知規則與輪詢秒數。
6. 系統建立 watch item。
7. background runtime 定期刷新對應頁面並重新解析價格。
8. 價格變化或狀態變化時發出通知。

## 4. 核心資料模型

### 4.1 三層表示

V1 需明確區分：

- `seed_url`
  - 原始輸入或目前頁面 URL
- `search_draft`
  - 可解析的查詢條件
- `watch_target`
  - 可正式排程監看的精確目標

只有 `watch_target` 可以進入 background runtime。

### 4.2 Watch Target identity

正式 identity 至少包含：

- `hotel_id`
- `room_id`
- `plan_id`
- `check_in_date`
- `check_out_date`
- `people_count`
- `room_count`

`currency` 不納入 identity，而屬於每次 snapshot。

### 4.3 Watch Item

`watch_item` 只表示使用者設定，不混入 runtime 狀態。

至少包含：

- 站點與 canonical target
- 飯店、房型、方案名稱
- 日期、人數、房數
- 輪詢秒數
- 通知規則
- `enabled`
- `paused_reason`
- `created_at`
- `updated_at`

### 4.4 Runtime 狀態與歷史

需分開保存：

- `latest_check_snapshot`
- `check_events`
- `price_history`
- `notification_states`
- `notification_throttle_states`
- `debug_artifacts`

## 5. 價格與 availability 語意

- `normalized_price_amount` 一律表示該 `watch_target` 在當次條件下的總支付金額
- `currency` 與 `normalized_price_amount` 必須成對保存
- 每人每晚價格只是衍生展示值，不作為正式比價基準

V1 availability enum：

- `available`
- `sold_out`
- `unknown`
- `parse_error`
- `target_missing`

## 6. 監看與通知行為

### 6.1 監看事件

需支持的主要事件：

- `price_drop`
- `became_available`
- `parse_failed`

只記錄不一定通知：

- 價格不變
- 價格上升
- 手動立即檢查成功

### 6.2 通知規則

V1 UI 先只支援單一 leaf rule：

- `any_drop`
- `below_target_price`

`target_price` 僅在 `below_target_price` 下有意義。

### 6.3 通知去重

- 同一 `watch_target` 在相同價格與相同 availability 下不重複通知
- 價格先回升後再跌回同一門檻，可再次通知
- 通道級冷卻需持久化，重啟後不可重置

## 7. 解析與監看策略

V1 正式主線：

- 以專用 Chrome 分頁為資料來源
- 以 browser page preview 建立候選
- 以 browser page snapshot 執行 background monitor

不再把 `HTTP-first` 視為正式主線。

## 8. GUI、通知與儲存

### 8.1 GUI 範圍

V1 GUI 至少包含：

- watch 列表
- 建立 watch
- watch 詳細頁
- 通知規則設定
- 全域通知通道設定
- debug captures

### 8.2 通知通道

V1 至少支援：

- desktop notification
- `ntfy`
- Discord webhook

通知內容應由共用 formatter 統一產生，各通道只負責送出。

### 8.3 儲存原則

- watch 設定與 runtime state 分離
- 單次 check 的最新狀態、歷史、通知狀態與 debug 摘要需在單一 transaction 內持久化
- SQLite 需啟用 `WAL` 與 `busy_timeout`

### 8.4 Debug

V1 需保留兩種診斷資料：

- preview capture
- runtime `debug_artifact`

兩者用途需區分，不混成同一份資料。

## 9. 驗收與驗證

### 9.1 驗收條件

V1 驗收最低標準：

- 可從專用 Chrome 分頁建立 watch
- background runtime 可定期刷新頁面並寫入歷史
- 價格變化可觸發通知
- watch 可啟用、停用、暫停、恢復與手動立即檢查
- 發生 blocked page、節流、parse error 時，GUI 與歷史可看出狀態

### 9.2 測試原則

- parser / normalizer 必須可用 fixture 脫網重跑
- runtime 的高風險路徑必須有測試
- web 主要操作 route 必須有測試
- persistence 與 migration 必須有 integration test
