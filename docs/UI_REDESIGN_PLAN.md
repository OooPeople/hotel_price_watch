# UI Redesign Plan

本文件是 GUI 第二輪改版的工程落地計畫。目標不是一次做出完整設計稿，而是把目前可用的本機 GUI 逐步整理成更接近產品介面的狀態，同時不破壞既有 Chrome-driven workflow。

目前第一輪 UI 已完成 AppShell、共用 UI primitives、Dashboard / Watch Detail / Add Watch / Settings / Debug 的基本產品化。2026-04-26 後的新方向是：以參考稿的資訊架構與視覺密度為目標，但採分批、保守、可回退的方式實作。

Dashboard 與 Add Watch 第二輪實作後，已確認單純繼續堆疊 UI 修改會放大 route orchestration、partial renderer、inline script 與 fragment contract 的維護風險。因此已先完成 Watch Detail 與 Settings 第二輪前的 web 架構整理，讓後續頁面重構建立在更穩定的頁面 contract 上。

## 1. 最新決策

- 飯店圖片先不列為第二輪必要項目；圖片資料來源、快取與 fallback 之後再評估。
- Icon 盡量補強，但不為了 icon 引入大型前端 build system。若現有 server-rendered HTML 不適合一次補齊，先使用輕量 SVG / 文字輔助，再排到後續視覺 polish。
- Dashboard 不直接照參考稿做成資訊很滿的 hybrid list row。上次第二輪清單改版效果不理想，新的方向是保留目前清單式可讀性，吸收參考稿的欄位分組、掃描節奏與狀態提示，做成折衷版。
- 首頁刪除操作目前維持直接可見，不收進更多選單，除非後續另外確認。
- 每一批改動都要能獨立驗證；不做一次性大重寫。
- 進入 Watch Detail 與 Settings 第二輪前，先暫停純視覺改版，優先整理 watch partial、client script、fragment payload 與 watch creation 初始 snapshot persistence。

## 1.1 目前實作對齊

本段用來避免文件把「已有雛形」誤寫成「整頁重構完成」：

- 已完成：AppShell / theme token / Dashboard 折衷清單 / Add Watch 3-step wizard / version polling / 首頁相對時間與退避倒數前端局部更新。
- 已有第一輪但仍待第二輪：Watch Detail 已有 hero、價格摘要、MiniPriceChart、detail fragment polling 與收合診斷；尚未依 `07_watch_detail.png` 重新整理整頁資訊架構。
- 已有第一輪但仍待第二輪：Settings 已有摘要卡、展開編輯、webhook 遮罩與未儲存提示；尚未依 `05_settings_notifications.png` 改成通道卡片 + 底部保存列的完整新版。
- 已完成主要架構整理：watch creation 初始價格保存已移到 application service 並走單一 transaction；watch list / detail client scripts 已抽出到 `watch_client_scripts.py`；list / detail / action HTML renderer 已搬到對應 partial 模組。
- 已完成主要架構整理：watch list / detail fragment payload 與 DOM hook contract 已集中到 `watch_fragment_contracts.py`，route、renderer、client script 與測試共用同一組 key / id 定義。
- 已完成主要架構整理：`WatchDetailPresentation` 與 `NotificationChannelSettingsPresentation` 已建立，Detail / Settings renderer 不再直接承擔首屏摘要與通道摘要的主要判讀。
- UI 重構前剩餘工作：可開始對照 `07_watch_detail.png` 與 `05_settings_notifications.png` 做視覺與資訊架構改版，過程中需沿用既有 presenter / fragment contract。

## 2. 參考圖片

參考圖放在 `docs/ui_reference/`，是第二輪 UI 實作時的主要視覺對照來源：

