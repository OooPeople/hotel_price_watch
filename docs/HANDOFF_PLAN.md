# Handoff Plan

本文件給新對話窗快速接手。建議先讀：

1. `docs/V1_SPEC.md`
2. `docs/ARCHITECTURE_PLAN.md`
3. `docs/UI_REDESIGN_PLAN.md`
4. `docs/TASK_BREAKDOWN.md`
5. `docs/HANDOFF_PLAN.md`

## 1. 目前狀態

專案目前已可實際使用：

- 單一啟動命令：`uv run python -m app.tools.dev_start`
- 專用 Chrome profile + CDP attach
- 從專用 Chrome 分頁建立 `ikyu` watch
- watch 列表、詳情、歷史、debug、通知設定
- watch 啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- 通用設定頁：通知通道、測試通知、GUI 時間顯示格式
- 設定頁提供未儲存提示與離頁前防呆
- background runtime 定期刷新、寫入歷史並發送通知
- 首頁與 watch 詳細頁已採 version polling：資料版本改變才抓 fragment，相對時間 / 退避倒數由前端局部更新

最新驗證狀態：

- 最近一次本輪驗證：`ruff check` 通過
- 最近一次本輪驗證：`pytest tests/unit -q` 通過，`225 passed`

## 2. 正式主線

V1 正式主線是 Chrome-driven：

- 不回到 `HTTP-first`
- 不加回手動 Seed URL 建立流程
- 建立 watch 的正式入口是「從目前專用 Chrome 頁面抓取」
- Chrome 分頁 preview 成功後，建立 watch 使用短期 preview cache，不再於提交建立時重抓同一分頁
- Watch creation preview cache 是 application service，掛在 `AppContainer.watch_creation_preview_cache`，不要在 route module 放全域 preview 狀態
- Chrome 分頁 URL 判斷分成兩層：`is_browser_page_url` 用於站點辨識 / 既有 watch 比對，`is_browser_preview_url` 用於建立 preview；IKYU 首頁與缺少飯店日期人數條件的頁面不可作為新增監視來源
- background runtime 依附專用 Chrome session 刷新頁面並解析價格
- `tab_id` 只作為短期操作鍵，不作為 watch identity
- watch identity 以 target identity / `browser_page_url` / query-aware matching 判斷

## 3. 核心架構決策

### Watch 與 Runtime State

- `watch_item` 保存使用者設定，不保存 runtime 結果
- runtime 結果保存到 latest snapshot、check events、price history、notification state、runtime state events、debug artifacts
- GUI 狀態統一透過 `WatchRuntimeState` 解讀
- `RECOVER_PENDING` 表示 control state 已恢復，但 latest snapshot 尚未證明站點成功恢復
- `watch_control_states` 目前只做 future migration plan，不立即 migration

### Control Command Policy

- `pause` / `disable` 立即阻止新任務
- in-flight check 不硬取消，採 `continue-and-gate`
- runtime 在 `AFTER_CAPTURE`、`BEFORE_NOTIFICATION_DISPATCH`、`BEFORE_PERSIST_RESULT` checkpoint 重讀 control state
- 若中途被 pause / disable，本次結果丟棄
- 若已進入 DB transaction，允許安全收尾
- 使用者在 `pause` / `disable` 後可以關閉對應 Chrome 分頁；若當下有 in-flight check，最多視為一次 bounded browser error
- `resume` / `enable` 後，runtime 應能依 watch identity、`browser_page_url` 與 canonical URL 重新找回或補開分頁

### Site Boundary

- 站點 adapter 與 browser strategy wiring 集中在 `src/app/bootstrap/site_wiring.py`
- `SiteAdapter` 承擔 browser page capability 與 strategy
- `ikyu` 規則留在 `src/app/sites/ikyu`
- `ChromeCdpHtmlFetcher` 只保留 generic CDP orchestration，不放站點規則

### Blocking 語意

- 新程式碼使用 generic 語意：`BrowserBlockingOutcome`、`pause_due_to_blocking`、`paused_blocked`
- 舊 403 enum / state 保留相容，不要移除
- `forbidden` 仍映射為 `http_403`，`rate_limited` 映射為 `http_429`

