# Task Breakdown

本文件只保留目前進度、下一步與風險。規格看 `docs/V1_SPEC.md`，架構邊界看 `docs/ARCHITECTURE_PLAN.md`，UI 改版看 `docs/UI_REDESIGN_PLAN.md`，交接看 `docs/HANDOFF_PLAN.md`。

## 目前總結

- o V1 正式主線已收斂為「附著專用 Chrome profile + CDP attach」
- o `ikyu` watch 建立、背景輪詢、歷史、debug、通知與控制操作已可實際使用
- o lifecycle owner、control command policy、site-aware browser strategy 已完成第一輪收斂
- o `main.py`、web routes、web renderers、`ChromeCdpHtmlFetcher` 已完成第一輪拆分
- o 最近一次本輪驗證已通過 `ruff check` 與 `pytest tests/unit -q`，目前單元測試數為 `225 passed`

## 已完成範圍

### V1 功能

- o parser / normalizer / fixture-based parser tests
- o `seed_url -> search_draft -> watch_target` 與精確 `room-plan` identity
- o scheduler、runtime、per-watch 互斥、`check-now`
- o SQLite schema、migration、`WAL`、`busy_timeout`
- o latest snapshot、check event、price history、notification state、runtime state event、debug artifact persistence
- o desktop / `ntfy` / Discord webhook notifier
- o notification formatter、dispatcher、throttle 與測試通知
- o watch 列表、新增、刪除、詳細頁、歷史、debug captures、通知設定
- o 通用設定頁已集中全域通知通道與 GUI 時間顯示偏好
- o 設定頁已支援未儲存提示與離頁前防呆
- o watch 啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- o 首頁與 watch 詳細頁已改為 version polling；資料版本不變時不再固定抓整包 fragment
- o 首頁最後檢查相對時間與退避倒數已改由前端局部更新，不觸發後端 fragment refresh

### V1.5 架構地基

- o V1 正式路徑不再使用 `HTTP-first`
- o 建立 watch 的正式入口已改為「從專用 Chrome 分頁抓取」
- o `WatchLifecycleCoordinator` 已成為人工 control transition owner
- o `watch_lifecycle_state_machine.py` 已集中 control command decision、scheduler side effect 與 in-flight policy
- o runtime auto-pause 已改走 lifecycle state machine
- o in-flight policy 明確採 `continue-and-gate`，不做 hard cancel
- o `TaskLifecyclePolicy` 已在 capture 後、通知前、持久化前 gate 結果
- o `WatchRuntimeState` 與 `runtime_state_events` 已成為 GUI / runtime 的正式狀態語意
- o `BrowserBlockingOutcome` 已取代錯誤訊息片段判斷
- o `SiteAdapter` 已承擔 browser page capability 與 browser strategy
- o `ChromeCdpHtmlFetcher` 已支援 per-site / per-request browser page strategy
- o 站點 adapter 與 browser strategy wiring 已集中到 `bootstrap/site_wiring.py`

### 結構整理