- `01_add_watch_source.png`：新增監視 Step 1，包含 AppShell、步驟條、來源選擇與開始前提醒。
- `02_add_watch_chrome_tabs.png`：新增監視 Step 1 的 Chrome 分頁選擇子頁，包含可附著分頁列表、可抓取 / 已建立 / 不可抓取狀態與右側選擇說明。
- `03_add_watch_confirm.png`：新增監視後續設定頁，包含候選方案、通知設定、建立前確認與右側摘要。
- `04_debug_captures.png`：進階診斷頁，包含摘要卡、狀態篩選、capture table 與主要操作。
- `05_settings_notifications.png`：通知設定頁，包含設定摘要卡、通道列、展開編輯區與底部保存列。
- `06_dashboard_watch_list.png`：Dashboard / 我的價格監視，包含摘要卡、折衷清單列、系統狀態與 AppShell。
- `07_watch_detail.png`：監視詳情頁，包含 detail hero、價格趨勢、價格變動紀錄與右側監視通知設定摘要。

使用規則：

- 實作任何 UI phase 前，先開啟對應參考圖確認資訊架構、視覺密度、spacing 與主要操作位置。
- 新增監視三張圖視為同一條流程的分段參考：`01` 是入口說明、`02` 是 Step 1 的 Chrome 分頁列表、`03` 是後續設定與確認。
- 新增監視流程若遇到參考圖細節不一致，以目前 3-step top wizard、現有專案文案與本文件的流程定義為準；確認建立作為 Step 3 內的完成區，不再放在上方流程條。
- 參考圖不要求 pixel-perfect，但完成後的頁面不可明顯偏離參考圖的資訊層級與操作節奏。
- 若目前後端資料不足，不可假造參考圖中的欄位；應使用保守文案、降權顯示或延後實作。
- 完成頁面改動後，應以瀏覽器截圖或人工檢查對照參考圖，確認沒有文字溢出、重疊或過度擁擠。

## 3. 改版目標

- 首頁一眼可判斷哪些 watch 有變動、異常、已達目標或值得注意。
- 桌機版首頁適合掃描多筆 watch；手機版維持容易閱讀的卡片節奏。
- 每筆 watch 顯示價格意義：目前價格、24 小時內價格變動、通知條件與 runtime 狀態。
- 新增監視流程更像引導式 wizard，而不是大型表單堆疊。
- Settings 與 Debug 頁面更接近工具型產品介面：摘要清楚、進階內容可展開、技術資訊有層級。
- 系統資訊保留但降權；Chrome attach、runtime tick、debug artifact 不再主導首頁。
- 設定、runtime state、watch identity、browser attach 與通知 domain contract 不因 UI 改版被重寫。

## 4. 範圍邊界

- 不改回 `HTTP-first`，V1 仍以附著專用 Chrome profile 為正式主線。
- 不恢復手動 Seed URL 建立流程。
- 不新增 domain 尚未支援的通知規則或價格條件。
- 不宣稱可自動避開站方風控；只把 Chrome-driven 限制作適度降權與清楚提示。
- 不引入 React / Vue / Vite 等前端 build system，除非後續有明確互動需求。
- 不引入大型 chart library；價格趨勢維持輕量 server-rendered SVG / HTML。
- 不做自動訂房、登入、搶房、點數最佳化或 Windows Service。
- 不為視覺效果修改 watch identity、runtime lifecycle 或資料庫核心契約。

## 5. 設計原則

- 判讀優先：首頁先顯示系統已整理出的結果，再顯示原始欄位。
- 掃描優先：桌機首頁以清單掃描為主，但避免單列塞入過多資訊。
- 漸進揭露：常用資訊直接顯示，診斷資料、完整 URL、raw metadata 預設降權或收合。
- 分級操作：主要操作清楚，破壞性操作保持明確且不隱藏到難以發現的位置。
- 不假造能力：如果 UI 需要上一筆有效價格、今日通知數、通道級測試等資料，必須先確認後端 context 可提供。
- Renderer 減負：價格判讀、badge 文案與排序規則集中在 presenter 或 view model，不散落在 HTML 字串中。
- 視覺一致：新的卡片、表格、按鈕、badge、icon 與 spacing 優先回到 `ui_styles.py` 與 `ui_components.py`。
- Contract 優先：改 UI 前先確認 page view model、fragment payload、DOM hook 與 client script 責任；不要在大型 partial 中同時改資料語意、HTML 與 JS。

## 6. Dashboard 折衷方向

Dashboard 不採參考稿中資訊量很高的完整 hybrid row，也不回到純技術表格。目標是保留目前清單式的易讀結構，加入參考稿中較清楚的資訊分區。

