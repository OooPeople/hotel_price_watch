# Architecture Plan

本文件只描述長期有效的架構邊界、決策與 guardrails。實作進度看 `docs/TASK_BREAKDOWN.md`，接手摘要看 `docs/HANDOFF_PLAN.md`，UI 參考與 phase 看 `docs/UI_REDESIGN_PLAN.md`。

## 1. 系統主線

V1 正式主線是 Chrome-driven：

- 使用專用 Chrome profile + CDP attach。
- 以 browser page 作為正式資料來源。
- 建立 watch 從專用 Chrome 分頁 preview 開始，不回到手動 Seed URL 主線。
- `HTTP-first` 不再視為 V1 正式路徑，只保留必要相容測試與歷史脈絡。
- 目前只支援 `ikyu`，但站點細節必須留在 `sites/ikyu` 與 site wiring。

架構分層原則：

- `domain` 保存純規則與資料模型。
- `application` 保存 use case / orchestration。
- `monitor` 保存 scheduler、runtime、backoff、狀態與通知觸發協調。
- `infrastructure` 保存 SQLite、Chrome CDP、file lock 等外部技術。
- `sites` 保存站點 adapter、parser、browser matching / strategy。
- `web` 保存本機 GUI route、page service、presenter、renderer 與 client script。

## 2. 資料與狀態邊界

正式流程需區分：

- `SearchDraft`：從目前頁面 URL / browser page 解析出的建立草稿。
- `WatchTarget`：可正式監看的精確 target identity。
- `WatchItem`：使用者設定，不混入 runtime 結果。
- `LatestCheckSnapshot`：列表與狀態判斷用的最新摘要。
- `CheckEvent`：每次檢查歷史。
- `PriceHistoryEntry`：成功價格點。
- `NotificationState` / `NotificationThrottleState`：通知去重與通道冷卻。
- `RuntimeStateEvent`：blocked / paused / resumed / recovered 等狀態轉移。
- `DebugArtifact`：runtime 或 parser 診斷資料。

守則：

- 不把 runtime 結果塞回 `watch_item`。
- GUI 與 runtime 都透過 `WatchRuntimeState` 解讀目前狀態。
- 通知狀態、最新狀態、debug 摘要不可互相重疊。
- `watch_item.enabled` 與 `watch_item.paused_reason` 目前仍是最小 control state；不得再臨時增加更多 control 欄位到 `WatchItem`。

### 2.1 Lodging Target Contract

目前 `SearchDraft`、`WatchTarget`、`OfferCandidate` 與 SQLite schema 仍採 lodging-room-plan 形狀：

- `hotel_id`
- `room_id`
- `plan_id`
- check-in / check-out
- people / room count

這是 V1 支援 `ikyu` 的刻意取捨，不代表通用層已經完成任意站點抽象。

第二站決策：

- 若第二站同屬 hotel / room / plan 型網站，可先沿用目前 contract。
- 若第二站不是這種目標模型，應先設計 site-specific target payload / candidate payload 與 migration。
- 在第二站樣本明確前，不把 `WatchTarget` / `SearchDraft` payload 化。
- 新程式碼不得把更多 `ikyu` 專屬語意塞進 route、view、runtime 或 repository。

### 2.2 `watch_control_states` Future Migration

目前不立即實作 `watch_control_states` migration，但長期方向已固定：

- `watch_items`：只保存 watch 靜態定義，例如 target、顯示資訊、canonical URL、notification rule、scheduler interval。
- `watch_control_states`：保存 control plane 狀態，例如 enabled、paused reason、updated time、version。
- lifecycle state machine 未來輸出 control state transition，而不是直接回傳修改後的 `WatchItem`。
- repository 提供 GUI / runtime 需要的 read model，避免 route 或 runtime 自行拼 join。

觸發條件：

- 第二站需要更多 control state。
- 出現 per-site control policy。
- 需要 user-visible pause reason history 或 control state versioning。
- `enabled` / `paused_reason` 以外的控制欄位開始增加。

## 3. Site Boundary

`SiteAdapter` 是 GUI / runtime 使用站點能力的正式邊界。新增站點時優先擴充 `src/app/bootstrap/site_wiring.py` 與 `src/app/sites/<site>`，不要把站點規則塞進 `main.py`、routes、views、runtime 或 `ChromeCdpHtmlFetcher`。

目前 adapter 需承擔：

- URL match / browser page eligibility。
- seed URL / browser page draft parsing。
- candidate fetch / preview。
- watch target resolution。
- runtime snapshot build。
- browser page strategy 與 tab matching。

`ChromeCdpHtmlFetcher` 只保留 generic CDP operation façade；站點 blocking detection、ready detection、page scoring、page signature 與 confident matching 透過 site-provided browser strategy 注入。

## 4. Browser-Driven Flow

### 建立 Watch