- o `main.py` 已收斂為 app factory、lifespan、container 掛載、router include 與 health endpoint
- o web routes 已拆到 `src/app/web/routes/`
- o web renderers 已依頁面群組拆分，`app.web.views` 只保留相容 re-export
- o web routes 已補必要 page context helper，避免首屏與 fragment 重複組資料
- o `ChromeCdpHtmlFetcher` 已拆出 profile launcher、CDP connector、page matcher、page capture helper 與 chrome models
- o web renderer 第二輪整理已完成主要拆分：`watch_client_scripts.py`、`watch_action_partials.py`、`watch_list_partials.py`、`watch_detail_partials.py` 已成為正式實作模組，`watch_view_partials.py` 只保留相容匯出
- o watch creation partial 已拆出：preview、candidate option、Chrome tab card、diagnostics table 已與頁面級 renderer 分離
- o UI primitives 已收斂：`ui_styles.py` 管理 style token，`ui_components.py` 管理 card、table、button/link，`view_helpers.py` 保留相容匯出
- o web renderer 內部 import 已改用正式 UI 模組，`view_helpers.py` 僅作相容層，避免後續出入口混亂
- o 設定頁正式入口已改為 `/settings`，舊 `/settings/notifications` 保留相容
- o UI 基礎第一輪已完成：`ui_styles.py` 管理 theme token / typography / spacing，`ui_components.py` 提供 AppShell、page header、summary card、badge、button、table、collapsible section 與 inline SVG icon
- o AppShell 已對齊參考圖方向：IKYU 品牌、icon 導覽、可收合 sidebar、窄版規則與主要內容平滑位移；側邊欄已移除重複的系統狀態與無功能帳號區
- o Dashboard / Watch List 已完成折衷清單方向：summary cards、卡片 / 清單切換、目前價格、24 小時價格變動、通知條件、runtime 狀態、最後檢查相對時間與底部可收合系統狀態
- o Add Watch 已完成第二輪主要流程：3-step top wizard、Chrome 分頁選擇、候選方案、建立前摘要、來源提醒、preview cache 與建立後初始價格顯示
- o Watch Detail 已有第一輪產品化與局部強化：hero summary、價格摘要、輕量 MiniPriceChart / sparkline、detail fragment polling 與預設收合的進階診斷；尚未依 `07_watch_detail.png` 完成第二輪整頁重構
- o Settings 已有第一輪產品化：設定摘要卡、展開編輯區、Discord webhook 摘要遮罩、未儲存提示與離頁防呆；尚未依 `05_settings_notifications.png` 完成第二輪通道卡片重構
- o Debug 已完成第一輪產品化：進階診斷定位、摘要卡、收合式 raw metadata / HTML 預覽；後續可再補 filter / tabs
- o Responsive pass 與 UI 一致性修正已完成多批：監視文案、按鈕尺寸、頁首返回入口、主要 CTA、首頁資訊重排、detail 趨勢圖 hover、fragment polling 保留顯示模式
- o UI 下一輪方向已重新收斂：飯店圖片與完整 icon polish 延後，Dashboard 維持折衷清單方向，不採資訊過密 hybrid row，也不把刪除收進更多選單
- o UI 參考圖已整理到 `docs/ui_reference/`，後續 UI phase 實作前後需對照圖片避免偏離目標資訊架構
- o 新增監視建立後會保存 preview 已抓到的初始價格摘要、檢查事件與價格歷史，首頁不再因剛建立就顯示「尚未檢查」
- o Chrome 分頁建立流程已改用短期 preview cache：抓取分頁成功後，按建立不再重抓同一 IKYU 分頁，並補 timeout 避免畫面無限等待
- o Chrome 分頁來源資格已拆成站點辨識與 preview eligibility；IKYU 首頁 / 缺日期人數條件頁不再出現在可抓取清單，但既有 watch 分頁比對仍維持寬鬆站點辨識
- o Watch creation preview cache 已收斂為 application service 並掛入 AppContainer，route 不再使用全域 dict 保存 preview 狀態
- o Watch creation 初始價格保存已移出 route，改由 `WatchCreationSnapshotService` 負責，並透過 repository 單一 transaction 寫入 latest snapshot、check event、price history
- o Dashboard Phase 3 第一段已完成：新增 `WatchRowPresentation` 集中首頁 row / card 判讀，清單與卡片共用價格、24 小時價格變動、通知條件與狀態文案
- o Dashboard 重構經驗已回饋到架構文件：Watch Detail / Settings 第二輪 UI 前需先整理 route orchestration、watch partial、client script 與 fragment contract
- o Watch client scripts 已從 `watch_view_partials.py` 抽出到 `watch_client_scripts.py`；watch list / detail / action HTML renderer 也已搬到對應 partial 模組
- o watch list / detail fragment payload 與 DOM hook contract 已集中到 `watch_fragment_contracts.py`，route、renderer、client script 與測試共用同一組 key / id 定義
- o Watch Detail 第二輪 UI 前的 presenter gate 已完成：`WatchDetailPresentation` 集中 detail hero、價格摘要、通知摘要與 runtime state 基礎資料
- o Settings 第二輪 UI 前的 presentation gate 已完成：`NotificationChannelSettingsPresentation` 集中摘要卡、啟用狀態、表單回填與敏感值遮罩

## 第二站前決策

- o 已明確標註目前 `SearchDraft`、`WatchTarget`、`OfferCandidate` 與 SQLite schema 仍是 lodging-room-plan contract
- 第二站若同屬 hotel / room / plan 型網站，可先沿用目前 contract
- 第二站若不是 hotel / room / plan 型網站，需先設計 site-specific target payload / candidate payload 與 migration
- 在第二站樣本明確前，暫不把 `WatchTarget` / `SearchDraft` payload 化，避免過度抽象
- 在第二站樣本明確前，暫不把 `ChromeDrivenMonitorRuntime` 泛化成非 browser runtime

## 延後項目

- `watch_control_states` table：目前只保留 future migration plan，不立即 migration
- 更完整的長時間真機穩定性驗證：包含節流、discard、blocked page、VPN / IP 風控
- Packaging：PyInstaller spec、build 腳本、無 Python 環境啟動驗證
- 第二站 spike：需先選定具體站點樣本，再判斷 target contract 是否足夠

## 下一步

1. 對照 `07_watch_detail.png` 重構監視詳情頁，沿用 `WatchDetailPresentation`、fragment contract 與既有 action presentation。
2. 對照 `05_settings_notifications.png` 重構設定頁，沿用 `NotificationChannelSettingsPresentation` 與既有設定保存流程。
3. 兩個頁面穩定後做人工 smoke test：啟動、列分頁、建立監視、手動 check、通知測試、暫停 / 恢復。
4. 若 smoke test 穩定，再進入 Packaging 或第二站 spike。

## 目前主要風險

- `ikyu` 真站仍可能對同一出口 IP 做風控。
- 背景監看依賴專用 Chrome session，仍需真機長時間驗證。
- Chrome 縮小、背景、discard 或站方 blocked page 的實際行為仍可能因環境不同而變動。
- 第二站若不是 lodging-room-plan 模型，現有 target / candidate / DB contract 需要 migration。
- `ui_components.py` 仍混合 layout、icons、primitives 與 behavior，後續新增共用 UI 時需避免繼續膨脹。
- `web/routes/` 仍承接部分 page workflow 與 fragment payload 組裝細節，後續可再抽 page read model / payload builder。
