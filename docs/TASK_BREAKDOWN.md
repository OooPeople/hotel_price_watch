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

- o `ikyu` parser / normalizer / fixture tests。
- o 從專用 Chrome 分頁建立精確 `room-plan` watch。
- o 背景 runtime、scheduler、per-watch 互斥、`check-now`。
- o SQLite persistence：latest snapshot、history、notification state、runtime event、debug artifact。
- o desktop / ntfy / Discord webhook notifier。
- o watch 列表、新增、刪除、詳細、歷史、debug captures、全域設定。
- o watch 啟用 / 停用 / 暫停 / 恢復。
- o 首頁與詳細頁採 version polling；相對時間與退避倒數由前端局部更新。

### 架構收斂

- o app entrypoint、routes、page services、presenters、renderers 已依責任拆分。
- o Watch list / detail fragment payload、DOM contract、client script entrypoint 已集中管理。
- o Watch creation workflow 已接管 preview、cache、create watch 與 initial snapshot orchestration。
- o Dashboard watch row 已拆成 card / table / shared row helper components。
- o Settings、Debug、Add Watch、Watch Detail 主要 renderer 已拆到 page-area modules。
- o Chrome CDP、monitor runtime、check executor 與 scheduler 相關協調器已拆出 owner。
- o Persistence 已拆為 watch item、runtime write、runtime history query、fragment query、notification throttle、app settings 等 owner。
- o `SqliteRuntimeRepository` 已降為 compatibility adapter；正式 app wiring 與 unit tests 使用專用 repository。
- o UI recurring layout pattern 已集中到 `ui_page_sections.py` 與既有 UI helper。
- o 測試已依架構邊界整理；`tests/unit/` 根目錄不再新增 top-level `test_*.py`。

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

1. 對照 `docs/ui_reference/07_watch_detail.png` 重構 Watch Detail 第二輪 UI。
2. 對照 `docs/ui_reference/05_settings_notifications.png` 重構 Settings 第二輪 UI。
3. UI 穩定後做人工 smoke test：啟動、列分頁、建立監視、手動 check、通知測試、暫停 / 恢復。
4. Smoke test 穩定後，再決定 Packaging 或第二站 spike。

## 主要風險

- `ikyu` 真站仍可能對同一出口 IP 做風控。
- 背景監看依賴專用 Chrome session，仍需長時間真機驗證。
- Chrome 縮小、背景、discard 或站方 blocked page 的實際行為仍可能因環境不同而變動。
- 第二站若不是 lodging-room-plan 模型，現有 target / candidate / DB contract 需要 migration。
- `repositories.py` 已降為相容 re-export，`SqliteRuntimeRepository` 已降為 compatibility adapter 且只保留 integration 相容測試；後續新增資料層實作不可加回 façade 或相容層。
- 部分 page-area presenter 仍可能變大；新增 UI 行為前應先拆分對應 component owner。
- Watch Detail / Settings 視覺重構時，仍需避免把 domain 判斷、DOM contract、fragment payload 或 inline script 塞回大型 partial。