### 6.1 桌機版 watch row 建議結構

每筆 watch 使用單層 row / card，不在卡片內再放卡片：

- 左區：飯店名稱、房型 / 方案、日期、人數 / 房數。
- 中區：目前價格、空房狀態、價格變動。
- 中右區：通知條件、狀態。
- 右區：最後檢查時間、查看詳情、暫停 / 恢復、刪除。

圖片區先不做必要欄位。若未來加入圖片，必須有穩定 fallback，且不影響沒有圖片時的掃描效率。

### 6.2 Dashboard 不做的項目

- 不把所有資料塞進一列造成閱讀負擔。
- 不把刪除操作收進更多選單。
- 不把首頁主要資訊改成 debug / URL 導向。
- 不顯示 canonical URL、tab id、seed URL 作為主要欄位。
- 不在資料不足時顯示假價格差異、假今日通知數或假圖片。

## 7. 需要新增或集中化的判讀欄位

首頁 watch presentation helper 至少要輸出：

- `current_price_text`：目前價格或尚未檢查。
- `price_change_text`：24 小時內下降 / 上升 / 無變動 / 尚無前次價格。
- `price_change_kind`：success / warning / muted。
- `attention_label`：已降價、已漲價、新空房、最近檢查失敗、正常監視中等。
- `attention_kind`：success / warning / danger / info / muted。
- `runtime_state_helper_text`：退避中、恢復確認中、暫停等狀態的下一步提示。
- `last_checked_relative_text`：最後檢查相對時間，前端可自行更新。

第一批可用既有 `price_history`、`check_events` 與 `latest_snapshot` 推導；若資料不足，顯示保守文案，不能假造價格差異或通知結論。首頁先不顯示接近目標價，避免欄位過密。

## 8. Phase Plan

### Phase 1：Design Token / AppShell 對齊（已完成）

目標：先把整體視覺基底往參考稿靠近，降低後續每頁重複微調成本。

任務：

- 調整 `ui_styles.py` 的背景、surface、border、shadow、radius、typography token。
- Sidebar 導覽補齊產品名稱、主要頁面導覽與收合狀態；專用 Chrome / runtime 狀態統一放在首頁系統狀態 dock，不再放側邊欄。
- Icon 先採輕量 helper；若 icon 品質或維護成本不理想，再列入後續 polish。
- 保持 mobile / narrow viewport 可用，不讓 sidebar 擋住主要內容。

驗證：

- AppShell 相關 unit tests 通過。
- Dashboard、Add Watch、Settings、Debug 首屏沒有明顯重疊或文字溢出。

### Phase 2：Add Watch Wizard（已完成主要流程）

目標：新增監視頁更像引導式流程，優先接近參考稿的資訊架構，但上方流程收斂為 3 步，避免分頁選擇與 preview 頁出現跳步感。

任務：

- 上方流程條使用 3 步：選擇來源、選擇方案、設定通知與確認。
- Step 1 強調「從專用 Chrome 選擇 IKYU 頁面」，並保留安全提醒。
- Step 2 候選方案使用更清楚的 selectable option，但避免過度裝飾。
- Step 3 通知條件與檢查頻率改成緊湊、可掃描的設定區。
- 建立前確認顯示飯店、日期、房型、目前價格、通知條件、檢查頻率，但不作為獨立上方步驟。
- 建立 watch 後，需把剛剛 preview 已抓到的候選價格寫入 latest snapshot / check event / price history，避免首頁顯示「尚未檢查」。
- 桌機版可加入右側 summary；手機版 summary 改為正常內容流。
- 保留 Chrome-driven 建立流程，不恢復 seed URL 主線。

驗證：

- Chrome tab preview、candidate 選擇、已建立 watch 判斷仍正常。
- parser diagnostics 仍在收合區可查。
- 不主動刷新或操作 ikyu 分頁。

### Phase 3：Dashboard 折衷清單（已完成目前折衷版）

目標：保留目前清單式可讀性，吸收參考稿的欄位分區與狀態提示。

任務：

