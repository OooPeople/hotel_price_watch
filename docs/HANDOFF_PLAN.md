# Handoff Plan

本文件用於交接目前實作現況、review finding 與下一階段的建議順序。

若切換到新的對話窗，建議閱讀順序：

1. `docs/V1_SPEC.md`
2. `docs/ARCHITECTURE_PLAN.md`
3. `docs/TASK_BREAKDOWN.md`
4. `docs/HANDOFF_PLAN.md`

## 1. 目前可用的功能

目前已可實際操作：

- `uv run python -m app.tools.dev_start`
  - 單一啟動命令
  - 會先檢查可附著的專用 Chrome，必要時先喚醒 profile，再啟動 GUI
- 專用 Chrome profile + CDP attach
- 從專用 Chrome 分頁選擇 `ikyu` 頁面建立 watch
- 顯示飯店、房型、價格與每人每晚衍生值
- watch 列表、刪除、通知規則設定
- 全域通知通道設定頁
- 全域通知設定頁的測試通知按鈕
- debug captures 列表 / 詳細頁 / 清空
- watch 詳細頁、歷史與錯誤摘要

## 2. review 已確認的核心問題

### 2.1 最大問題：background runtime 已初步接線，但還沒完成穩定化

目前 monitor 模組已能透過 app 啟動流程帶起，但仍屬初步版本：

- `lifespan` 已會啟動 monitor runtime
- scheduler 已可實際執行單次 background check
- notifier / dispatcher 已可依全域設定參與通知發送

目前尚未正式完成：

- 單實例保護的 deeper 整合與既有實例導向體驗
- 更長期穩定的 Chrome 分頁識別策略
- 節流 / blocked page / tab discard 的完整 runtime 策略

換句話說，現在已不是只有 GUI / preview / CRUD，但仍不能把它視為最終穩定版背景輪詢。

### 2.2 `SiteAdapter` 契約已部分收斂，但 runtime 路徑仍未完全統一

目前已完成：

- `build_preview_from_browser_page()` 已進入正式 `SiteAdapter` 契約
- `ChromeTabPreviewService` 不再依賴 `hasattr()`
- `build_snapshot_from_browser_page()` 已進入正式 `SiteAdapter` 契約
- `fetch_target_snapshot()` 舊契約已移除，程式與測試改為單一路徑的 browser-page snapshot 介面

目前仍需完成：

- 避免 preview 與 runtime 後續再長出新特例

### 2.3 舊的 `HTTP-first` / form-based 假設仍殘留

文件已改成 Chrome-driven monitor 主線，但程式內還殘留：

- target -> URL -> HTML 的 snapshot 假設
- 舊的 target snapshot 仍偏向由 URL 重建，而不是正式 Chrome-driven runtime

目前已完成：

- `preview_from_form_inputs()` 已移除
- create flow 不再處理已從 UI 移除的日期 / 人數 / 房數欄位
- 建立 watch 會優先沿用目前 preview 來源，而不是再走舊的表單覆寫路徑
- 舊的 target -> URL -> HTML snapshot 契約已從 `SiteAdapter` 正式介面移除

這些都會擾亂後續維護。

### 2.4 全域通知設定已初步生效，但還需 runtime 驗證

目前已完成：

- GUI 頁面
- DB 儲存
- application service

目前尚未完成：

- 補更完整的 runtime 測試與可觀測性
- 驗證長時間運作下的節流、失敗與重試行為

## 3. 建議執行順序

### Step 1: 收斂 Chrome-driven runtime 穩定性

目前已完成：

