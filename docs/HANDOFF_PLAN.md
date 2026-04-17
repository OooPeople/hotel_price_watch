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
- `pytest` 通過，`222 passed`

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
- `watch_control_states` 目前只做 future migration plan，不實作 migration；後續若控制欄位增加，應把 control state 從 `watch_item` 拆出

### 3.2 Control Command Policy

- `pause` / `disable` 阻止新任務
- in-flight check 不硬取消，正式 policy 是 `continue-and-gate`
- in-flight check 透過 `TaskLifecyclePolicy` / `TaskLifecycleDisposition` 在 checkpoint 重讀 control state
- runtime checkpoint 目前包含 `AFTER_CAPTURE`、`BEFORE_NOTIFICATION_DISPATCH`、`BEFORE_PERSIST_RESULT`
- 若中途被 pause / disable，本次結果丟棄
- 若已進入 DB transaction，允許安全收尾
- 使用者在 `pause` / `disable` 後可以關閉對應 Chrome 分頁
- 若剛好有 in-flight check 正在抓該分頁，可能產生一次 bounded browser error，但不應造成崩潰、持續重試或 watch 永久壞掉
- `resume` / `enable` 後，runtime 必須能依保存的 watch identity、`browser_page_url` 與 canonical URL 重新找回或補開分頁

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
- notification dispatch 前與 persist 前已有 late gate，後段 pause / disable 仍能阻止提交
- 403 auto-pause 的 control state 與 check outcome 同 transaction
- auto-pause 後從 scheduler 移除 watch
- runtime 啟動時多 watch 不共用同一分頁
- 通知通道失敗不會中止整次 check
- 通知通道冷卻可跨 runtime 重啟保留
- timeout backoff 與成功後清除 failure state
- preview cooldown 與 debug capture 已具 site metadata / site filter
- state-changing POST 已有本機 `Origin/Referer` 驗證

## 5. 下一步：V1.5 多站地基

V1 功能層已可視為完成。下一階段不是立刻新增第二站，也不是先拆 `main.py`，而是先把不需要第二站樣本也能確定正確的地基收斂掉。

### Step 1: 建立 site descriptor / capability metadata（已完成第一輪）

已完成：

- 先只註冊 `ikyu`
- 補 `SiteDescriptor`，包含 display name、browser page label、browser tab hint 與 browser preview/runtime capability
- UI / preview flow 已開始吃 metadata，不再直接硬寫 `ikyu` 文案
- `PreviewAttemptGuard` 不再有預設 `site_name="ikyu"`，呼叫端需明確傳入
- Chrome 分頁選擇頁可顯示每個 tab 對應的站點 label

後續可再優化：

- Chrome tab preview service 的回傳模型仍可進一步帶 site descriptor，而不是只在 route 層補 label

### Step 2: browser page strategy 改為 per-site / per-request（已完成第一輪）

已完成：

- `ChromeCdpHtmlFetcher` 保留 generic CDP 能力
- `fetch_html` / `fetch_tab_capture` / `refresh_capture_for_url` / `ensure_tab_for_url` 可由呼叫端傳入 site strategy
- `SiteAdapter` 可提供 `browser_page_strategy`
- `ikyu` adapter 持有 `IkyuBrowserPageStrategy`
- `runtime` 由 watch target / adapter 決定 refresh / restore 使用的 strategy
- Chrome tab preview 由分頁 URL 對應 adapter，再使用該 adapter 的 strategy 抓取內容
- `LiveIkyuHtmlClient` 的 browser fallback 透過 strategy-bound wrapper 使用 `ikyu` strategy

後續可再優化：

- `ChromeCdpHtmlFetcher` 仍同時負責 profile 啟動、CDP attach、tab matching、capture 訊號；拆 `main.py` 後可再拆內部責任
- `build_default_browser_page_strategy()` 仍保留給 dev_start / chrome_profile 作為 V1 預設起始頁用途，不再代表 runtime 的全域唯一策略

### Step 3: lifecycle owner / control state 拆分決策（已完成第一輪）

已完成：

