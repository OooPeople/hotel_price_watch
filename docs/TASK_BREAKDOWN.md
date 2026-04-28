# Task Breakdown

本文件只記錄目前進度、下一步與主要風險。長期架構邊界看 `docs/ARCHITECTURE_PLAN.md`，UI phase 看 `docs/UI_REDESIGN_PLAN.md`，新對話接手看 `docs/HANDOFF_PLAN.md`。

完成項目以 `- o ...` 標示；未完成或延後項目使用一般清單。

## 目前總結

- o V1 正式主線已收斂為「專用 Chrome profile + CDP attach」。
- o `ikyu` watch 建立、背景輪詢、歷史、debug、通知與控制操作已可實際使用。
- o Dashboard 與 Add Watch 第二輪主要流程已落地。
- o Watch Detail / Settings 已完成第二輪 UI 前的架構 gate，但視覺與資訊架構仍待重構。
- o 最近一次驗證通過 `ruff check`、`pytest tests/unit -q`、`pytest tests/sites -q`、`pytest tests/integration/test_sqlite_repositories.py -q`。

## 已完成

### V1 功能

- o parser / normalizer / fixture-based parser tests。
- o `seed_url -> search_draft -> watch_target` 與精確 `room-plan` identity。
- o scheduler、runtime、per-watch 互斥、`check-now`。
- o SQLite schema、migration、WAL、busy timeout。
- o latest snapshot、check event、price history、notification state、runtime state event、debug artifact persistence。
- o desktop / ntfy / Discord webhook notifier。
- o watch 列表、新增、刪除、詳細頁、歷史、debug captures、全域設定。
- o watch 啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查。
- o 首頁與 watch 詳細頁採 version polling；相對時間與退避倒數由前端局部更新。

### 架構收斂

- o `main.py` 已收斂為 app factory、lifespan、container 掛載、router include 與 health endpoint。
- o web routes 已拆到 `src/app/web/routes/`。
- o route orchestration 已抽 page service：`WatchPageService`、`WatchCreationPageService`、`SettingsPageService`。
- o web renderer 已依頁面群組拆分，`app.web.views` 只保留相容 re-export。
- o watch list / detail / action / creation / settings / debug 的主要 renderer 已拆到對應 partial / view module。
- o `ui_layout.py`、`ui_primitives.py`、`ui_icons.py`、`ui_behaviors.py` 已拆出；`ui_components.py` 只作相容 re-export。
- o watch list / detail fragment payload 與 DOM hook 已集中到 `watch_fragment_contracts.py`。
- o settings / watch creation DOM id 與 inline behavior 已集中到 `client_contracts.py` 與 dedicated client script renderer。
- o Dashboard、Watch Detail、Settings、Debug capture 已建立 page view model / presenter gate。
- o Watch creation preview cache 與初始價格保存已移到 application service；初始 snapshot 以單一 transaction 寫入。
- o `watch_client_scripts.py` 已拆成 watch list / watch detail client script renderer，原檔只保留相容 re-export。
- o `watch_creation_routes.py` 已抽出 `WatchCreationWorkflow`，route 不再直接協調 preview guard、cache、create watch 與初始 snapshot。
- o `settings_partials.py` 已拆成 global / rule / test partial modules，原檔只保留相容 re-export。
- o `watch_list_partials.py` 已拆出 runtime dock / summary card modules；`watch_creation_partials.py` 已拆出 Chrome tab / diagnostics modules。
- o `ChromeCdpHtmlFetcher` 已拆出 profile launcher、CDP connector、page matcher、page capture helper 與 chrome models。
- o `ChromeDrivenMonitorRuntime` 已抽出 check executor、startup restorer、assignment coordinator、notification dispatch coordinator、watch definition sync coordinator。
- o `WatchCheckExecutor` 已加入 setup / captured / evaluated pipeline context，先收斂單次 check 的資料流但不大拆流程。
- o `SqliteRuntimeRepository` 已加上 write / history query / fragment query façade；runtime write façade 已直接持有 database，不再委派相容 repository。
- o 資料層第二輪第一刀已完成：SQLite serializer、revision token helper、watch item row mapping 已從 `repositories.py` 抽到 dedicated modules。
- o 資料層第二輪第二刀已完成：runtime history query SQL 與 row mapping 已抽到 `runtime_history_queries.py`，history façade 不再委派相容 repository。
- o 資料層第二輪第三刀已完成：runtime fragment revision query 與 notification throttle state SQL 已抽到 dedicated modules。
- o 資料層第二輪第四刀已完成：watch item repository、runtime repository façade、runtime write records、app settings repository 已拆出，`repositories.py` 降為相容 re-export。
- o 測試已依架構邊界整理到 `tests/unit/*/` 子目錄；`tests/unit/` 根目錄不再新增 top-level `test_*.py`。

