# UI Redesign Plan

本文件是 GUI 第二輪改版計畫。目標是讓本機 GUI 更接近產品介面，同時不破壞 Chrome-driven workflow。架構邊界看 `docs/ARCHITECTURE_PLAN.md`，進度總表看 `docs/TASK_BREAKDOWN.md`。

## 1. 最新決策

- 飯店圖片先不列為第二輪必要項目；資料來源、快取與 fallback 之後再評估。
- Icon 盡量補強，但不引入大型前端 build system。
- Dashboard 採折衷清單方向：保留目前可讀性，吸收參考稿的欄位分組、掃描節奏與狀態提示，不照抄資訊過滿的 hybrid row。
- 首頁刪除操作維持直接可見，不收進更多選單。
- 每一批改動要能獨立驗證，不做一次性大重寫。
- Watch Detail / Settings 第二輪 UI 必須沿用已完成的 page service、presenter、partial、client contract，不把判斷塞回 route 或大型 partial。
- Watch Detail 已先完成 section registry / fragment assembler / page shell 拆分；第二輪 UI 只調整 presentation 與 partial，不重新發明局部更新 contract。
- 第二輪 UI 新增 layout 時優先使用 `ui_page_sections.py`、`ui_layout.py`、`ui_primitives.py`，避免新的 page-specific inline layout string 繼續擴散。
- Watch Detail / Settings 重構時，stack、cluster、grid、nowrap、form field、details panel、table action cell 等 recurring layout 必須走 `ui_page_sections.py` 或既有 helper；page partial 只保留真正一次性的視覺樣式。

## 2. 參考圖片

參考圖放在 `docs/ui_reference/`：

- `01_add_watch_source.png`：新增監視入口。
- `02_add_watch_chrome_tabs.png`：Chrome 分頁選擇。
- `03_add_watch_confirm.png`：候選方案、通知設定、建立前摘要。
- `04_debug_captures.png`：進階診斷。
- `05_settings_notifications.png`：通知設定。
- `06_dashboard_watch_list.png`：Dashboard / 我的價格監視。
- `07_watch_detail.png`：監視詳情。

使用規則：

- 實作 UI phase 前先看對應參考圖。
- 不要求 pixel-perfect，但資訊層級、視覺密度、主要操作位置不可明顯偏離。
- 若後端資料不足，不假造欄位；使用保守文案、降權顯示或延後實作。
- 完成 UI 改動後，需用瀏覽器截圖或人工檢查對照，確認沒有文字溢出、重疊或過度擁擠。

## 3. 設計原則

- 判讀優先：先顯示系統已整理出的結果，再顯示原始欄位。
- 掃描優先：桌機首頁以清單掃描為主，手機維持卡片節奏。
- 漸進揭露：技術資訊、完整 URL、raw metadata 預設降權或收合。
- 分級操作：主要操作清楚，破壞性操作明確可見。
- 不假造能力：資料來源不存在時，不顯示假價格差異、假通知數或假圖片。
- Renderer 減負：價格判讀、badge 文案、排序與狀態提示集中在 presenter / view model。
- Contract 優先：改 UI 前確認 page view model、fragment payload、DOM hook 與 client script 責任。
- Script entrypoint 優先：頁面互動掛到 page-level script renderer，不從 partial 任意拼接多段 script。

## 4. 範圍邊界

- 不改回 `HTTP-first`。
- 不恢復手動 Seed URL 建立流程。
- 不新增 domain 尚未支援的通知規則或價格條件。
- 不宣稱可自動避開站方風控。
- 不引入 React / Vue / Vite 等前端 build system。
- 不引入大型 chart library；價格趨勢維持輕量 server-rendered SVG / HTML。
- 不為視覺效果修改 watch identity、runtime lifecycle 或資料庫核心契約。

## 5. 目前 UI 狀態

已完成：

- AppShell、sidebar、theme token、可收合 layout。
- Dashboard 折衷清單、summary cards、runtime dock、相對時間前端更新。
- Add Watch 3-step wizard、Chrome tab selection、候選方案、建立前摘要、preview cache、建立後初始價格顯示。
- Watch Detail 第一輪：hero summary、價格摘要、MiniPriceChart、detail fragment polling、收合診斷。
- Settings 第一輪：摘要卡、展開編輯、Discord webhook 遮罩、未儲存提示、離頁防呆。
- Debug 第一輪：摘要卡、capture table、收合 raw metadata / HTML 預覽。
- Watch Detail / Settings 第二輪前的架構 gate：page service、presenter、partial 拆分、client script / DOM contract 集中。
- Watch Detail page shell 與 fragment payload 已共用 `WATCH_DETAIL_FRAGMENT_SECTIONS`，避免 detail UI 重構時散改 DOM id / payload key / JS 更新邏輯。
- Watch fragment payload 組裝已移到 `watch_fragment_payloads.py`；page service 不再直接呼叫 HTML renderer。
- Settings / Watch Detail 已建立 page-level script entrypoint，重複 layout helper 已集中到 `ui_page_sections.py`。

