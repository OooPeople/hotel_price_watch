# UI Redesign Plan

本文件是根目錄 `UI.md` 的工程落地計畫。`UI.md` 保留產品觀察與設計方向；本文件負責把方向收斂成可分批實作、可測試、且不破壞既有 Chrome-driven workflow 的任務。

目前第一輪 UI 已完成 AppShell、共用 UI primitives、Dashboard / Watch Detail / Add Watch / Settings / Debug 的基本產品化。

2026-04-26 決策更新：Dashboard 第二輪中「hybrid list row、單層四段式卡片、刪除收進更多選單、summary cards 改為今日通知 / 最近有變動」的實作已撤回。首頁先維持第一輪版本；後續若要再改 Dashboard，必須先提出設計並確認，不直接實作。

## 1. 改版目標

- 首頁一眼可判斷哪些 watch 有變動、異常、已達目標或值得注意。
- 桌機版首頁預設適合掃描多筆 watch；手機版維持較容易閱讀的卡片節奏。
- 每筆 watch 顯示價格意義：目前價格、與上次差異、與目標價距離、通知或異常狀態。
- 系統資訊保留但降權；Chrome attach、runtime tick、debug artifact 不再主導首頁。
- 設定、runtime state、watch identity、browser attach 與通知 domain contract 不因 UI 改版被重寫。

## 2. 範圍邊界

- 不改回 `HTTP-first`，V1 仍以附著專用 Chrome profile 為正式主線。
- 不恢復手動 Seed URL 建立流程。
- 不新增 domain 尚未支援的通知規則或價格條件。
- 不宣稱可自動避開站方風控；只把 Chrome-driven 限制做適度降權與清楚提示。
- 不引入前端 build system、重型 JavaScript framework 或大型 chart library。
- 不做自動訂房、登入、搶房、點數最佳化或 Windows Service。
- 不為視覺效果修改 watch identity、runtime lifecycle 或資料庫核心契約。

## 3. 設計原則

- 判讀優先：首頁先顯示系統已整理出的結果，再顯示原始欄位。
- 掃描優先：桌機主畫面以 list row 為預設，讓多筆 watch 可快速比較。
- 分級操作：首頁保留既有直接刪除操作；不得未確認就改為收進更多選單。
- 技術降權：系統狀態縮小為摘要或收合區塊，Debug 頁保留完整排錯資訊。
- 不假造能力：如果 UI 需要上一筆有效價格、今日通知數、通道級測試等資料，必須先確認後端 context 可提供。
- Renderer 減負：價格判讀、badge 文案與排序規則集中在 presentation helper 或 view model，不散落在 HTML 字串中。

## 4. Dashboard 後續重構暫緩

### 4.1 已撤回方向

- 不把桌機預設改成清單模式。
- 不把現有 table 清單改成 hybrid list row。
- 不把卡片改成單層四段式。
- 不把刪除收進更多選單。
- 不把 summary cards 改成「最近有變動 / 今日通知次數」作為目前主線。

### 4.2 保留項目

可以保留第一輪已完成且未被否定的項目：

- AppShell、PageHeader、共用 UI primitives。
- Dashboard 現有 summary cards、watch card、table list 切換。
- Watch Detail 的 hero summary、價格摘要與 MiniPriceChart。
- Add Watch、Settings、Debug 的第一輪產品化。

## 5. 需要新增或集中化的判讀欄位

首頁 watch presentation helper 至少要輸出：

- `current_price_text`：目前價格或尚未檢查。
- `price_change_text`：較上次下降 / 上升 / 無變動 / 尚無前次價格。
- `price_change_kind`：success / warning / muted。
- `target_distance_text`：已低於目標價 / 距目標價差多少 / 未設定目標價。
- `target_distance_kind`：success / info / muted。
- `attention_label`：已降價、已漲價、新空房、最近檢查失敗、正常監視中等。
- `attention_kind`：success / warning / danger / info / muted。

第一批可用既有 `check_events` 與 `latest_snapshot` 推導；若資料不足，顯示保守文案，不能假造價格差異或通知結論。

## 6. Phase Plan

### Phase 1：Dashboard 後續重構（暫緩）

目標：暫不進行首頁結構重改。若要重新設計，需要先輸出方案並取得確認。

任務：

