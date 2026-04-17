# Architecture Plan

本文件描述目前採用的架構邊界與後續整理方向。進度細節請看 `docs/TASK_BREAKDOWN.md`，交接摘要請看 `docs/HANDOFF_PLAN.md`。

## 1. 設計方向

V1 正式主線是：

- 專用 Chrome profile + CDP attach
- 以 browser page 作為正式資料來源
- GUI、application、runtime、persistence、notification 分層處理
- 目前只支援 `ikyu`，但站點細節需留在 `sites/ikyu`

不再把 `HTTP-first` 視為 V1 正式路徑。

核心原則：

- 設定與 runtime state 分離
- 站點 parser / browser matching / blocking detection 與監看核心分離
- GUI 與 runtime 都透過 `SiteAdapter` 使用站點能力
- watch 最新狀態、歷史、通知狀態、debug 摘要分離保存
- GUI 與 runtime 對 watch 狀態的解讀透過 `WatchRuntimeState` 收斂

## 2. 目錄責任

```text
src/app/
├─ bootstrap/       # container 與 V1 site wiring
├─ application/     # use case / orchestration
├─ config/          # 全域設定模型與 validation
├─ domain/          # 純資料模型與核心規則
├─ infrastructure/  # SQLite、Chrome CDP、file lock 等外部技術
├─ monitor/         # scheduler、runtime、backoff、狀態與通知觸發
├─ notifiers/       # formatter、dispatcher、throttle、通道 sender
├─ sites/           # 站點 adapter、parser、browser matching / strategy
├─ tools/           # dev_start、chrome_profile 等本機工具
├─ web/             # 本機 GUI render helper
└─ main.py          # 目前仍承載 routes，等 V1.5 site-aware flow 落地後再拆
```

## 3. 主要資料模型

正式流程需區分：

- `SearchDraft`：由目前頁面 URL 解析出的建立草稿
- `WatchTarget`：可正式監看的精確目標 identity
- `WatchItem`：使用者設定，不混入 runtime 結果
- `LatestCheckSnapshot`：列表與狀態判斷用的最新摘要
- `CheckEvent`：每次檢查歷史
- `PriceHistoryEntry`：成功價格點
- `NotificationState` / `NotificationThrottleState`：通知去重與通道冷卻
- `RuntimeStateEvent`：blocked / paused / resumed / recovered 等狀態轉移
- `DebugArtifact`：runtime 或 parser 診斷資料

`watch_item.enabled` 與 `watch_item.paused_reason` 目前仍是 control state 的最小欄位。後續若要更完整分離 control state，需做正式 migration，不應臨時增加零散欄位。

### 3.1 `watch_control_states` Future Migration Plan

目前不立即實作 `watch_control_states` migration，但先固定長期方向，避免後續新增控制欄位時繼續塞進 `watch_item`。

未來拆分目標：

- `watch_items`：只保存 watch 靜態定義，例如 target、hotel / room / plan 顯示資訊、canonical URL、notification rule、scheduler interval
- `watch_control_states`：保存 control plane 狀態，例如 `watch_item_id`、`enabled`、`paused_reason`、`updated_at`、可選的 `version`
- lifecycle state machine 未來輸出 control state transition，而不是直接回傳修改後的 `WatchItem`
- repository 提供 GUI / runtime 需要的 read model，避免 route 或 runtime 自行拼 join
- scheduler sync、check-now gate、pause / disable / resume 都只依 control state 判斷

暫緩原因：

- 目前只有單站，control state 仍只有 `enabled` / `paused_reason`
- 立即 migration 會同時影響 SQLite schema、repository、GUI list、runtime scheduler sync、integration tests
- 目前較重要的是先守住 state ownership：不要新增更多 control 欄位到 `watch_item`

觸發條件：

- 第二站需要更多 control state
- 出現 per-site control policy
- 需要 user-visible pause reason history 或 control state versioning
- `enabled` / `paused_reason` 以外的控制欄位開始增加

## 4. Site Boundary

`SiteAdapter` 是 GUI / runtime 使用站點能力的正式邊界。V1.5 的目標是先讓現有單站流程 site-aware，而不是立刻平台化多站。

目前最小能力：

- `match_url`
- `parse_seed_url`
- `normalize_search_draft`
- `fetch_candidates`
- `build_preview_from_browser_page`
- `build_snapshot_from_browser_page`
- `resolve_watch_target`
- `is_browser_page_url`
- `browser_tab_matches_watch`

V1.5 已補第一輪 `SiteDescriptor` metadata / capability：

