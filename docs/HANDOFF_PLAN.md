# Handoff Plan

本文件給新對話窗快速接手。閱讀順序：

1. `docs/V1_SPEC.md`
2. `docs/ARCHITECTURE_PLAN.md`
3. `docs/TASK_BREAKDOWN.md`
4. `docs/HANDOFF_PLAN.md`

## 1. 目前狀態

專案目前已可實際使用：

- 單一啟動命令：`uv run python -m app.tools.dev_start`
- 專用 Chrome profile + CDP attach
- 從專用 Chrome 分頁建立 `ikyu` watch
- watch 列表、詳情、歷史、debug、通知設定
- watch 啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- 全域通知通道設定與測試通知
- background runtime 已能定期刷新、寫入歷史並發送通知
- 首頁與 watch 詳細頁已支援局部 polling 更新

最新驗證狀態：

- `ruff check src tests` 通過
- `pytest` 通過，`203 passed`

## 2. 正式主線

V1 正式主線是 Chrome-driven：

- 不再把 `HTTP-first` 當正式路徑
- 建立 watch 的正式入口是「從目前專用 Chrome 頁面抓取」
- background runtime 依附專用 Chrome session 刷新頁面並解析價格
- `tab_id` 只作為短期操作鍵，不作為 watch identity
- watch identity 以 target identity / `browser_page_url` / query-aware matching 判斷

## 3. 重要架構決策

### 3.1 Watch 與 Runtime State

- `watch_item` 保存使用者設定
- runtime 結果保存到 latest snapshot、check events、price history、notification state、runtime state events、debug artifacts
- GUI 狀態統一透過 `WatchRuntimeState` 解讀
- `RECOVER_PENDING` 表示控制狀態已恢復，但 latest snapshot 仍未有成功檢查證明站點已恢復

### 3.2 Control Command Policy

- `pause` / `disable` 阻止新任務
- in-flight check 不硬取消
- in-flight check 在通知與持久化前重讀 control state
- 若中途被 pause / disable，本次結果丟棄
- 若已進入 DB transaction，允許安全收尾

### 3.3 Blocking 語意

新程式碼使用 generic 語意：

- `BrowserBlockingOutcome`
- `pause_due_to_blocking`
- `paused_blocked`

舊語意保留相容：

- `http_403`
- `pause_due_to_http_403`
- `paused_blocked_403`

目前 `forbidden` 仍映射為 `http_403`，`rate_limited` 映射為 `http_429`。

### 3.4 Site Boundary

- 站點 adapter 與 browser strategy wiring 集中在 `src/app/bootstrap/site_wiring.py`
- `SiteAdapter` 已承擔 browser page capability
- `ChromeCdpHtmlFetcher` 透過 browser page strategy 處理 blocked / ready / scoring
- `ikyu` 站點規則應留在 `src/app/sites/ikyu`

## 4. 已處理的高風險路徑

以下已完成第一輪測試或實作收斂：

- 同一 watch 的 per-watch 互斥
- background assignment 與 `check-now` 共用同一 inflight task
- 單次 check 的 transaction 一致性
- in-flight check 中途被 pause / disable 時不寫入結果或發通知
- 403 auto-pause 的 control state 與 check outcome 同 transaction
- auto-pause 後從 scheduler 移除 watch
- runtime 啟動時多 watch 不共用同一分頁
- 通知通道失敗不會中止整次 check
- 通知通道冷卻可跨 runtime 重啟保留
- timeout backoff 與成功後清除 failure state
- preview cooldown 與 debug capture 已具 site metadata / site filter
- state-changing POST 已有本機 `Origin/Referer` 驗證

## 5. 下一步

### Step 1: 拆 `main.py`

先做純拆檔，不改行為。

建議方向：

- `main.py` 保留 app 建立、lifespan、container 掛載、router include
- routes 拆到 `src/app/web/routes/`
- POST origin / referer 驗證保留共用 helper
- 拆完立即跑 `ruff check src tests` 與 `pytest`

### Step 2: 拆 `web/views.py`

建議方向：

- 先拆 watch list / watch detail
- 再拆 notification settings / global settings / debug captures
- 保持 HTML 輸出不變，避免與 route 拆分混在一起

### Step 3: 收斂 `ChromeCdpHtmlFetcher`

建議方向：

- 拆 profile 啟動
- 拆 CDP attach
- 拆 tab matching
- 拆 capture / throttling / discard 訊號

## 6. 不要重做的方向

- 不要回到 `HTTP-first` 主線
- 不要把 Seed URL 手動輸入流程加回 GUI
- 不要把站點規則塞回 `main.py` 或 `views.py`
- 不要把 runtime 結果塞回 `watch_item`
- 不要移除舊 403 enum / state，因為舊 DB 可能仍有歷史資料

## 7. 仍需觀察

- 長時間背景運作、節流、discard、blocked page 的真機穩定性
- VPN / IP 風控下的使用者操作流程
- 第二站加入前，blocking outcome 是否需要更正式的 control recommendation
- `watch_item` 靜態定義與 control state 是否值得在後續 migration 中拆表
