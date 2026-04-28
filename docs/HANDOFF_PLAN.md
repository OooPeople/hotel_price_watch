# Handoff Plan

本文件給新對話快速接手。先讀：

1. `docs/ARCHITECTURE_PLAN.md`
2. `docs/TASK_BREAKDOWN.md`
3. `docs/UI_REDESIGN_PLAN.md`
4. `docs/HANDOFF_PLAN.md`

## 1. 目前狀態

專案目前可實際使用：

- 專用 Chrome profile + CDP attach。
- 從專用 Chrome 分頁建立 `ikyu` watch。
- watch 列表、詳情、歷史、debug、全域設定。
- watch 啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查。
- desktop / ntfy / Discord 通知。
- background runtime 定期刷新、寫入歷史並發送通知。
- 首頁與詳細頁採 version polling；相對時間與退避倒數由前端局部更新。

最近驗證：

- `.\scripts\uv.ps1 run ruff check src tests`
- `.\scripts\uv.ps1 run pytest tests/unit -q`：257 passed
- `.\scripts\uv.ps1 run pytest tests/sites -q`：31 passed
- `.\scripts\uv.ps1 run pytest tests/integration/test_sqlite_repositories.py -q`：20 passed

## 2. 最高優先規則

- 不回到 `HTTP-first` 主線。
- 不加回手動 Seed URL 建立流程。
- 不把站點規則塞回 `main.py`、routes、views、runtime 或 `ChromeCdpHtmlFetcher`。
- 不把 runtime 結果塞回 `watch_item`。
- 不移除舊 403 enum / state；它們仍是相容層。
- 不在第二站樣本明確前 payload 化 `WatchTarget` / `SearchDraft` 或大改 DB schema。
- 不在新 renderer 中把 `view_helpers.py`、`watch_view_partials.py`、`watch_detail_partials.py`、`ui_components.py` 當實作入口；這些多數已是相容 re-export 或頁面集成層。
- UI 實作前要看 `docs/ui_reference/README.md` 與對應圖片；不要假造後端尚未支援的資料。

GUI / Chrome 操作仍以 `AGENTS.md` 為準：Codex 不可自行啟動 GUI server 或專用 Chrome。需要視覺檢查時，必須請使用者先用安全模式啟動，並在使用者明確回覆已啟動後才可接手。

## 3. 正式主線

建立 watch：

1. 使用者在專用 Chrome 開啟可 preview 的 IKYU 頁面。
2. GUI 列出可附著分頁。
3. 使用者選分頁並 preview。
4. 使用者選候選方案、通知條件與檢查頻率。
5. application service 建立 watch，並用 preview 初始價格寫入 latest snapshot、check event、price history。

背景監看：

1. runtime 恢復 enabled 且未 paused 的 watch 分頁。
2. scheduler dispatch due work。
3. executor 擷取 browser page、建立 snapshot、compare、notification gate、persist。
4. repository 寫入 latest snapshot、history、notification state、runtime event、debug artifact。

`tab_id` 只作短期 Chrome session hint，不是 watch identity。

## 4. 重要架構位置

Runtime / monitor：

- `src/app/monitor/runtime.py`：高階 runtime 入口，只保留 wiring、start/stop、loop、status。
- `src/app/monitor/check_executor.py`：單次檢查主流程。
- `src/app/monitor/startup_restore.py`：啟動恢復分頁。
- `src/app/monitor/assignment_coordinator.py`：scheduler due work、in-flight 互斥、check-now。
- `src/app/monitor/notification_dispatch.py`：通知 dispatch 與 dispatcher cache。
- `src/app/monitor/watch_sync_coordinator.py`：watch definition sync 與 scheduler register/update/remove。
- `src/app/domain/watch_lifecycle_state_machine.py`：control command 與 runtime blocked pause 的正式決策中心。

Persistence：

- `src/app/infrastructure/db/repositories.py`
- runtime write / history query / fragment query / notification throttle state 已有 façade。
- write façade 已直接持有 database；history query SQL 尚有部分保留在相容 repository。

