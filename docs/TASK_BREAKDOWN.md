# Task Breakdown

本文件只保留目前進度、下一步與風險。規格看 `docs/V1_SPEC.md`，架構邊界看 `docs/ARCHITECTURE_PLAN.md`，UI 改版看 `docs/UI_REDESIGN_PLAN.md`，交接看 `docs/HANDOFF_PLAN.md`。

## 目前總結

- o V1 正式主線已收斂為「附著專用 Chrome profile + CDP attach」
- o `ikyu` watch 建立、背景輪詢、歷史、debug、通知與控制操作已可實際使用
- o lifecycle owner、control command policy、site-aware browser strategy 已完成第一輪收斂
- o `main.py`、web routes、web renderers、`ChromeCdpHtmlFetcher` 已完成第一輪拆分
- o 目前已通過 `ruff check src tests` 與全量 `pytest`，目前測試數為 `249 passed`

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
- o 首頁與 watch 詳細頁局部 polling 更新

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
- o web renderer 第二輪整理已開始：watch list / detail partial 已拆出，為後續 UI 美化與版面重設準備
- o watch creation partial 已拆出：preview、candidate option、Chrome tab card、diagnostics table 已與頁面級 renderer 分離
- o UI primitives 已收斂：`ui_styles.py` 管理 style token，`ui_components.py` 管理 card、table、button/link，`view_helpers.py` 保留相容匯出
- o web renderer 內部 import 已改用正式 UI 模組，`view_helpers.py` 僅作相容層，避免後續出入口混亂
- o 設定頁正式入口已改為 `/settings`，舊 `/settings/notifications` 保留相容
- o UI 改版第一步已建立 presentation helper，集中價格、空房、通知、錯誤與狀態文案
- o UI components 第一輪已補 page header、section header、summary card、status badge、key-value grid 與 collapsible section
- o Dashboard / Watch List 第一輪已改為 summary cards、watch cards 與降權系統狀態
- o Watch Detail 第一輪已加入 hero summary、價格摘要卡與預設收合的進階診斷
- o Add Watch 第一輪已改為單頁步驟區塊、方案卡與預設收合的抓取詳情
- o Settings 第一輪已加入設定摘要卡、展開編輯區與 Discord webhook 摘要遮罩
- o Debug 第一輪已套用進階診斷定位、摘要卡與收合式 raw metadata / HTML 預覽
- UI 下一輪需重新評估；Dashboard 第二輪清單 / 卡片重構已撤回，先維持第一輪首頁版本
- o Visual Theme / AppShell 第一段已完成：theme token、sidebar 導覽、窄版上方導覽與 AppShell 測試
- o renderer 內常見 hard-coded color 已收斂到 `ui_styles.py` theme token 與 meta / card helper
- o typography hierarchy 與主要 spacing 節奏已收斂到 `ui_styles.py` helper
- o 頁首返回入口已收斂到 `page_header(back_href=...)`，主要 CTA 統一保留在 header actions 區
- o Watch Card 第二輪第一段已完成：最後檢查、目前價格、通知條件、錯誤摘要；刪除維持直接顯示
- o Watch Detail 第二輪已加入輕量 MiniPriceChart / sparkline，並接上 detail fragment polling
- o Responsive pass 第一段已完成：頁首操作、AppShell 導覽、表格與 detail hero 已補窄版規則
- o UI 一致性修正第一批已完成：文案統一為「監視」、按鈕尺寸分級、首頁卡片資訊重排、使用者層隱藏「停用」、新增監視流程降噪
- o UI 一致性修正第二批已完成：左側 AppShell 可收合，首頁監視項目支援卡片 / 清單切換，且 fragment polling 會保留顯示模式
- o UI 一致性修正第三批已完成：新增監視頁首說明降噪、watch detail 最近通知時間分行、價格趨勢補輕量座標軸與 hover 點位資訊
- Dashboard 第二輪第一批已撤回：不採用 hybrid list row、單層四段式卡片、刪除收進更多選單與產品摘要替換

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

1. 依新版 UI 計畫補強新增監視頁流程感：步驟條、Step 4 確認摘要與桌機版 summary。
2. UI 穩定後做人工 smoke test：啟動、列分頁、建立監視、手動 check、通知測試、暫停 / 恢復。
3. 若 smoke test 穩定，再進入 Packaging 或第二站 spike。

## 目前主要風險

- `ikyu` 真站仍可能對同一出口 IP 做風控。
- 背景監看依賴專用 Chrome session，仍需真機長時間驗證。
- Chrome 縮小、背景、discard 或站方 blocked page 的實際行為仍可能因環境不同而變動。
- 第二站若不是 lodging-room-plan 模型，現有 target / candidate / DB contract 需要 migration。
