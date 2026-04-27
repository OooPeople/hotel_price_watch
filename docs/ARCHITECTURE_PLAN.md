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
└─ main.py          # app factory、lifespan、router include 與 health endpoint
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

### 3.1 Lodging Target Contract

目前 `SearchDraft`、`WatchTarget`、`WatchTargetIdentity`、`OfferCandidate`、`CandidateSelection` 與 SQLite schema 仍採 lodging-room-plan 形狀：

- `hotel_id`
- `room_id`
- `plan_id`
- check-in / check-out
- people / room count

這是 V1 支援 `ikyu` 的刻意取捨，不代表通用層已經完成任意站點抽象。第二站若同樣屬於 hotel / room / plan 型住宿網站，可沿用目前 contract；若第二站不是這種目標模型，應先設計 site-specific target payload / candidate payload 與 migration，再實作站點。

在第二站樣本明確前，不急著把 `WatchTarget` / `SearchDraft` payload 化，避免做出無根據的抽象。但新增程式碼時需避免把更多 `ikyu` 專屬語意塞進 route、view、runtime 或 repository，並把站點判斷留在 `SiteAdapter` / `sites/<site>`。

### 3.2 `watch_control_states` Future Migration Plan

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

後續可改善：

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

## 9. GUI Settings Boundary

全域設定頁正式入口是 `/settings`。舊 `/settings/notifications` 與 `/settings/notifications/test` 保留相容，但新連結與表單應使用 `/settings` 與 `/settings/test-notification`。

目前設定拆成兩個 model：

- `NotificationChannelSettings`：只保存通知通道設定，例如 desktop、ntfy、Discord webhook
- `DisplaySettings`：保存 GUI 顯示偏好，例如 12 / 24 小時制

設定可集中在同一頁顯示，但不應把不同種類的設定塞進同一個 dataclass。新增設定時先判斷是否應建立獨立 model / table，再由設定頁組合呈現。

## 10. 已完成的架構收斂與守則

### 10.1 Lifecycle Owner 已完成第一輪收斂

目前 control command policy 已明確，且 runtime 已在 notification dispatch 前與 persist 前補 late gate，讓 pause / disable 在後段也能阻止通知或結果提交。

`src/app/domain/watch_lifecycle_state_machine.py` 是 lifecycle transition 的正式決策中心。它統一處理人工 enable / disable / pause / resume / check-now，以及 runtime blocked pause，並輸出 watch 更新、runtime state event、scheduler side effect 與 in-flight policy。

`WatchLifecycleCoordinator` 負責讀取目前 watch / latest snapshot、呼叫 state machine、保存人工 transition，並依 decision 移除 scheduler active set；它不再轉呼叫 `WatchEditorService`。runtime auto-pause 也透過 `RuntimeControlRecommendation` 承載 state machine decision，`runtime.py` 不再自行拼接 paused watch 或保留獨立 lifecycle event builder。

目前決策：

- 維持現有 in-flight policy：不硬取消，以多段 gate 丟棄結果
- 不新增 `watch_control_states` table；等第二站或更複雜控制需求明確後再評估 migration
- `WatchEditorService` 聚焦 watch 建立、刪除、通知規則與 preview，不再負責 lifecycle transition

### 10.2 Browser strategy 已完成第一輪 per-request 化

`ChromeCdpHtmlFetcher` 的主要抓取方法已可接收 request-scoped browser page strategy；runtime 與 Chrome tab preview 會依 adapter 傳入對應策略。後續若新增第二站，應在 `sites/<site>` 實作自己的 strategy，並從 adapter 暴露，不要把站點規則塞進 fetcher。

### 10.3 UI / Preview Flow 的單站假設已完成第一輪收斂

目前已補 `SiteDescriptor`，新增 watch 與 Chrome 分頁選擇頁已使用 site metadata，`PreviewAttemptGuard` 也不再提供 `site_name="ikyu"` 預設值。後續可讓 Chrome tab preview service 直接回傳 site descriptor，避免 route 層自行補 tab label。

### 10.4 `main.py` 已完成第一輪拆分

site descriptor、per-site strategy、lifecycle owner 與 task disposition 已完成第一輪，route / web orchestration 也已完成第一輪拆分。維護 guardrails：