## 4. 目前重要模組

- `src/app/domain/watch_lifecycle_state_machine.py`：control command 與 runtime blocked pause 的正式決策中心
- `src/app/application/watch_lifecycle.py`：lifecycle coordinator
- `src/app/monitor/runtime.py`：Chrome-driven background runtime
- `src/app/infrastructure/browser/chrome_cdp_fetcher.py`：Chrome CDP operation façade
- `src/app/infrastructure/browser/chrome_profile_launcher.py`：專用 Chrome 啟動與 profile 設定
- `src/app/infrastructure/browser/chrome_cdp_connection.py`：Playwright CDP attach
- `src/app/infrastructure/browser/chrome_page_matcher.py`：分頁 matching / scoring
- `src/app/infrastructure/browser/chrome_page_capture.py`：HTML capture 與 throttling / discard 訊號
- `src/app/web/routes/`：本機 GUI routes
- `src/app/web/*_views.py`：本機 GUI renderers
- `src/app/web/ui_styles.py`：GUI style token 與語意化 style helper
- `src/app/web/ui_components.py`：GUI 共用 layout、button、card、empty state、table 等 UI primitives；含可收合 AppShell、inline SVG icon 導覽與窄版 responsive 規則
- `src/app/web/ui_presenters.py`：GUI presentation helper，集中價格、狀態、通知、錯誤與 badge 文案
- `src/app/web/watch_detail_presenters.py`：watch detail page presentation，集中 detail hero、價格摘要、通知摘要與 runtime state 基礎資料
- `src/app/web/settings_presenters.py`：全域設定頁 presentation，集中摘要卡、啟用狀態、表單回填與敏感值遮罩
- `src/app/web/view_formatters.py`：GUI 共用顯示格式化 helper
- `src/app/web/view_helpers.py`：舊 renderer import 的相容匯出入口
- `src/app/web/watch_client_scripts.py`：watch list / detail version polling、relative time updater、runtime dock collapse 與 list view mode persistence script renderer
- `src/app/web/watch_fragment_contracts.py`：watch list / detail fragment payload schema 與 DOM hook id contract；route、renderer、client script 與測試需共用此檔定義
- `src/app/web/watch_action_partials.py`：watch 操作表單與 quick action mode renderer
- `src/app/web/watch_list_partials.py`：watch list / dashboard partial renderer 實作入口
- `src/app/web/watch_detail_partials.py`：watch detail partial renderer 實作入口
- `src/app/web/watch_view_partials.py`：舊 renderer import 的相容匯出入口，新程式碼不要再把實作加回此檔
- `src/app/web/watch_creation_partials.py`：新增 watch / Chrome tab selection 可替換區塊 partial；新增流程上方採 3-step wizard，確認建立收在 Step 3 內容內
- `src/app/web/debug_views.py`：進階診斷 / preview capture renderer，raw metadata 與 HTML 預覽預設收合
- `docs/ui_reference/`：第二輪 UI 參考圖；實作 Dashboard、Add Watch、Settings、Debug 或 AppShell 前後都應開啟對應圖片對照
- `src/app/tools/dev_start.py`：單一啟動入口；會在本專案流程內加入 `NODE_OPTIONS=--disable-warning=DEP0169`，抑制 Playwright driver 在 Node 24 觸發的 `url.parse()` deprecation warning
- `src/app/sites/ikyu/`：`ikyu` adapter、parser、normalizer、browser strategy

目前 review 後的 web 架構注意事項：