- `display_name`
- `browser_page_label`
- browser page 操作提示
- 是否支援 browser preview
- 是否支援 browser runtime snapshot

仍待收斂：

- Chrome tab preview service 的回傳模型可再直接攜帶 site descriptor

站點 browser 行為透過 browser page strategy 注入 `ChromeCdpHtmlFetcher`，目前包含：

- blocked page detection
- ready page detection
- page scoring
- page signature
- confident page matching

目前 browser page strategy 已完成第一輪 per-site / per-request 化：`SiteAdapter` 可提供 strategy，preview、runtime capture、runtime tab restore 會依 adapter 傳入 `ChromeCdpHtmlFetcher`。`ChromeCdpHtmlFetcher` 自身仍保留 generic 預設 strategy，供無站點 context 的低階操作兜底。

V1 的站點 adapter 與 browser strategy wiring 集中在 `src/app/bootstrap/site_wiring.py`。新增第二站時，優先擴充這裡與 `sites/<site>`，不要直接把站點規則塞進 `main.py`、`views.py` 或 `ChromeCdpHtmlFetcher`。

## 5. Browser-Driven 資料流

### 建立 watch

1. 使用者以 `uv run python -m app.tools.dev_start` 啟動 GUI 與專用 Chrome
2. 使用者在專用 Chrome 開啟 `ikyu` 頁面
3. GUI 列出可附著分頁
4. 使用者選分頁
5. adapter 從 browser page 建立 preview
6. 使用者確認候選、通知規則、輪詢秒數
7. 系統建立 `watch_item` 與 draft

### 背景監看

1. runtime 啟動時低速恢復 enabled 且未 paused 的 watch 分頁
2. scheduler 取出到期 watch
3. runtime 依 `browser_page_url`、target identity、query-aware matching 找回或補建分頁
4. Chrome 刷新頁面並擷取 HTML
5. adapter 建立 `PriceSnapshot`
6. compare / notification engine 判斷事件與通知
7. repository 以單一 transaction 寫入最新摘要、歷史、通知狀態、runtime event、debug artifact

`tab_id` 只作為當次 Chrome session 的短期操作鍵，不作為 watch identity。

## 6. Control Command Policy

V1 採保守策略：

- `pause` / `disable` 立即阻止新的 scheduler dispatch 與 `check-now`
- 已 in-flight 的 check 不硬取消，避免中斷 browser / parser / notifier 的不可預期區段
- in-flight check 在通知與持久化前重新讀 control state；若 watch 已 pause / disable，該次結果直接丟棄
- 若 check 已進入單一 DB transaction，允許安全收尾，避免半套寫入
- `resume` / `enable` 只解除 control gate，不代表已成功恢復；若 latest snapshot 仍是 blocked error，current state 仍會是 `RECOVER_PENDING`

### 6.1 分頁關閉與 In-flight Check

`pause` / `disable` 的產品語意是「立即停止後續監看意圖」，不是「強制殺掉已進入外部系統的同步操作」。

使用者在按下 `pause` / `disable` 後，可以關閉對應 Chrome 分頁。若當下剛好有 in-flight check 正在透過 Chrome / CDP 抓取該分頁，該次檢查可能產生一次臨時 browser error，例如 tab closed、frame detached 或 network error。這類錯誤應被視為 bounded error：

- 不應造成程式崩潰
- 不應造成 watch 永久壞掉
- 不應造成 paused / disabled watch 持續重試
- 不應阻止之後 `resume` / `enable` 重新找回或補開分頁

因此 V1 的正式 task lifecycle policy 是 `continue-and-gate`：

- control command 立即更新 control state 並移除 scheduler active set
- in-flight check 不硬取消
- 每個不可逆外部 side effect 前由 `TaskLifecyclePolicy` 評估 `TaskLifecycleDisposition`
- runtime 目前在 `AFTER_CAPTURE`、`BEFORE_NOTIFICATION_DISPATCH`、`BEFORE_PERSIST_RESULT` 三個 checkpoint 套用 disposition
- 若中途已 pause / disable，後續通知與持久化結果丟棄
- 若 notifier 已經送出或 DB transaction 已經開始，不嘗試回滾
- `resume` / `enable` 後，runtime 需依保存的 watch identity、`browser_page_url` 與 canonical URL 找回或補開分頁

這個策略刻意避免 hard cancel，因為目前 Chrome 操作、notifier dispatch 與 SQLite 寫入可能透過同步外部操作執行，強制中斷反而會讓 side effect 邊界更難推理。

## 7. Blocking 與 Runtime State

目前新語意採 generic 命名：

