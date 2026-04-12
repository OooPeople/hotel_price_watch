# V1 Spec

## 0. 目前實作現況註記

本文件描述 V1 目標行為與預期完成狀態。

截至目前為止，已落地且可實際操作的是：

- 專用 Chrome profile + CDP attach 的 GUI 建立 watch 流程
- watch 列表、刪除、通知規則設定、全域通知通道設定頁
- debug captures、歷史頁與 parser / persistence 基礎

尚未正式接線完成的是：

- background monitor runtime 的持續啟動
- scheduler / worker 與 notifier 的正式 app-level wiring
- 全域通知通道設定對實際通知發送的影響

交接與開發現況請一併參考：

- `docs/TASK_BREAKDOWN.md`
- `docs/HANDOFF_PLAN.md`

## 1. 目標

建立一個可在 Windows 背景執行的 `ikyu` 價格監看器。

V1 以「精確監看指定房型方案價格」為主，不追求一次解決所有網站互動情境。

## 2. 範圍與非目標

### 2.1 V1 範圍

- V1 僅支援 `ikyu`
- V1 僅支援精確 `room-plan` 監看
- V1 支援由一般飯店頁 URL 或固定方案 URL 建立監看項
- V1 已完成價格比對、歷史保存與通知模組，背景輪詢 runtime 仍待正式接線
- V1 GUI 以本機管理介面為主
- V1 目前依賴附著專用 Chrome profile，透過刷新目標頁面後再解析價格

### 2.2 非目標

- 不支援整間飯店最低價監看
- 不處理登入會員價
- 不做自動登入
- 不做自動訂房
- 不做雲端同步
- 不做多人共用後台

## 3. 核心使用流程

1. 使用者開啟專用 Chrome profile，並在其中進入 `ikyu` 飯店頁或方案頁。
2. 系統列出目前可附著的 `ikyu` Chrome 分頁。
3. 使用者選擇要建立 watch 的分頁。
4. 系統讀取該分頁目前內容，列出可監看的房型方案候選。
5. 使用者選定要追蹤的方案。
6. 系統建立 watch item。
7. 背景排程定期刷新對應頁面並重新解析價格。
8. 價格下降或狀態改變時發出通知。

### 3.1 混合建立流程

V1 採單一 editor，同時支援以下兩種入口：

- 入口 A：從專用 Chrome 目前已開啟的 `ikyu` 分頁中選擇一頁，系統直接讀取該頁面
- 入口 B：貼入已包含 `cid`、`rm`、`pln` 的精確 URL，系統以該 URL 作為初始入口或 debug 輔助

兩種入口最終都進入同一流程：

1. 建立或選取 `seed_url`
2. 建立 `search_draft`
3. 由專用 Chrome 讀取目前頁面內容並查詢候選項
4. 自動比對預填選項是否仍有效
5. 讓使用者確認或改選
6. 產生最終 `watch_target`

### 3.2 Watch Editor 欄位要求

watch editor 至少要有：

- 飯店 URL 或 Chrome 分頁入口
- 房型候選
- 方案候選
- 輪詢秒數
- 通知條件

如果 seed URL 已帶 `room_id` / `plan_id`，UI 需顯示：

- 目前為預填選項
- 是否仍有效
- 若失效，要求重新選擇

日期、人數、房數的調整在 V1 不由 API 表單直接控制，而由使用者在專用 Chrome 頁面中完成。
GUI 只負責顯示目前抓到的條件與候選結果。

## 4. 核心資料模型

### 4.1 三層表示模型

V1 需明確區分三種資料：

- `seed_url`
  - 使用者貼上的原始 URL
- `search_draft`
  - 目前 UI 中可編輯的查詢條件
- `watch_target`
  - 已解析完成、可正式排程監看的精確目標

只有 `watch_target` 可以進入背景監看。
`search_draft` 變更後，系統必須重新解析並重新產生 `watch_target`。

### 4.2 Watch Target identity

監看目標不能只存原始 URL，也要存拆解後條件：

- `hotel_id`
- `room_id`
- `plan_id`
- `check_in_date`
- `check_out_date`
- `people_count`
- `room_count`

避免因 query 順序或無關參數變動造成誤判。