- `main.py` 保留 app 建立、lifespan、container 掛載、router include
- routes 可依頁面群組拆到 `src/app/web/routes/`
- 共用 request / form parsing helper 可先抽到 `src/app/web/`
- 不在 route 層新增 lifecycle 決策，必須繼續呼叫 application service / state machine owner
- 不在 route 層新增 site-specific 規則，必須透過 `SiteAdapter` / registry
- 每一刀只搬一組 route 或一組 helper，搬完跑 route 相關測試
- route 若需要組多個 repository / service 結果給 renderer，優先抽小型 page context helper，避免同一頁首屏與 fragment 路徑各自重組資料

目前結構：

- `src/app/main.py`：app factory、lifespan、router include
- `src/app/web/routes/watch_routes.py`：watch list、detail、control action
- `src/app/web/routes/watch_creation_routes.py`：watch creation / Chrome tab preview flow
- `src/app/web/routes/settings_routes.py`：notification channel settings
- `src/app/web/routes/debug_routes.py`：debug captures
- `src/app/web/routes/system_routes.py`：health 可視情況再拆分

### 10.5 `web/views.py` 已收斂為 re-export 入口

頁面 render helper 已依頁面群組拆分，`src/app/web/views.py` 只保留相容 re-export：

- o debug captures 已拆到 `src/app/web/debug_views.py`
- o notification settings / global settings 已拆到 `src/app/web/settings_views.py`
- o watch list 已拆到 `src/app/web/watch_views.py`
- o watch detail 已拆到 `src/app/web/watch_views.py`
- o watch creation / Chrome tab selection 已拆到 `src/app/web/watch_creation_views.py`

第二輪 view 整理方向是把「頁面級 renderer」與「可替換 UI partial」再拆開，避免後續 UI 美化或版面重設時繼續改動整個頁面 renderer。目前已完成：

- o watch list / detail partial 已拆到 `src/app/web/watch_view_partials.py`
- o watch creation / Chrome tab selection partial 已拆到 `src/app/web/watch_creation_partials.py`
- o style token 已拆到 `src/app/web/ui_styles.py`
- o card、empty state、data table、button/link 等 UI primitives 已拆到 `src/app/web/ui_components.py`
- o display formatter 已拆到 `src/app/web/view_formatters.py`
- o `src/app/web/view_helpers.py` 保留為舊 import 的相容匯出入口

後續 UI 美化應優先改 `ui_styles.py` 的 token 與 `ui_components.py` 的 component helper，只有在資訊架構改變時才調整各頁 partial。
新 renderer 應直接 import `ui_styles.py`、`ui_components.py`、`view_formatters.py`，不要再把 `view_helpers.py` 當正式入口使用。

### 10.6 `ChromeCdpHtmlFetcher` 已完成第一輪責任拆分

`ChromeCdpHtmlFetcher` 目前保留為 CDP browser operation 的 orchestration façade，內部責任已拆成：

- o profile 啟動與 profile preference 寫入：`src/app/infrastructure/browser/chrome_profile_launcher.py`
- o CDP attach 與 Playwright lifecycle：`src/app/infrastructure/browser/chrome_cdp_connection.py`
- o tab matching / score / confidence 判斷：`src/app/infrastructure/browser/chrome_page_matcher.py`
- o capture / throttling / discard 訊號：`src/app/infrastructure/browser/chrome_page_capture.py`
- o capture 資料模型：`src/app/infrastructure/browser/chrome_models.py`

### 10.7 State Ownership 仍需守住

後續新增功能時，避免：

- 把 runtime 結果塞回 `watch_item`
- 讓 GUI 直接用多個 primitive 欄位拼狀態
- 讓通知狀態、最新狀態、debug 摘要互相重疊

## 11. Watch Detail / Settings UI 前的架構整理 Gate

Dashboard 第二輪 UI 重構期間暴露出新的 web 維護風險：問題不再集中於 `views.py`，而是轉移到 route orchestration、watch partial renderer、inline scripts 與 page fragment contract。進入 Watch Detail 與 Settings 第二輪 UI 前，需先做一輪架構整理，避免同樣問題在後續頁面被放大。