- `lifespan` 已會啟動 monitor runtime
- `run_watch_check_once()` 已能刷新 Chrome 頁面、解析 snapshot、寫入歷史
- notifier / dispatcher 已能讀取全域設定參與發送
- `dev_start` 已初步接上 port + lock file 的單實例檢查
- Chrome 分頁選取已不再依賴 `context.pages` 的 index 順序，而改用 session 內較穩定的 page key
- `ikyu` 分頁比對已補強為 query-aware，會優先比對 `rm/pln/cid/ppc/rc` 等條件
- watch 建立後已會保存 `browser_tab_id` / `browser_page_url` 線索，runtime 輪詢時會優先沿用
- 首頁與 `/health` 已會顯示 runtime 狀態摘要，可直接看到 monitor 是否運行、註冊幾筆 watch、Chrome session 是否可附著
- 已補 runtime 啟停與 active watch 同步測試，確認只會註冊 enabled/unpaused watch，且停止後會清空 scheduler 狀態
- 已補多 watch 與 runtime 啟動後新增 watch 的 loop 測試，確認後續 tick 會持續同步並執行檢查
- blocked page / throttling / tab discard 已整理成 watch 詳細頁上方的 runtime 訊號摘要，不再只藏在 debug artifact 表格中
- `dev_start` 在沿用既有實例前，已會先探測 `/health`，避免把失效的舊執行個體誤判成可沿用
- `dev_start` 在沿用既有實例前，已會比對 lock file 與 `/health` 回報的 `instance_id`，避免誤連到另一個不一致的執行個體
- 已有最小單元測試驗證：
  - 單次 runtime check 會寫入 `latest_check_snapshots` / `check_events` / `price_history`
  - 命中通知規則時會經過 dispatcher 發送
  - `possible_throttling` 訊號會寫入 runtime `debug_artifacts`
  - `403/blocked page` 會暫停 watch 並寫入錯誤摘要
  - 前次失敗 / degraded 狀態會在下次成功時正確清零
  - `dev_start` 在既有實例、stale lock、正常啟動三種情境下的行為

下一步目標：

- 補單實例保護整合
- 補更完整的 background runtime 測試
- 將目前 draft 層級的 browser 線索策略收斂成更長期的正式模型
- o 已收斂 preview captures 與 runtime `debug_artifacts` 的分工

建議切入點：

- `src/app/bootstrap/container.py`
- `src/app/main.py`
- `src/app/monitor/`

### Step 2: 重整 `SiteAdapter` 正式契約

目標：

- 已完成 browser page preview 正式介面化
- 下一步要把 Chrome-driven snapshot 也變成正式介面

建議切入點：

- `src/app/sites/base.py`
- `src/app/sites/ikyu/adapter.py`
- `src/app/application/chrome_tab_preview.py`

### Step 3: 清除舊假設

目標：

- 已完成移除 `preview_from_form_inputs()`
- 已完成移除 create flow 裡已失效的表單覆寫路徑
- 決定 target snapshot 只保留 Chrome-driven 正式主線

建議切入點：

- `src/app/application/watch_editor.py`
- `src/app/main.py`

### Step 4: 補強 notifier runtime 驗證

目前已完成：

- 全域通知通道設定已可影響 runtime notifier 建立
- desktop / ntfy / Discord 已能由 runtime 決定是否發送
- 全域通知設定頁已可送出一則真正走 dispatcher / notifier 路徑的測試通知

下一步目標：

- 補長時間運作與失敗路徑驗證
- 補通知發送結果的歷史與可觀測性檢查

建議切入點：

- `src/app/bootstrap/container.py`
- `src/app/notifiers/`
- `src/app/monitor/`
- `src/app/application/app_settings.py`

### Step 5: 收斂背景節流與分頁識別策略

目標：

- 不再長期依賴 index 型 `tab_id`
- 明確處理背景分頁節流 / tab discard / blocked page
- 決定 preview captures 與 runtime `debug_artifacts` 的分工

建議切入點：

- `src/app/infrastructure/browser/chrome_cdp_fetcher.py`
- `src/app/application/chrome_tab_preview.py`
- `src/app/monitor/`
- `src/app/application/debug_captures.py`

## 4. 建議新增或修改的文件說明

若下一個對話要繼續做 runtime，建議同步維護：

- `docs/TASK_BREAKDOWN.md`
  - 將 Milestone 6.5 的完成狀態持續更新
- `docs/ARCHITECTURE_PLAN.md`
  - 若 `SiteAdapter` 契約有變，優先更新
- `docs/V1_SPEC.md`
  - 若背景輪詢正式接線完成，再把「目前實作現況註記」更新掉

## 5. 交接時的注意事項

- 目前 `uv run ruff check .` 仍會被 repo 內 `tickets_hunter/` 的既存 lint 問題干擾
- 驗證時建議只對本次修改檔案跑 `ruff`
- `uv` 偶爾會撞到本機 cache 權限問題；必要時需在既有批准的前綴下重跑
- 目前 schema 已升到 `4`
- 若讀到舊 DB，現有程式已支援 `2 -> 3 -> 4` 的最小 migration