`currency` 不納入 `watch_target` identity，而是在每次檢查快照中保存。
同一個房型方案即使因 locale 或顯示環境改變幣別，仍視為同一個監看目標。

`nights` 不作為 target identity 的正式欄位，而是由 `check_in_date` 與 `check_out_date` 推導，供 UI 顯示與使用者理解。

### 4.3 Watch Item 定義

`watch_item` 在 V1 中只表示「使用者設定的監看項」，不混入最新執行結果。

每個 watch item 至少要包含：

- `site`: `ikyu`
- `hotel_id`
- `hotel_name`
- `canonical_url`
- `room_id`
- `room_name`
- `plan_id`
- `plan_name`
- `check_in_date`
- `check_out_date`
- `nights`
- `people_count`
- `room_count`
- `target_price`
- `notification_rule`
- `scheduler_interval_seconds`
- `enabled`
- `paused_reason`
- `created_at`
- `updated_at`

資料保留規則：

- 一個 watch item 僅對應一個精確 `watch_target`
- 若使用者要追多個方案，應建立多個 watch items
- 價格歷史 V1 先完整保存
- retention 與清理策略列入後續版本

最新執行狀態與歷史需分開保存：

- `latest_check_snapshot`
  - 保存最新一次檢查摘要，例如最新價格、availability、最後檢查時間、backoff / degraded 狀態
- `check_events`
  - 保存每次檢查的整理後歷史事件，用於歷史頁與錯誤追蹤
- `notification_states`
  - 保存通知去重與上次通知基準
- `price_history`
  - 保存用於價格曲線的成功價格點

### 4.4 價格語意

- `normalized_price_amount` 一律表示該 `watch target` 在當次查詢條件下的總支付金額
- `currency` 與 `normalized_price_amount` 必須成對保存
- UI 以 `display_price_text` 為主要顯示值
- UI 可依 `normalized_price_amount`、`nights`、`people_count` 推算並顯示「每人每晚」價格
- 「每人每晚」屬於衍生展示值，不作為通知判定與歷史比價的正式基準

### 4.5 Availability 狀態

V1 合法 availability enum：

- `available`
- `sold_out`
- `unknown`
- `parse_error`
- `target_missing`

## 5. 監看與通知行為

### 5.1 監看事件

需要通知：

- `price_drop`
- `became_available`
- `parse_failed`

可只記錄不通知：

- 價格不變
- 價格變貴
- 手動立即檢查成功

### 5.2 通知條件模型

V1 的通知規則架構需預留可擴充空間，但第一版 UI 先只提供單一規則。

- domain / storage 層允許未來擴充為複合規則
- V1 UI 先只支援單一 leaf rule
- V1 先提供：
  - `any_drop`
  - `below_target_price`
- 後續若擴充複合規則，可在不改 `watch_target` 模型的前提下加入 `AND` / `OR`

`target_price` 僅在 `below_target_price` 條件下有意義。

### 5.3 通知去重規則

- 同一 `watch target` 在相同價格與相同 availability 下不重複通知
- 若價格先回升後再下降到相同門檻，應再次通知
- 若無房與可訂狀態反覆切換，狀態再次轉為可訂時應再次通知
- `below_target_price` 僅在 `price < target_price` 時可觸發通知
- `below_target_price` 若仍低於門檻，但價格相較上次已通知的低價結果發生變化，應再次通知
- `below_target_price` 若價格仍低於門檻且與上次已通知價格相同，不重複通知

### 5.4 選項失效處理

- 若使用者變更日期、人數、房數後，原 `room-plan` 失效
- 系統不得自動猜測替代選項
- 使用者必須重新確認有效候選項

## 6. 解析策略

### 6.1 優先順序

1. 以專用 Chrome 目前頁面為主，讀取已載入 DOM / hydration 資料
2. 先從 HTML 中的 SSR 可見價格區塊解析
3. 再從 Nuxt hydration / JSON-LD 資料解析 `hotel / room / plan / amount` 相關欄位
4. 若頁面仍不完整，提示使用者在專用 Chrome 中手動切到正確頁面後重新抓取

### 6.2 Canonicalization

