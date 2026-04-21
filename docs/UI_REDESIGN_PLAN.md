# UI Redesign Plan

本文件是後續 UI 改版的正式工程計畫。根目錄 `UI.md` 保留為產品願景與設計方向，本文件負責把願景收斂成可分階段實作、可驗證、且不破壞既有 Chrome-driven workflow 的任務。

## 1. 改版目標

- 將目前偏工程工具的本機 GUI，重構為面向一般使用者的價格監視產品介面。
- 首屏優先呈現價格、狀態、異動與通知結果。
- Debug、runtime、parser、artifact、canonical URL 等技術資訊保留，但降權到進階區塊或 Debug 頁。
- 保留既有後端契約、routes 與資料模型，第一輪不引入前端 build system 或重型 JavaScript framework。

## 2. 不在第一輪處理的範圍

- 不改回 `HTTP-first`，UI 仍以附著專用 Chrome profile 為正式主線。
- 不恢復手動 Seed URL 建立流程。
- 不新增尚未有 domain support 的通知條件。
- 不在第一輪做每個通知通道的獨立測試 API；目前測試通知仍走正式 dispatcher，測所有已啟用通道。
- 不引入大型 chart library；價格趨勢先使用輕量 HTML / SVG / CSS 呈現。
- 不做完整漢堡選單系統；第一輪先讓桌機與窄版自然可用。
- 不為 UI 改版修改 watch identity、runtime lifecycle 或資料庫核心契約。

## 3. 設計原則

- 產品資訊優先：飯店、房型、日期、目前價格、價格變動、監視狀態、通知狀態。
- 系統資訊降權：Chrome attach、runtime tick、parser diagnostics、debug captures、artifacts。
- 文字人話化：避免 raw enum 或工程術語直接暴露在主流程。
- 操作分級：主要 CTA 明確，危險操作收斂，不與主要操作同等醒目。
- 元件先行：頁面改版前先補足 presentation helpers 與 UI primitives，避免 renderer 堆疊業務判斷。

## 4. UI Presentation Layer

第一階段需先建立或整理 UI 專用的 presentation helpers，避免各 renderer 直接散落 domain 判斷。

### 必要 helper

- 狀態文案 mapping：例如 `checked` 顯示為 `已檢查`，`not_requested` 顯示為 `本次未通知`。
- badge kind mapping：watch 狀態、availability、通知結果、錯誤狀態要有一致顏色語意。
- 價格顯示 helper：目前價格、無價格、幣別、價格差異。
- 時間顯示 helper：沿用設定頁的 12 / 24 小時制偏好。
- watch summary view model：整理 card / hero summary 所需資料，避免 template 直接查多個 runtime object。

### 邊界

- presentation helper 只能做顯示轉換與排序輔助，不應改變 domain decision。
- 若某個 UI 需求需要新的 domain 狀態，先補 domain / application 測試，再接 UI。

## 5. Design System 第一輪

在 `src/app/web/ui_styles.py`、`src/app/web/ui_components.py`、`src/app/web/view_formatters.py` 基礎上擴充，不建立新的正式入口取代它們。

### 需要新增或強化的元件

- AppShell：全站頁面框架與主要導覽。
- PageHeader：頁面標題、副標、主要 CTA。
- SectionHeader：區塊標題與輔助文字。
- SummaryCard：首頁與 detail 的摘要數字卡。
- StatusBadge：統一狀態顯示。
- WatchCard：watch 列表核心元件。
- PriceChangeLabel：價格變化顯示。
- KeyValueGrid / InfoRow：hero summary 與設定摘要。
- CollapsibleSection：進階診斷與 debug 收合區。
- FormSection：設定頁與新增 watch 的表單區塊。
- MoreActions：第一輪可用 `<details>` / `<summary>` 實作，不做複雜 JS menu。
- MiniPriceChart：第一輪只做輕量容器或簡單 sparkline。

## 6. 頁面改版順序

### Phase 1：Dashboard / Watch List

目標：首頁一打開就能看懂哪些 watch 需要注意。

任務：

- 建立 AppShell 與 PageHeader。
- 加入 summary cards：啟用中監視、最近價格異動、最近同步、通知狀態。
- 將 Background Monitor 狀態降權為小型系統摘要。
- 以 WatchCard 取代傳統表格主視覺。
- 排序規則先明確化：最近已通知或價格下降、異常、最近價格變動、其他正常項目。
- 首頁主要 CTA 使用 `新增監視`。