1. 使用者啟動 GUI 與專用 Chrome。
2. 使用者在專用 Chrome 開啟可 preview 的 `ikyu` 頁面。
3. GUI 列出可附著分頁。
4. 使用者選分頁。
5. adapter 從 browser page 建立 preview。
6. 使用者確認候選、通知規則與輪詢秒數。
7. application service 建立 `watch_item` / draft，並把 preview 初始價格以單一 transaction 寫入 latest snapshot、check event、price history。

### 背景監看

1. runtime 啟動時低速恢復 enabled 且未 paused 的 watch 分頁。
2. scheduler 取出到期 watch。
3. runtime 依 watch identity、`browser_page_url`、canonical URL 與 query-aware matching 找回或補建分頁。
4. Chrome 擷取 HTML。
5. adapter 建立 `PriceSnapshot`。
6. compare / notification engine 判斷事件與通知。
7. repository 以單一 transaction 寫入最新摘要、歷史、通知狀態、runtime event、debug artifact。

`tab_id` 只作為當次 Chrome session 的短期操作鍵，不作為 watch identity。

## 5. Control Command Policy

V1 採 `continue-and-gate`：

- `pause` / `disable` 立即阻止新的 scheduler dispatch 與 `check-now`。
- 已 in-flight 的 check 不硬取消。
- runtime 在 capture 後、通知前、持久化前重新讀 control state。
- 若 watch 已 pause / disable，該次結果丟棄。
- 若 notifier 已送出或 DB transaction 已開始，不嘗試回滾。
- `resume` / `enable` 只解除 control gate，不代表站點已恢復；若 latest snapshot 仍是 blocked error，current state 仍可為 `RECOVER_PENDING`。

使用者在 `pause` / `disable` 後可以關閉對應 Chrome 分頁。若當下有 in-flight check，最多視為 bounded browser error；不應造成 watch 永久壞掉或 paused / disabled watch 持續重試。

## 6. Blocking 語意

新程式碼使用 generic 語意：

- browser blocking outcome：`BrowserBlockingOutcome`
- blocked pause event：`pause_due_to_blocking`
- blocked pause current state：`paused_blocked`

歷史相容仍保留：

- `pause_due_to_http_403`
- `paused_blocked_403`
- `http_403`

後續若新增 challenge / login wall / captcha，應擴充 outcome 與 control recommendation，不再新增訊息片段判斷。

## 7. Web 架構邊界

Web 層切分方向：

- route：request parsing、origin guard、redirect / response type、HTTP status。
- page service：組頁面 context、revision token；不得直接組 HTML fragment payload。
- fragment payload assembler：把 page context 與 revision 組成 JSON payload。
- presenter / page view model：集中 UI 文案、狀態、排序與顯示判斷。
- partial renderer：只負責 HTML 組裝。
- client script renderer：集中 inline behavior。
- contract module：集中 DOM id、payload key、fragment endpoint contract。

目前 guardrails：

- 新 renderer 不應把實作加回 `watch_view_partials.py`、`view_helpers.py` 或 `ui_components.py` 這類相容 re-export 檔。
- Watch list / detail fragment payload 與 DOM hook 由 `watch_fragment_contracts.py` 管理。
- Watch Detail fragment section 由 `WATCH_DETAIL_FRAGMENT_SECTIONS` 管理；page shell、fragment assembler 與 client script 必須吃同一份 section registry，不可各自手寫 DOM id / payload key 對應。
- Watch list / detail fragment payload HTML 組裝由 `watch_fragment_payloads.py` 管理；`WatchPageService` 只提供 read context 與 revision token。
- Settings / watch creation DOM id 由 `client_contracts.py` 管理。
- page-level client behavior 需從 page script entrypoint 匯出，例如 `watch_detail_page_scripts.py`、`settings_page_scripts.py`；partial 不直接拼多段 script。
- 重複 layout pattern 放入 `ui_page_sections.py` 或既有 UI helper；第二輪 UI 不新增大量 ad-hoc inline layout string。
- Watch Detail / Settings 第二輪 UI 必須沿用既有 page view model，不把 domain 判斷塞回 partial。
- 新共用 UI 放到 `ui_layout.py`、`ui_primitives.py`、`ui_icons.py` 或 `ui_behaviors.py`。

## 8. Persistence 邊界

SQLite table 不急著拆，但 Python adapter 責任需分離：

- runtime write：latest snapshot、check event、price history、notification state、runtime event、debug artifact 的寫入 transaction。
- history query：detail page history、price history、runtime events、debug artifacts 查詢。
- fragment query：watch list / detail revision token 與 fragment 輕量查詢。
- notification throttle state：通道級節流狀態。

目前 `repositories.py` 只保留相容 re-export；SQLite serializer、revision token helper、watch item row mapping、watch item repository、runtime repository façade、runtime write records、runtime history query SQL、runtime fragment revision query、notification throttle state SQL 與 app settings repository 都已拆到 dedicated modules。正式 `AppContainer` 不再持有 `SqliteRuntimeRepository`；該 façade 只保留給相容測試與舊呼叫端過渡，新增正式路徑必須使用 write / history / fragment / throttle 專用 repository。