- 已補 `WatchRowPresentation` 集中 row / card 需要的價格、24 小時價格變動、通知與狀態文案；後續若再擴大首頁資料，可收斂為 `DashboardPageViewModel`。
- 桌機版建立折衷 watch row：資訊分區清楚，但單列不要過度密集。
- 手機版維持卡片式閱讀，不強迫套用桌機 row。
- Summary cards 可以保留現有版本；若改成「最近有變動 / 今日通知」，必須先確認後端資料來源。
- 刪除操作維持直接顯示。

驗證：

- `/fragments/watch-list` 與 `/fragments/watch-list/version` contract 仍正常。
- fragment 更新後仍保留使用者顯示模式或預設行為。
- 首頁不顯示 canonical URL、tab id、seed URL。
- 價格差異只在有上一筆有效價格時顯示明確差額。
- Dashboard 相關 unit tests 通過。

### Phase 4：Web 架構整理 Gate（已完成）

目標：吸收 Dashboard 重構與 review 的結論，在進入 Watch Detail / Settings 視覺改版前，先降低 web 層維護風險。

任務：

- 將 watch list / detail 的 client-side script 從 `watch_view_partials.py` 抽出到集中模組，至少包含 version polling、relative time updater、runtime dock collapse 與 list view mode persistence。
- 將 `watch_view_partials.py` 依頁面責任拆分，優先拆成 watch list partial 與 watch detail partial；拆分時不改視覺與行為。
- 建立 Watch Detail 的 page view model / presenter，先集中 hero、目前價格、通知摘要、runtime state helper 與價格趨勢所需文案。
- 建立 Settings 的 channel presentation，集中摘要卡、啟用狀態、遮罩文案與展開編輯所需資訊。
- 把 watch creation 初始價格保存移出 route，改為 application use case，並以單一 transaction 寫入 latest snapshot、check event、price history。
- 保持第二站 target / candidate contract 暫緩策略；不要為了這輪 UI 架構整理提前 payload 化。

目前進度：

- 已完成：watch creation 初始 snapshot persistence 移入 `WatchCreationSnapshotService`，repository 提供單一 transaction 寫入。
- 已完成：watch list / detail version polling 與相對時間更新抽出到 `watch_client_scripts.py`。
- 已完成：`watch_list_partials.py`、`watch_detail_partials.py`、`watch_action_partials.py` 已成為頁面責任實作入口；`watch_view_partials.py` 只保留相容匯出。
- 已完成：watch list / detail fragment payload 與 DOM hook contract 集中到 `watch_fragment_contracts.py`，避免 route、renderer、client script 各自硬寫 key / id。
- 已完成：`WatchDetailPresentation` 已集中 Detail hero、目前價格、空房、通知摘要、runtime state 與技術資訊需要的基礎資料。
- 已完成：`NotificationChannelSettingsPresentation` 已集中全域設定摘要卡、啟用狀態、表單回填與敏感值遮罩。
- 下一步：開始 Phase 5 Watch Detail 第二輪 UI，對照 `07_watch_detail.png` 重構資訊架構。

驗證：

- 不改 GUI 視覺結果時，現有 web route / renderer 測試仍通過。
- watch list / detail version polling contract 不變。
- 建立監視後首頁仍可直接顯示 preview 初始價格，不回到「尚未檢查」。

### Phase 5：Watch Detail 第二輪（下一步）

目標：在 page contract 穩定後，對照 `07_watch_detail.png` 重構監視詳情頁，讓價格、狀態、通知與歷史更容易閱讀。

任務：

- Detail hero 顯示飯店、房型、日期、人數 / 房數、目前 runtime state 與最後檢查。
- 價格摘要與主要 hero 文案使用 `WatchDetailPresentation` 提供的資料，不直接在 partial 中判讀 domain entity。
- 通知設定摘要可放在右側或高權重區，但不重複塞滿所有 debug 欄位。
- 進階診斷維持收合，debug artifacts 與 runtime state events 不干擾主要價格資訊。
- 操作按鈕沿用 action presentation；列表 quick action 與 detail form 行為不可混用。

驗證：

- `/watches/{id}/fragments` 與 `/watches/{id}/fragments/version` contract 不變。
- 價格趨勢、檢查歷史、debug artifacts 仍能局部更新。
- 暫停 / 恢復 / 刪除 / 立即檢查不因 detail UI 重構而跳錯頁或失去 origin guard。