- 所有監看條件都需 canonicalize
- 不以原始 URL 作為唯一識別
- canonicalization 結果需可穩定重建 `watch_target`

## 7. 排程與錯誤處理

- 每個 watch item 可設定輪詢秒數
- 預設輪詢間隔為 `600` 秒
- 預設 jitter 為 `±10%`
- 預設最大並行數為 `2` 到 `3`
- 背景輪詢目前以附著專用 Chrome 為主
- 到輪詢時間後，系統需主動刷新目標頁面，再重新解析價格
- timeout / parse failure / 站方阻擋頁 都需採 backoff 與自動重試
- 若偵測到阻擋頁或分頁可能節流，需在歷史與 debug 中留下訊號
- 若頁面刷新後仍被站方阻擋，暫停該 watch item，並在 UI 顯示需人工介入
- 不因單次錯誤立即停用 watch item
- `parse_failed` 單次失敗只記錄；連續 `3` 次後標記為 degraded 並通知一次
- 電腦從睡眠恢復後應盡快補掃一次
- 背景輪詢依賴專用 Chrome session，需能辨識目標分頁是否可能因背景化而節流
- V1 採單實例執行，避免同時有多份 scheduler
- 單實例判定需同時使用固定 port、lock file 與 PID 驗證
- 若 lock file 存在但 PID 已不存在，視為 stale lock，啟動時自動清理
- 若 port 已被非本 app 程序占用，應顯示明確錯誤，不強行啟動

## 8. GUI、通知與儲存

### 8.1 GUI 範圍

V1 GUI 至少包含：

- 新增 watch item
- watch item 列表
- 啟用 / 暫停
- 手動立即檢查
- 顯示最近價格與上次檢查時間
- 顯示最近錯誤摘要
- 通知設定
- watch editor 的 URL 預填與重新查詢能力
- 已選房型方案失效時的明確提示
- 歷史頁

歷史頁 V1 先以表格呈現，圖表列入後續版本。
歷史頁需包含成功檢查、失敗檢查、availability 變化與通知結果，不只顯示成功價格曲線。

### 8.2 通知設定

V1 支援：

- 本機桌面通知
- `ntfy`
- Discord webhook

所有遠端通知均為 opt-in。
通知通道設定屬於全域設定，放在主頁層級管理，不與單一 watch 綁定。

### 8.3 儲存設計

設定資料：

- 使用者通知設定
- 預設輪詢間隔
- GUI 狀態

執行資料：

- watch item
- 最近檢查結果
- 檢查歷史
- 價格歷史
- 通知結果歷史

### 8.4 Debug 快照

- 解析失敗時保存 debug 快照
- debug 快照至少包含時間、URL、HTTP 狀態與原始 HTML / hydration 摘要
- 每個 watch item 僅保留最近 `20` 筆 debug 快照

## 9. 驗收與驗證

### 9.1 驗收條件

- 可建立精確 room-plan 監看項
- 可由一般飯店 URL 建立監看項
- 可由固定方案 URL 預填後建立監看項
- 使用者改變日期或房型後可在 UI 內重新解析，不必重新貼 URL
- 正式接上 background runtime 後，可在背景穩定輪詢
- 價格下降時通知一次，避免重複洗版
- 重新啟動後可保留 watch item 與歷史資料
- parser 對 fixture 測試可穩定通過
- 專用 Chrome 縮小至工作列時，系統仍能刷新頁面並明確記錄是否出現背景節流訊號

### 9.2 測試原則

- V1 測試框架以 `pytest` 為準
- parser 測試必須可完全脫離網路，只依賴 `fixtures/` 內的固定樣本
- 若 `ikyu` HTML 結構變動，先更新 fixture 與測試，再更新正式 parser
- parser fixture test 至少驗證：
  - `hotel_id`
  - `room_id`
  - `plan_id`
  - `availability`
  - `display_price_text`
  - `normalized_price_amount`
  - `currency`
- fixture 至少覆蓋以下情境：
  - 正常可訂
  - 無房
  - 目標 room-plan 消失
  - 價格格式變化
- `normalized_price_amount` 的測試必須以總支付金額為準，不得混入每人每晚的衍生展示值
- 任何會影響 canonicalization、通知判定、price normalization 的修改，都必須補對應測試