- 不實作本文件上一版的 Dashboard 第二輪方案。
- 若只做小修，需維持既有卡片 / 清單結構與刪除直接顯示。
- 任何刪除操作位置調整都必須先確認。

驗證：

- `/fragments/watch-list` polling 仍回傳 summary、runtime 與 watch list HTML。
- fragment 更新後仍套用目前顯示模式。
- 首頁不顯示 canonical URL、tab id、seed URL。
- 價格差異只在有上一筆有效價格時顯示明確差額。
- `ruff`、Dashboard 相關 unit tests 通過。

### Phase 2：Add Watch 流程感補強

目標：新增監視頁更像引導式流程，而不是大型表單。

任務：

- Step 1~4 改成更明確的流程步驟條。
- 建立完成前的 Step 4 顯示飯店、日期、房型、目前價格、通知條件、檢查頻率。
- 桌機版評估加入右側固定 summary。
- 保留 Chrome-driven 建立流程，不恢復 seed URL 主線。

驗證：

- Chrome tab preview、candidate 選擇、已建立 watch 判斷仍正常。
- parser diagnostics 仍在收合區可查。

### Phase 3：Chrome 分頁選擇頁

目標：選分頁時先看飯店與條件，不被長 URL 干擾。

任務：

- 分頁卡優先顯示飯店名稱、日期區間、人數 / 房數、可抓取狀態、是否已建立 watch。
- URL 截斷並降權顯示。
- 若已取得候選方案數，顯示候選摘要。

驗證：

- 不主動刷新或操作 ikyu 分頁。
- 分頁 timeout 與錯誤提示仍可用。

### Phase 4：Settings 第二輪

目標：設定頁從大型表單改成摘要 + 展開編輯。

任務：

- 桌面通知、ntfy、Discord 各自成為通知通道卡片。
- 預設顯示狀態與摘要，展開後才顯示完整設定欄位。
- Discord webhook 預設遮罩，編輯時才輸入完整值。
- 若後端尚未支援通道級測試，仍保留全通道測試，不新增假按鈕。

驗證：

- 保存設定與測試通知仍走既有流程。
- 未儲存提示與離頁防呆仍正常。

### Phase 5：Debug / Diagnostics 補強

目標：進階診斷維持技術導向，但更容易篩選。

任務：

- 增加 filter / tabs：全部、success、failed、blocked、parser issues。
- 保留 debug captures、artifacts、下載 HTML 等既有能力。
- 與主產品共享 badge、table、button style。

驗證：

- 清除 debug capture、詳情頁、HTML 下載功能不變。

### Phase 6：Renderer 拆分

目標：降低 `watch_view_partials.py` 大型 renderer 的維護成本。

任務：

- 補 `WatchRowViewModel`、`WatchCardViewModel`、`WatchDetailHeroViewModel`。
- 拆出 WatchListRow、WatchCard、MiniPriceChart component-level renderer。
- 將價格判讀與 badge 規則集中到 presenter / view model。

驗證：

- 行為不變，snapshot 相關測試與 web tests 通過。
- HTML polling contract 不變。

### Phase 7：Smoke Test / 下一階段決策

目標：用真機流程驗證 UI 與 Chrome-driven workflow 是否一致。

任務：

- 由使用者在一般 PowerShell 啟動安全模式 dev server 與專用 Chrome。
- 從專用 Chrome 分頁建立 watch。
- 檢查首頁 polling、detail polling、暫停 / 恢復、手動 check、通知測試。
- 檢查 Debug 頁是否足夠排錯。

完成後再決定：

- 進入 Packaging。
- 或先做第二站 spike，驗證目前 lodging-room-plan contract 是否足夠。

## 7. 文件與進度同步規則

- 更新本文件時，若有任務已實作，需同步更新 `docs/TASK_BREAKDOWN.md`。
- `docs/TASK_BREAKDOWN.md` 完成項目使用 `- o ...`，未完成項目使用一般 `- ...`。
- `刪除` 目前維持首頁直接顯示；不可在未確認下收進更多選單。

## 8. 驗證方式

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

## 9. 第二輪完成定義

- Dashboard 維持第一輪卡片 / 清單結構。
- 首頁刪除操作維持直接顯示。
- 不保留已撤回的 hybrid list row 與四段式卡片改版。
- 沒有新增後端不支援的 UI 承諾。
- `ruff` 與相關測試通過。