- `src/app/domain/watch_lifecycle_state_machine.py` 是 lifecycle transition 的正式決策中心
- `WatchLifecycleCoordinator` 已接管 enable / disable / pause / resume transition，不再轉呼叫 `WatchEditorService`
- `WatchEditorService` 已回到 watch 建立、刪除、通知規則更新與 preview 相關責任
- 已補 `WatchLifecycleCommand` / `WatchLifecycleDecision` / `WatchLifecycleTransitionResult` / `WatchLifecycleContext`
- state machine 明確輸出 watch 更新、runtime state event、scheduler side effect 與 in-flight policy
- check-now gate 由 coordinator 呼叫 state machine 判斷
- runtime auto-pause 已改由 `RuntimeControlRecommendation` 承載 state machine decision，runtime 不再直接拼接 paused watch
- runtime lifecycle events 已集中由 state machine 建立，`runtime.py` 不再保留獨立 event builder
- in-flight policy 維持不硬取消，依 `TaskLifecyclePolicy` / `TaskLifecycleDisposition` 丟棄後續結果；若使用者同時關閉 Chrome 分頁，當下 browser error 僅視為 bounded error

決策：

- 目前不新增 `watch_control_states` table；等第二站或更複雜控制需求明確後再 migration
- 目前不引入 in-flight hard cancel；避免取消 Chrome / DB / notifier 中間狀態造成更難推理的錯誤
- `resume` / `enable` 的恢復能力比硬取消更重要：runtime 需能重新找回或補開 watch 對應分頁

已切入：

- `src/app/application/watch_lifecycle.py`
- `src/app/application/watch_editor.py`
- `src/app/domain/watch_lifecycle_state_machine.py`
- `src/app/monitor/runtime.py`
- `src/app/monitor/policies.py`
- `tests/unit/test_watch_lifecycle_state_machine.py`
- `tests/unit/test_watch_lifecycle.py`
- `tests/unit/test_monitor_runtime.py`
- `tests/unit/test_web_app.py`

### Step 4: 再拆 `main.py`

建議方向：

- site-aware flow、per-site strategy、lifecycle owner 決策已完成第一輪，可以開始拆
- 第一刀已完成：request / form helper 已抽到 `src/app/web/request_helpers.py`
- 第二刀已完成：debug captures routes 已抽到 `src/app/web/routes/debug_routes.py`
- 第三刀已完成：settings / notification routes 已抽到 `src/app/web/routes/settings_routes.py`
- 第四刀已完成：watch list / detail / control routes 已抽到 `src/app/web/routes/watch_routes.py`
- 第五刀已完成：watch creation / Chrome tab preview routes 已抽到 `src/app/web/routes/watch_creation_routes.py`
- `main.py` 已收斂為 app 建立、lifespan、container 掛載、router include 與 health endpoint
- routes 拆到 `src/app/web/routes/`
- POST origin / referer 驗證保留共用 helper
- 下一步建議拆 `src/app/web/views.py`，依 watch list、watch detail、settings、debug pages 分檔

### 延後項目

- 不急著把 `WatchTarget` / `SearchDraft` 改成 `site_payload`
- 不急著把 `ChromeDrivenMonitorRuntime` 泛化成非 browser runtime
- 不急著新增 `watch_control_states` table；目前 lifecycle owner 與 control state 拆分先不做 migration
- `watch_control_states` 的 future migration plan 已寫在 `docs/ARCHITECTURE_PLAN.md`，不要在未 migration 前把更多 control 欄位塞進 `watch_item`
- 等第二站樣本明確後，再決定是否需要 capability payload 或 HTTP execution strategy

## 6. 不要重做的方向

- 不要回到 `HTTP-first` 主線
- 不要把 Seed URL 手動輸入流程加回 GUI
- 不要把站點規則塞回 `main.py` 或 `views.py`
- 不要在第二站尚未明確前大改 `WatchTarget` / `SearchDraft`
- 不要把 runtime 結果塞回 `watch_item`
- 不要移除舊 403 enum / state，因為舊 DB 可能仍有歷史資料

## 7. 仍需觀察

- 長時間背景運作、節流、discard、blocked page 的真機穩定性
- VPN / IP 風控下的使用者操作流程
- 第二站加入前，blocking outcome 是否需要更正式的 control recommendation
- `watch_item` 靜態定義與 control state 是否值得在後續 migration 中拆表