Web：

- `src/app/web/routes/`：HTTP route。
- `src/app/web/watch_page_service.py`：watch list / detail page context、fragment payload、revision token。
- `src/app/web/watch_creation_page_service.py`：Chrome tab selection context。
- `src/app/web/settings_page_service.py`：settings page context。
- `src/app/web/watch_fragment_contracts.py`：watch list / detail fragment payload 與 DOM hook contract。
- `src/app/web/client_contracts.py`：settings / watch creation DOM id。
- `src/app/web/ui_layout.py`、`ui_primitives.py`、`ui_icons.py`、`ui_behaviors.py`：共用 UI 基礎設施。
- `src/app/web/ui_components.py`、`view_helpers.py`：相容 re-export，新實作不要加回去。

Presenter / view model：

- `watch_list_presenters.py`：Dashboard / watch row / runtime dock。
- `watch_detail_presenters.py`：Watch Detail page view model。
- `settings_presenters.py`：Settings page view model。
- `watch_creation_presenters.py`：Add Watch page view model。
- `debug_presenters.py`：Debug capture list/detail presentation。

## 5. UI 進度

已完成：

- AppShell / sidebar / theme token。
- Dashboard 折衷清單。
- Add Watch 3-step wizard。
- Watch Detail 第一輪產品化。
- Settings 第一輪產品化。
- Debug 第一輪產品化。
- Watch Detail / Settings 第二輪前的 page service、presenter、partial、client script 架構 gate。

尚未完成：

- Watch Detail 尚未依 `docs/ui_reference/07_watch_detail.png` 做第二輪整頁資訊架構。
- Settings 尚未依 `docs/ui_reference/05_settings_notifications.png` 做通道卡片新版。
- Debug filter / tabs 可延後。
- 飯店圖片與完整 icon polish 不列為目前完成條件。

## 6. 下一步

1. 重構 Watch Detail 第二輪 UI。
   - 先看 `docs/ui_reference/07_watch_detail.png`。
   - 沿用 `WatchDetailPageViewModel`。
   - 修改對應 detail summary / trend / history partial，不把判斷塞回 route。
   - 保持 `/watches/{id}/fragments` 與 version endpoint contract 不變。

2. 重構 Settings 第二輪 UI。
   - 先看 `docs/ui_reference/05_settings_notifications.png`。
   - 沿用 `SettingsPageViewModel` 與 `settings_partials.py`。
   - 保持保存設定、測試通知、未儲存提示與離頁防呆。

3. UI 穩定後做人工 smoke test。
   - 由使用者啟動安全模式 GUI / 專用 Chrome。
   - 檢查列分頁、建立監視、手動 check、通知測試、暫停 / 恢復。

## 7. 測試位置

- `tests/unit/web/`：web route、renderer、fragment contract、settings、watch action、watch creation、debug capture。
- `tests/unit/monitor_runtime/`：runtime check execution、notification、backoff/blocking、startup restore、scheduler/check-now。
- `tests/unit/application/`：application service / use-case。
- `tests/unit/domain/`：domain rule。
- `tests/unit/notifiers/`：notifier formatter / dispatcher / transport。
- `tests/unit/infrastructure/`：non-browser infrastructure。
- `tests/unit/sites/` 與 `tests/sites/<site>/`：site boundary 與 parser fixture。
- `tests/integration/test_sqlite_repositories.py`：SQLite persistence integration。

不要再新增 `tests/unit/` 根目錄 top-level `test_*.py`。

## 8. 仍需觀察

- 長時間背景運作、節流、discard、blocked page 的真機穩定性。
- VPN / IP 風控下的使用者操作流程。
- 第二站加入前，blocking outcome 是否需要更正式的 control recommendation。
- `watch_item` 靜態定義與 control state 是否需要正式拆表。
- version polling endpoint 的 revision token 是否需要在更多頁面局部更新時抽成共用 read model service。