### UI 進度

- o AppShell、theme token、sidebar 收合、底部 runtime dock 已完成目前版本。
- o Dashboard 已完成折衷清單方向：summary cards、清單 / 卡片切換、價格、24 小時變動、通知條件、狀態、最後檢查。
- o Add Watch 已完成 3-step wizard、Chrome tab selection、候選方案、建立前摘要、preview cache 與建立後初始價格顯示。
- o Watch Detail 已有第一輪產品化：hero summary、價格摘要、MiniPriceChart、detail fragment polling、收合診斷。
- o Settings 已有第一輪產品化：摘要卡、展開編輯、Discord webhook 遮罩、未儲存提示與離頁防呆。
- o Debug 已有第一輪產品化：摘要卡、capture table、收合 raw metadata / HTML 預覽。
- o UI 參考圖已整理到 `docs/ui_reference/`。

## 目前不做

- `watch_control_states` table：只保留 future migration plan，等 control state 需求增加再做。
- 飯店圖片：資料來源、快取與 fallback 未定，第二輪 UI 不把圖片列為完成條件。
- 第二站：需先選定具體站點樣本，再判斷 lodging-room-plan contract 是否足夠。
- Packaging：等 UI 與真機 smoke test 穩定後再進。
- Windows Service、自動訂房、登入、搶房、點數最佳化。

## 下一步

1. 做 `web/` 第二輪 page-area 檢查：重點觀察 Watch Detail / Settings 第二輪 UI 會碰到的 presenter 是否需要再拆。
2. 若資料層後續繼續成長，優先改直接 import dedicated repository module；目前不改 schema 與 public behavior。
3. 對照 `docs/ui_reference/07_watch_detail.png` 重構 Watch Detail 第二輪 UI，沿用 `WatchDetailPageViewModel` 與拆分後的 detail partial。
4. 對照 `docs/ui_reference/05_settings_notifications.png` 重構 Settings 第二輪 UI，沿用 `SettingsPageViewModel` 與 `settings_partials.py`。
5. UI 與架構穩定後做人工 smoke test：啟動、列分頁、建立監視、手動 check、通知測試、暫停 / 恢復。
6. Smoke test 穩定後，再決定進入 Packaging 或第二站 spike。

## 主要風險

- `ikyu` 真站仍可能對同一出口 IP 做風控。
- 背景監看依賴專用 Chrome session，仍需長時間真機驗證。
- Chrome 縮小、背景、discard 或站方 blocked page 的實際行為仍可能因環境不同而變動。
- 第二站若不是 lodging-room-plan 模型，現有 target / candidate / DB contract 需要 migration。
- `repositories.py` 已降為相容 re-export；後續新增資料層實作不可加回此檔。
- 部分 page-area presenter 仍可能變大；新增 UI 行為前應先拆分對應 component owner。
- Watch Detail / Settings 視覺重構時，仍需避免把 domain 判斷、DOM contract 或 inline script 塞回大型 partial。