驗證：

- 既有 watch list fragment polling 仍正常。
- Debug / runtime 資訊不再主導首屏。
- `tab_id`、canonical URL、seed URL 不出現在 watch card 主資訊。

### Phase 2：Watch Detail

目標：進入 detail 後立即知道此 watch 監視什麼、目前多少錢、狀態是否正常。

任務：

- 建立 hero summary：飯店、房型、方案、日期、人數房數、目前價格、availability、最後檢查時間。
- 建立價格摘要卡：目前價格、價格差異、連續失敗、通知條件。
- 保留歷史表格，但使用人話化欄位與 event 文案。
- 加入 MiniPriceChart 容器或輕量 sparkline。
- Debug artifacts、runtime state events、technical details 移入預設收合的進階診斷。

驗證：

- detail fragment polling 仍正常。
- 暫停、恢復、停用、刪除、立即檢查仍使用既有 routes。
- 技術資訊可展開查看，但不干擾主流程。

### Phase 3：Add Watch

目標：讓建立 watch 像建立價格提醒，而不是填工程表單。

任務：

- 保持單頁，不改 routes。
- 分成四個步驟區塊：選擇來源、選擇方案、設定通知、確認建立。
- Chrome tab selection 使用產品化卡片。
- candidate 選項改為 selectable cards。
- `輪詢秒數` 改為 `檢查頻率`。
- `建立 Watch Item` 改為 `開始監視價格`。
- 診斷資訊移到預設收合的抓取詳情。

驗證：

- 已建立 watch 的分頁仍在進入 preview 前標示不可重複建立。
- 不恢復 Seed URL input。
- candidate parser diagnostics 仍可在展開區看到。

### Phase 4：Settings

目標：集中管理設定，避免設定頁變成一整頁裸露 input。

任務：

- 主入口名稱維持 `設定`，不要改回 `通知設定`。
- 設定頁分區：顯示偏好、通知通道、測試通知。
- 通知通道用摘要卡呈現，展開後才編輯。
- Discord webhook URL 等敏感資訊在摘要中遮罩。
- 保留既有未儲存提示與離頁前防呆。

延後：

- 個別通道測試需要 application/service API 支援，列為後續功能，不混入第一輪 UI 改版。

驗證：

- `/settings` 是正式入口。
- `/settings/notifications` 只保留相容 redirect / alias 語意。
- 保存設定與測試通知仍走既有後端流程。

### Phase 5：Debug / Diagnostics

目標：Debug 頁與主產品共享 design system，但定位為進階工具。

任務：

- 頁首標示為進階診斷。
- Debug captures / artifacts 保留表格，但改善欄位命名與可讀性。
- 增加返回 Dashboard 的明確入口。
- 與主產品頁共享 card、table、badge、button style。

驗證：

- Debug capture list / detail / html download 仍可用。
- 清除 debug capture 功能不變。

## 7. 文案替換規則

第一輪可直接替換：

- `輪詢秒數` -> `檢查頻率`
- `建立 Watch Item` -> `開始監視價格`
- `checked` -> `已檢查`
- `price_changed` -> `價格變動`
- `not_requested` -> `本次未通知`
- `capture` -> `抓取結果` 或 `擷取紀錄`
- `debug artifact` -> `診斷檔案`

不可直接新增承諾：

- 不顯示尚未實作的通知規則。
- 不宣稱程式能自動避開站方風控。
- 不把 Chrome-driven 限制完全隱藏；只做降權與清楚說明。

## 8. 驗證方式

每個 phase 完成後至少執行：

- `.\scripts\uv.ps1 run ruff check src tests`
- 與該頁相關的 unit tests
- 全量 `.\scripts\uv.ps1 run pytest`

若新增 UI helper，需補 unit test 檢查：

- 主要文案存在
- 技術資訊降權或收合
- 既有 route / form action 沒有改壞
- fragment endpoint 回傳仍符合前端 polling 需求

## 9. 完成定義

第一輪 UI 改版完成時，應符合：

- Dashboard 首屏以 watch 狀態與價格為主，不以 runtime debug 為主。
- Watch Detail 首屏可看懂監視目標、價格、通知條件與狀態。
- Add Watch 流程具步驟感，且不需要手動 Seed URL。
- Settings 是集中式設定入口，通知通道與顯示偏好清楚分區。
- Debug 可用但降權。
- 沒有新增後端不支援的 UI 承諾。
- `ruff` 與全量 `pytest` 通過。