### Phase 6：Settings 第二輪（待 Watch Detail 後實作）

目標：設定頁從大型表單改成摘要 + 展開編輯。

任務：

- 時間顯示、桌面通知、ntfy、Discord 各自成為設定卡片。
- 預設顯示狀態與摘要，展開後才顯示完整設定欄位。
- Discord webhook 預設遮罩，編輯時才輸入完整值。
- 若後端尚未支援通道級測試，仍保留全通道測試，不新增假按鈕。

驗證：

- 保存設定與測試通知仍走既有流程。
- 未儲存提示與離頁防呆仍正常。

### Phase 7：Debug / Diagnostics 補強

目標：進階診斷維持技術導向，但更容易篩選。

任務：

- 增加 filter / tabs：全部、success、failed、blocked、parser issues。
- 保留 debug captures、artifacts、下載 HTML 等既有能力。
- 與主產品共享 badge、table、button style。
- 技術欄位密度可以高，但要避免和 Dashboard 的產品資訊混在一起。

驗證：

- 清除 debug capture、詳情頁、HTML 下載功能不變。

### Phase 8：UI 基礎設施拆分與 Polish

目標：在主要頁面 contract 穩定後，降低 UI 基礎設施長期維護成本，並補視覺細節。

任務：

- 視情況把 `ui_components.py` 拆成 layout、primitives、icons、behaviors。
- 視後續複雜度補 `DashboardPageViewModel`；Detail 與 Settings 已先有 `WatchDetailPresentation` 與 `NotificationChannelSettingsPresentation` 作為頁面 contract。
- 拆出 WatchListRow、WatchCard、MiniPriceChart 等 component-level renderer。
- 視情況補 icon helper、空狀態插圖、飯店圖片 fallback，但不作為前面 phases 的阻塞項。

驗證：

- 行為不變，snapshot 相關測試與 web tests 通過。
- HTML polling contract 不變。

### Phase 9：Smoke Test / 下一階段決策

目標：用真機流程驗證 UI 與 Chrome-driven workflow 是否一致。

任務：

- 由使用者在一般 PowerShell 啟動安全模式 dev server 與專用 Chrome。
- 從專用 Chrome 分頁建立 watch。
- 檢查首頁 polling、detail polling、暫停 / 恢復、手動 check、通知測試。
- 檢查 Debug 頁是否足夠排錯。

完成後再決定：

- 進入 Packaging。
- 或先做第二站 spike，驗證目前 lodging-room-plan contract 是否足夠。

## 9. 文件與進度同步規則

- 更新本文件時，若有任務已實作，需同步更新 `docs/TASK_BREAKDOWN.md`。
- `docs/TASK_BREAKDOWN.md` 完成項目使用 `- o ...`，未完成項目使用一般 `- ...`。
- 若 Dashboard 方向再變更，需同步更新本文件、`TASK_BREAKDOWN.md` 與 `HANDOFF_PLAN.md`。

## 10. 驗證方式

每個實作批次至少執行：

- `.\scripts\uv.ps1 run ruff check src tests`
- 與該頁相關的 unit tests

較大批次完成後執行：

- `.\scripts\uv.ps1 run pytest`

若新增 UI helper，需補 unit test 檢查：

- 主要文案存在。
- 技術資訊已降權或收合。
- 既有 route / form action 沒有改壞。
- fragment endpoint 回傳仍符合前端 polling 需求。

## 11. 第二輪完成定義

- Add Watch 已呈現清楚 3-step top wizard，且建立前確認與右側摘要不造成跳步感。
- Dashboard 已採折衷清單：資訊分區清楚，但不過度密集。
- Watch Detail / Settings 第二輪前已完成 web 架構整理 gate，watch partial、client script 與 route persistence 責任不再繼續膨脹。
- Settings 第二輪已完成摘要 + 展開編輯的新版資訊架構。
- Debug 已有基本 filter / tabs 與更清楚的診斷層級。
- 圖片不是完成條件；icon 至少有一致策略，未完成項目列入後續 polish。
- 沒有新增後端不支援的 UI 承諾。
- `ruff` 與相關測試通過。