- `watch_view_partials.py` 的壓力已先解除：client scripts、list partial、detail partial、action partial 已拆出；下一步不要再把新 UI 實作加回相容檔。
- watch creation 初始價格保存已移入 `WatchCreationSnapshotService`，並以 repository 單一 transaction 寫入 latest snapshot、check event、price history。
- watch list / detail fragment payload 與 DOM hook contract 已集中到 `watch_fragment_contracts.py`，後續新增 fragment 欄位或改 DOM id 應先改 contract，再同步 renderer / client script / tests。
- Watch Detail / Settings 第二輪 UI 前的 presenter gate 已完成：Detail 使用 `WatchDetailPresentation`，Settings 使用 `NotificationChannelSettingsPresentation`；後續重構視覺時不要把摘要判讀放回 partial。
- `ui_components.py` 可暫時保留，但新增共用 UI 時避免繼續混入 layout、icons、primitives 與 behavior script。
- 第二站 target / candidate contract 已在架構文件中標記為 lodging-room-plan 暫緩，不因這輪 UI 架構整理提前 payload 化。

目前 UI 進度口徑：

- Dashboard 與 Add Watch 的第二輪主要流程已落地；Watch Detail / Settings 前置 web 架構整理已完成，可開始第二輪頁面 UI 重構。
- Watch Detail 只有第一輪產品化與 MiniPriceChart / fragment polling 強化，尚未完成 `07_watch_detail.png` 的整頁重構。
- Settings 只有第一輪摘要 / 展開編輯 / webhook 遮罩，尚未完成 `05_settings_notifications.png` 的通道卡片新版。

## 5. 第二站前注意事項

目前通用層仍是 lodging-room-plan contract：

- `hotel_id`
- `room_id`
- `plan_id`
- check-in / check-out
- people / room count

第二站決策：

- 若第二站同屬 hotel / room / plan 型住宿網站，可先沿用目前 contract
- 若第二站不是這種形狀，先設計 site-specific target payload / candidate payload 與 migration
- 不要在第二站樣本明確前把 `WatchTarget` / `SearchDraft` payload 化
- 不要在第二站樣本明確前把 runtime 泛化成非 browser runtime

## 6. 不要重做的方向

- 不要回到 `HTTP-first` 主線
- 不要把 Seed URL 手動輸入流程加回 GUI
- 不要把站點規則塞回 `main.py`、routes、views 或 `ChromeCdpHtmlFetcher`
- 不要把 runtime 結果塞回 `watch_item`
- 不要移除舊 403 enum / state
- 不要為了抽象第二站而在沒有樣本時大改 DB schema
- 不要在新 renderer 中把 `view_helpers.py` 當正式入口；應直接用 `ui_styles.py`、`ui_components.py`、`view_formatters.py`
- 新全域設定連結應使用 `/settings`；舊 `/settings/notifications` 只作相容入口
- UI 實作前需先看 `docs/ui_reference/README.md` 與對應圖片；完成後需用瀏覽器截圖或人工檢查對照，避免資訊層級與視覺密度偏離參考
- 飯店圖片不是第二輪 UI 必要項目；沒有穩定資料來源與 fallback 前，不要為了視覺效果假造圖片
- Dashboard 不採資訊過密的完整 hybrid list row；新方向是保留目前清單式可讀性，吸收參考稿的欄位分區與狀態提示
- 首頁刪除操作目前維持直接可見，不收進更多選單，除非使用者後續另外確認

## 7. 建議下一步

1. 對照 `07_watch_detail.png` 重構監視詳情頁，沿用 `WatchDetailPresentation`、fragment contract 與既有 action presentation。
2. 對照 `05_settings_notifications.png` 重構設定頁，沿用 `NotificationChannelSettingsPresentation` 與既有設定保存流程。
3. UI 與架構穩定後做人工 smoke test：啟動、列分頁、建立監視、手動 check、通知測試、暫停 / 恢復。
4. 若 smoke test 穩定，進入 Packaging；若要先做第二站，只做 spike，先驗證 target / candidate contract 是否足夠。

## 8. 仍需觀察

- 長時間背景運作、節流、discard、blocked page 的真機穩定性
- VPN / IP 風控下的使用者操作流程
- 第二站加入前，blocking outcome 是否需要更正式的 control recommendation
- `watch_item` 靜態定義與 control state 是否值得在後續 migration 中拆表
- Watch Detail / Settings 第二輪 UI 是否會需要更正式的 page view model 與 settings presentation contract
- version polling endpoint 的 revision token 是否需要在更多頁面局部更新時抽成共用 read model service