- browser blocking 以 `BrowserBlockingOutcome` 表示
- blocked pause event 寫入 `pause_due_to_blocking`
- blocked pause current state 使用 `paused_blocked`

歷史相容保留：

- `pause_due_to_http_403`
- `paused_blocked_403`
- `http_403`

目前 `forbidden` blocking outcome 仍映射到 `http_403`，`rate_limited` 映射到 `http_429`。後續若新增 challenge / login wall / captcha，應擴充 outcome 與 control recommendation，而不是再新增訊息片段判斷。

## 8. 測試策略

至少維持：

- parser / normalizer 單元測試
- runtime 單元測試
- SQLite integration test
- web route / 主要操作測試
- notifier transport 測試

高風險路徑需有測試：

- blocked page
- throttling / discard 訊號
- sleep 恢復補掃
- 同一 watch 互斥
- transaction 一致性
- control state gate

## 9. 目前架構缺口

### 9.1 Lifecycle Owner 已完成第一輪收斂

目前 control command policy 已明確，且 runtime 已在 notification dispatch 前與 persist 前補 late gate，讓 pause / disable 在後段也能阻止通知或結果提交。

`src/app/domain/watch_lifecycle_state_machine.py` 是 lifecycle transition 的正式決策中心。它統一處理人工 enable / disable / pause / resume / check-now，以及 runtime blocked pause，並輸出 watch 更新、runtime state event、scheduler side effect 與 in-flight policy。

`WatchLifecycleCoordinator` 負責讀取目前 watch / latest snapshot、呼叫 state machine、保存人工 transition，並依 decision 移除 scheduler active set；它不再轉呼叫 `WatchEditorService`。runtime auto-pause 也透過 `RuntimeControlRecommendation` 承載 state machine decision，`runtime.py` 不再自行拼接 paused watch 或保留獨立 lifecycle event builder。

目前決策：

- 維持現有 in-flight policy：不硬取消，以多段 gate 丟棄結果
- 不新增 `watch_control_states` table；等第二站或更複雜控制需求明確後再評估 migration
- `WatchEditorService` 聚焦 watch 建立、刪除、通知規則與 preview，不再負責 lifecycle transition

### 9.2 Browser strategy 已完成第一輪 per-request 化

`ChromeCdpHtmlFetcher` 的主要抓取方法已可接收 request-scoped browser page strategy；runtime 與 Chrome tab preview 會依 adapter 傳入對應策略。後續若新增第二站，應在 `sites/<site>` 實作自己的 strategy，並從 adapter 暴露，不要把站點規則塞進 fetcher。

### 9.3 UI / Preview Flow 的單站假設已完成第一輪收斂

目前已補 `SiteDescriptor`，新增 watch 與 Chrome 分頁選擇頁已開始使用 site metadata，`PreviewAttemptGuard` 也不再提供 `site_name="ikyu"` 預設值。後續仍應讓 Chrome tab preview service 直接回傳 site descriptor，避免 route 層自行補 tab label。

### 9.4 `main.py` 偏大

site descriptor、per-site strategy、lifecycle owner 與 task disposition 已完成第一輪，可以開始低風險拆分 route / web orchestration。拆分 guardrails：

- `main.py` 保留 app 建立、lifespan、container 掛載、router include
- routes 可依頁面群組拆到 `src/app/web/routes/`
- 共用 request / form parsing helper 可先抽到 `src/app/web/`
- 不在 route 層新增 lifecycle 決策，必須繼續呼叫 application service / state machine owner
- 不在 route 層新增 site-specific 規則，必須透過 `SiteAdapter` / registry
- 每一刀只搬一組 route 或一組 helper，搬完跑 route 相關測試

目標結構：

- `src/app/main.py`：app factory、lifespan、router include
- `src/app/web/routes/watch_routes.py`：watch list、detail、control action、creation flow
- `src/app/web/routes/settings_routes.py`：notification channel settings
- `src/app/web/routes/debug_routes.py`：debug captures
- `src/app/web/routes/system_routes.py`：health / fragments 可視情況拆分

### 9.5 `web/views.py` 偏大

後續應依頁面拆分 render helper：

- watch list
- watch detail
- notification settings
- global settings
- debug captures

### 9.6 `ChromeCdpHtmlFetcher` 偏大

per-site strategy 落地後，可再拆成：

- profile 啟動
- CDP attach
- tab matching
- capture / throttling / discard 訊號

### 9.7 State Ownership 仍需守住

後續新增功能時，避免：

- 把 runtime 結果塞回 `watch_item`
- 讓 GUI 直接用多個 primitive 欄位拼狀態
- 讓通知狀態、最新狀態、debug 摘要互相重疊
