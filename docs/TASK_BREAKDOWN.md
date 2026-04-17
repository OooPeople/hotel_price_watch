# Task Breakdown

本文件只保留專案進度與下一步。規格看 `docs/V1_SPEC.md`，架構邊界看 `docs/ARCHITECTURE_PLAN.md`，交接看 `docs/HANDOFF_PLAN.md`。

## 目前總結

- o V1 正式主線已收斂為「附著專用 Chrome profile + CDP attach」
- o GUI、preview、watch CRUD、通知設定、debug captures、background runtime 已可實際操作
- o 拆 `main.py` / `web/views.py` 前的第一輪高風險收斂已完成
- 目前主線進入 V1.5 架構地基：先補 lifecycle late gate，再收斂多站前的 site / browser strategy 邊界，最後才拆 `main.py`

## Milestone 1: 專案初始化（已完成）

- o Python `3.12` + `uv` 工作流
- o 專案目錄、lint、test 骨架
- o `SiteAdapter` / registry / domain model 基礎

## Milestone 2: Parser Proof（已完成）

- o `ikyu` URL normalizer、fixture、parser tests
- o `seed_url -> search_draft -> watch_target`
- o 精確 `room-plan` 價格解析與 target identity
- o 每人每晚價格衍生顯示

## Milestone 3: Monitor Engine（已完成）

- o scheduler / queue / worker state
- o compare / notification evaluator / dedupe / backoff / wakeup rescan
- o monitor runtime 已透過 app `lifespan` 接到啟動流程
- o 背景排程與 `check-now` 已共用 per-watch 互斥

## Milestone 4: Persistence（已完成）

- o SQLite schema、migration、`WAL`、`busy_timeout`
- o watch 設定與 runtime state 分離
- o latest snapshot / check event / price history / notification state / runtime state event / debug artifact persistence
- o 單次 check 已改成單一 transaction 持久化

## Milestone 5: Notifications（已完成）

- o desktop / `ntfy` / Discord webhook notifier
- o formatter / dispatcher / throttle
- o 全域通知通道設定與測試通知已走正式 dispatcher / notifier 路徑
- o 通道冷卻可跨 runtime 重啟保留

## Milestone 6: GUI（已完成第一版）

- o watch 列表、新增、刪除、詳細頁、歷史與錯誤摘要
- o 從專用 Chrome 分頁抓取建立 watch，不再要求手動 Seed URL
- o 單一 watch 通知規則與全域通知通道設定頁
- o debug captures 列表、詳細頁、清空
- o watch 啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- o 首頁與 watch 詳細頁支援局部 polling 更新
- o Chrome 分頁清單已用 target identity / `browser_page_url` / query-aware matching 判斷既有 watch
- o runtime 啟動恢復時，多個 watch 不會共用同一分頁依序跳轉

## Milestone 6.5: Chrome-driven Runtime 收斂（第一輪完成）

- o V1 control command policy 已文件化：不硬取消 in-flight check，阻止新任務並在提交前 gate
- o `WatchLifecycleCoordinator` 已接上 pause / disable / resume / check-now
- o in-flight check 中途被 pause / disable 時，不寫入新結果或發通知
- o 403 auto-pause 的 control state 已納入 check outcome 同一個 SQLite transaction，且會同步從 scheduler 移除
- o `WatchRuntimeState` 與 `runtime_state_events` 已成為 GUI / runtime 的正式狀態語意
- o `RECOVER_PENDING`、`PAUSED_BLOCKED`、`pause_due_to_blocking` 已取代新的 403 中心顯示語意；舊 403 enum/state 僅保留歷史相容
- o `SiteAdapter` 已補 browser page capability，tab filtering / matching 已由 adapter / registry 驅動
- o `ChromeCdpHtmlFetcher` 已改用可注入 browser page strategy，blocked / ready / page scoring 不再硬寫在 fetcher 內
- o `ikyu` blocked page guard 已移到 `sites/ikyu`
- o `BrowserBlockingOutcome` 已取代錯誤訊息片段判斷，支援 `forbidden -> http_403` 與 `rate_limited -> http_429`
- o preview cooldown 與 debug capture 已補 site metadata / site filter
- o V1 站點 adapter 與 browser strategy wiring 已集中到 `bootstrap/site_wiring.py`

## Milestone 6.5 尚未完成但不阻擋 V1 使用

- 補更完整的長時間運作、節流與重試行為驗證
- 補 blocked / recover control recommendation 的更完整語意
- 規劃 `watch_item` 靜態定義與控制狀態的長期分離方式，先不急著做大 migration

## Milestone 6.6: V1.5 多站地基（進行中）

- o 補 lifecycle late gate：notification dispatch 前與 persist 前再次確認 control state，縮小 pause / disable race window
- o 建立 site descriptor / capability metadata：先只註冊 `ikyu`，但 UI / preview flow 不再直接硬寫站點文案與預設 site
- o `PreviewAttemptGuard` 已移除 `site_name="ikyu"` 預設值，呼叫端需明確提供 site scope
- o 調整 Chrome tab preview / runtime restore / capture，使 site metadata 與 browser strategy 跟著 adapter 走
- o 將 browser page strategy 改成 per-site / per-request：`ChromeCdpHtmlFetcher` 不再只有全域單一 `IkyuBrowserPageStrategy`
- 暫緩 `WatchTarget` / `SearchDraft` 的 `site_payload` 化，等第二站樣本明確後再決定
- 暫緩把 `ChromeDrivenMonitorRuntime` 泛化成非 browser runtime，等第二站確定需要 HTTP execution 再做

## Milestone 6.7: Lifecycle Owner / Control State 深化（拆 `main.py` 前決策）

- o 將 `WatchLifecycleCoordinator` 從 façade 演進成 lifecycle transition owner，人工 control transition 不再由 `WatchEditorService` 執行
- o 抽出 control command decision / transition result，明確描述 enable / disable / pause / resume / check-now 的允許條件與副作用
- o 抽出 runtime auto-pause control recommendation，讓 runtime 不再直接拼接暫停 watch state
- o 明確定義 in-flight task lifecycle：維持不硬取消、以 late gate 丟棄結果；目前不引入硬取消策略
- 評估是否新增 `watch_control_states` table；若沒有第二站或更複雜控制需求，先只完成設計，不做 migration
- o 已完成拆 `main.py` 前的 lifecycle/control 決策：不做 migration，先以 coordinator + recommendation 收斂控制權

## Milestone 7: Packaging（尚未開始）

- 建立 PyInstaller spec
- 建立 build 腳本
- 驗證無 Python 環境啟動

## 下一步

1. 開始拆 `main.py`：先拆 router / web orchestration，保留 app 建立、lifespan、container 掛載在 entrypoint
2. 拆 `web/views.py`：依 watch list、watch detail、settings、debug pages 拆 render helper
3. 進一步收斂 `ChromeCdpHtmlFetcher` 內部責任：profile 啟動、CDP attach、tab matching、capture 訊號分層

## 目前主要風險

- `ikyu` 真站仍可能對同一出口 IP 做風控
- 背景監看依賴專用 Chrome session，不依賴使用者目前前景分頁
- Chrome 縮小或背景運作時，仍需持續驗證節流 / discard / blocked page 行為
- 第二站前仍需檢查新站是否需要額外 `site_payload` 或非 Chrome-driven execution strategy