下一輪資料層收斂方向：

- 每個 façade 應逐步對應到自己的 SQL owner，不只拆 public API。
- watch item persistence、runtime write records、runtime history query、fragment revision query、notification throttle state 與 app settings persistence 已有 dedicated module。
- row mapping、datetime / decimal / JSON serialization、revision token hashing 已離開主 repository module。
- 後續資料層若要再收斂，優先檢查 façade 是否能從相容入口改成直接 import；每一刀都不改 schema 與 public behavior。

## 9. Runtime 邊界

`ChromeDrivenMonitorRuntime` 應維持高階協調入口，只負責：

- dependency wiring
- start / stop
- runtime loop
- status
- 呼叫既有 coordinator / executor

低階責任已有 owner：

- `WatchCheckExecutor`：單次檢查、capture、compare、notification gate、persistence orchestration。
- `BrowserAssignmentRestorer`：啟動恢復、claimed tabs、restore capture without reload。
- `WatchAssignmentCoordinator`：scheduler due work、in-flight task registry、check-now 共用任務。
- `NotificationDispatchCoordinator`：notifier factory、dispatcher cache、notification dispatch。
- `WatchDefinitionSyncCoordinator`：watch definition sync、scheduler register/update/remove、sleep wakeup rescan。

新增 runtime feature 時，先判斷應放入既有 owner，避免把流程塞回 `runtime.py`。

下一輪 runtime 收斂方向：

- 目前不主動大拆 `WatchCheckExecutor`。
- `check_pipeline_contexts.py` 已建立 setup / captured / evaluated context，降低單次 check 內大量局部變數互傳。
- 若之後要新增 gate checkpoint、control recommendation、runtime event 或 persistence side effect，先延伸既有 pipeline context，再加功能。
- 避免新增行為時同時散改 executor、policy、event builder 與 artifact builder。

## 10. Web 第二輪責任收斂

`web/` 已完成第一輪拆分，但 page-area 模組仍可能成為新的壓力中心。後續 UI 功能增加前，優先守住：

- `watch_creation_routes.py` 已把 preview、cache、create 與 initial snapshot orchestration 交給 `WatchCreationWorkflow`；route 只保留 request / response mapping。新增建立流程時仍應放進 workflow/helper，不塞回 route。
- `watch_client_scripts.py` 已降為相容 re-export；watch list / watch detail script renderer 已拆到 page-specific module。後續若 script 再成長，優先拆 polling、view mode、runtime dock、relative time、action submit 等小 owner。
- Watch Detail page shell 已移到 `watch_detail_views.py`，fragment HTML 組裝集中在 `watch_detail_fragment_assembler.py`；新增 detail 區塊時先改 section registry 與 assembler，不直接散改 route、page service 或 client script。
- `watch_fragment_payloads.py` 是 watch list / detail fragment payload 的 HTML 組裝入口；route 先向 page service 取 context / revision，再交給 payload assembler。
- `ui_page_sections.py` 提供 page stack、responsive section grid、details panel、inline cluster 與欄位群組 helper，避免 Watch Detail / Settings 第二輪繼續累積 page-specific layout string。
- `watch_detail_page_scripts.py` 與 `settings_page_scripts.py` 是頁面級 client behavior entrypoint；新增行為時先掛到 entrypoint，不從 partial 任意串接 script。
- `settings_partials.py` 已降為相容 re-export；全域設定、單一 watch 通知規則、測試通知 partial 已拆到 page-area modules。
- Dashboard list partial 已拆出 runtime dock 與 summary card modules；watch creation partial 已拆出 Chrome tab selection 與 diagnostics modules。
- 大型 partial / presenter 模組若繼續成長，應拆成 page-area component，而不是把 HTML / JS / state 判斷重新堆在同一檔。
- `watch_fragment_contracts.py` 與 `client_contracts.py` 繼續作為 DOM / payload contract owner。

## 11. 測試策略

至少維持：

- parser / normalizer fixture tests。
- runtime focused tests。
- SQLite integration tests。
- web route / renderer / fragment contract tests。
- notifier formatter / dispatcher / transport tests。

測試放置原則：

- `tests/unit/application/`：application service 與 use-case。
- `tests/unit/domain/`：純 domain 規則。
- `tests/unit/infrastructure/`：非 browser-specific infrastructure。
- `tests/unit/monitor/`：monitor 基礎元件。
- `tests/unit/monitor_runtime/`：background runtime 相關。
- `tests/unit/notifiers/`：notifier。
- `tests/unit/sites/`：site registry 與站點邊界；parser fixture 測試仍放 `tests/sites/<site>/`。
- `tests/unit/web/`：GUI route、renderer、fragment contract、settings、watch action、watch creation、debug capture。
- `tests/unit/` 根目錄不再新增 top-level `test_*.py`。

legacy compatibility 測試需保留清楚語意；只要相容程式碼仍存在，不應單純因為不是新主線而刪除。