### 11.1 Route 層責任收斂

`web/routes/` 仍可負責 request / response、origin guard、redirect 與 HTTP status，但不應持續承接 page workflow 與 persistence 細節。

優先整理方向：

- watch list / detail 的 page context、fragment payload 與 revision token 可逐步抽成 page service 或 read model builder。
- watch creation 的初始價格保存已移到 `WatchCreationSnapshotService`，並透過 repository 單一 transaction 寫入 latest snapshot、check event 與 price history；後續 route 不應再新增 runtime persistence 細節。
- control action 的 route fallback 可保留，但 quick action fragment response contract 應集中在固定 payload model，不在多個 handler 中手工拼接。
- route 不新增 site-specific 判斷；站點資格、preview eligibility 與 target matching 仍透過 `SiteAdapter`。

### 11.2 Watch Partial 與 Client Script 分離

`watch_view_partials.py` 曾是新的 UI 壓力中心，當時同時承接 list / detail partial、runtime dock、price trend、debug sections、fragment polling script 與 DOM data attribute contract。現在已先拆出 client scripts、list partial、detail partial 與 action partial；後續重構 Watch Detail 時，實作應放在新模組，不再回填到相容匯出檔。

建議拆分順序：

- `watch_list_partials.py`：Dashboard summary、watch card / list row、runtime dock。
- `watch_detail_partials.py`：detail hero、價格摘要、價格趨勢、檢查歷史、runtime state events、debug artifacts。
- `watch_client_scripts.py`：watch list / detail version polling、relative time updater、runtime dock collapse、view mode persistence。

目前 `watch_client_scripts.py`、`watch_action_partials.py`、`watch_list_partials.py` 與 `watch_detail_partials.py` 已完成抽出；舊 `watch_view_partials.py` 只保留相容匯出，新 renderer 不應再把實作加回該檔。

拆分時需維持既有 route contract，不在同一刀同時改視覺與資料語意。

### 11.3 Page Contract 與 View Model

首頁重構後已證明單純把 domain entity 傳入 renderer 會讓 HTML、狀態文案、排序與 JS contract 互相牽動。後續頁面改版時應優先建立 page-level contract：

- Dashboard 以 `WatchRowPresentation` 作為 row / card 判讀入口，後續可再收斂為 `DashboardPageViewModel`。
- Watch Detail 已建立 `WatchDetailPresentation`，集中 hero、目前價格、空房、通知摘要、runtime state 與技術資訊需要的基礎資料；後續重構 `07_watch_detail.png` 時應沿用這個 presenter。
- Settings 已建立 `NotificationChannelSettingsPresentation`，集中「摘要顯示」、「啟用狀態」、「表單回填」與遮罩文案；後續重構 `05_settings_notifications.png` 時應沿用這個 presenter。
- watch list / detail fragment payload 與 DOM hook 已集中到 `src/app/web/watch_fragment_contracts.py`，route、renderer、client script 與測試需共用此 contract，不再各自硬寫 key / id。

後續若新增局部更新區塊，應先擴充 contract，再調整 fragment payload builder、HTML id 與 client script，避免出現「後端欄位已改、前端仍抓舊 key」或「按鈕行為混用」的維護風險。

### 11.4 Client Update Policy

首頁與詳細頁的更新策略已改為 version polling：

- 後端提供輕量 version endpoint。
- 前端只在 version 改變時抓取 HTML fragment。
- 相對時間與退避倒數屬於純前端顯示更新，不應觸發後端 fragment refresh。

後續新增頁面局部更新時，需沿用這個策略，不要回到固定時間抓整包 fragment。

### 11.5 UI 基礎設施拆分方向

`ui_components.py` 目前仍混合 AppShell、layout、icons、primitives 與少量 behavior script。它不是 Watch Detail / Settings 前的阻塞項，但新增共用 UI 時應避免繼續膨脹。

長期拆分方向：

- `ui_layout.py`：AppShell、sidebar、page shell。
- `ui_primitives.py`：button、badge、card、table、action row。
- `ui_icons.py`：inline SVG icon registry。
- `ui_behaviors.py`：跨頁共用 client-side behavior。