尚未完成：

- Watch Detail 第二輪整頁資訊架構。
- Settings 第二輪通道卡片新版。
- Debug filter / tabs。
- 飯店圖片與完整 icon polish。

## 6. Dashboard 既定方向

Dashboard 已採折衷清單，不再列為下一個主要 UI phase。

桌機 watch row 的資訊分區：

- 左區：飯店名稱、房型 / 方案、日期、人數 / 房數。
- 中區：目前價格、空房狀態、24 小時價格變動。
- 中右區：通知條件、runtime 狀態。
- 右區：最後檢查時間、暫停 / 恢復、刪除。

不做：

- 不顯示 canonical URL、tab id、seed URL 作為主要欄位。
- 不把刪除收進更多選單。
- 不顯示資料不足的假價格差異、假今日通知數或假圖片。

## 7. Phase Plan

### 已完成

- o AppShell / design token / sidebar / runtime dock。
- o Add Watch 3-step wizard、Chrome tab selection、候選方案、建立前摘要。
- o Dashboard 折衷清單、summary cards、卡片 / 清單切換。
- o Web 架構 gate：page service、presenter、fragment contract、page-level script entrypoint、UI helper。
- o runtime / repository 主要責任收斂，避免 UI 重構時回頭處理資料層雙軌問題。

### Phase 5：Watch Detail 第二輪（下一步）

目標：對照 `07_watch_detail.png` 重構監視詳情頁，讓價格、狀態、通知與歷史更容易閱讀。

實作守則：

- 沿用 `WatchDetailPageViewModel`。
- 主要改 detail summary / trend / history partial。
- Detail hero 顯示飯店、房型、日期、人數 / 房數、runtime state、最後檢查。
- 價格摘要、趨勢、歷史、通知摘要需有清楚層級。
- 進階診斷維持收合，不干擾主要價格資訊。
- 暫停 / 恢復 / 刪除 / 立即檢查沿用 action presentation，不混用列表 quick action 與 detail form 行為。

驗證：

- `/watches/{id}/fragments` 與 `/watches/{id}/fragments/version` contract 不變。
- 價格趨勢、檢查歷史、debug artifacts 仍可局部更新。
- control action 不跳錯頁、不失去 origin guard。

### Phase 6：Settings 第二輪

目標：對照 `05_settings_notifications.png`，從大型表單改成摘要 + 通道卡片 + 展開編輯。

實作守則：

- 沿用 `SettingsPageViewModel` 與 `settings_partials.py`。
- 時間顯示、桌面通知、ntfy、Discord 各自成為設定卡片。
- 預設顯示狀態與摘要，展開後才顯示完整欄位。
- Discord webhook 預設遮罩。
- 若後端尚未支援通道級測試，保留目前全通道測試，不新增假按鈕。

驗證：

- 保存設定與測試通知仍走既有流程。
- 未儲存提示與離頁防呆仍正常。

### Phase 7：Debug / Diagnostics 補強

可延後到 Watch Detail / Settings 後。

- 若需要再補 filter / tabs 與 raw diagnostics，但不混入 Dashboard 主要資訊。

### Phase 8：Smoke Test / 下一階段決策

由使用者啟動安全模式 GUI / 專用 Chrome 後測：

- 列分頁、建立 watch、首頁與 detail polling、暫停 / 恢復、手動 check、通知測試。

穩定後再決定 Packaging 或第二站 spike。

## 8. 驗證方式

每批至少執行：

- `.\scripts\uv.ps1 run ruff check src tests`
- 與該頁相關的 unit tests

較大批次完成後執行：

- `.\scripts\uv.ps1 run pytest tests/unit -q`
- 若牽涉 parser：`.\scripts\uv.ps1 run pytest tests/sites -q`
- 若牽涉 SQLite：`.\scripts\uv.ps1 run pytest tests/integration/test_sqlite_repositories.py -q`

需要 GUI 視覺檢查時，遵守 `AGENTS.md`：Codex 不自行啟動 GUI / Chrome，由使用者啟動後才接手檢查。

## 9. 第二輪完成定義

- Add Watch 已完成清楚 3-step wizard。
- Dashboard 已完成折衷清單。
- Watch Detail 已完成第二輪資訊架構。
- Settings 已完成摘要 + 通道卡片 + 展開編輯新版。
- Debug 至少有清楚診斷層級；filter / tabs 可視情況延後。
- 沒有新增後端不支援的 UI 承諾。
- `ruff` 與相關測試通過。
