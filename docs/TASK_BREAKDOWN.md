# Task Breakdown

本文件只保留三種資訊：
- 已完成到哪個里程碑
- 目前主線還缺什麼
- 下一步應先做什麼

細節設計與交接說明請看：
- `docs/V1_SPEC.md`
- `docs/ARCHITECTURE_PLAN.md`
- `docs/HANDOFF_PLAN.md`

## 目前總結

- o V1 正式主線已改為「附著專用 Chrome profile + CDP attach」
- o GUI、preview、watch CRUD、全域通知設定、debug captures 已可實際操作
- o background runtime 已接線，且已完成第一輪高風險穩定化
- 目前主線已從「功能缺失」轉進「長時間穩定性驗證 + 第二層結構整理」

## Milestone 1: 專案初始化（已完成）

- o Python `3.12` + `uv` 工作流
- o 專案目錄、lint、test 骨架
- o `SiteAdapter` / registry / domain model 基礎

## Milestone 2: Parser Proof（已完成）

- o `ikyu` URL normalizer
- o fixture 收集規則與 parser tests
- o `seed_url -> search_draft`
- o 精確 `room-plan` 價格解析
- o watch target canonicalization
- o 條件改變後的候選重查
- o 每人每晚價格衍生顯示

## Milestone 3: Monitor Engine（已完成模組，已初步接線）

- o scheduler / queue / worker state
- o compare / notification evaluator / dedupe / backoff / wakeup rescan
- o 單實例所需的 port / lock / PID 驗證骨架
- o monitor runtime 已透過 app `lifespan` 初步接到啟動流程

## Milestone 4: Persistence（已完成）

- o SQLite schema
- o watch item / draft / latest snapshot / check event / price history / notification state / debug artifact persistence
- o watch 設定與 runtime state 分離
- o schema versioning 與 migration 基礎

## Milestone 5: Notifications（已完成模組，已初步接線）

- o desktop / `ntfy` / Discord webhook notifier
- o formatter / dispatcher / throttle
- o degraded 通知流程
- o 全域通知通道設定已接到 runtime
- o 測試通知會走正式 dispatcher / notifier 路徑

## Milestone 6: GUI（已完成第一版）

- o watch 列表、新增、刪除
- o 從專用 Chrome 分頁抓取建立 watch
- o 候選方案、價格、每人每晚顯示
- o watch 詳細頁、歷史與錯誤摘要
- o 單一 watch 的通知規則設定
- o 全域通知通道設定頁
- o debug captures 列表、詳細頁、清空
- o watch 的啟用 / 停用 / 暫停 / 恢復 / 手動立即檢查
- o 首頁與 watch 詳細頁已支援局部 polling 更新，不需手動整頁刷新
- o Chrome 分頁清單已改成以 target identity / `browser_page_url` / query-aware matching 判斷既有 watch，不再由 `tab_id` 主導
- o runtime 啟動恢復時，已恢復給前一個 watch 的 tab 不會再被下一個 watch 重用

### Milestone 6 風險註記

- `ikyu` 真站仍可能對同一出口 IP 做風控
- 背景監看依賴專用 Chrome session，不依賴使用者當前前景分頁
- Chrome 縮小或背景運作時，仍需持續驗證節流 / discard / blocked page 行為

## Milestone 6.5: Chrome-driven Runtime 收斂（第一輪高風險項已完成）

- o runtime 已正式接上 app 啟動流程
- o `SiteAdapter` 已正式支援 browser preview 與 browser snapshot
- o create flow 與 runtime 主線已收斂到 Chrome-driven 路徑
- o watch 與 Chrome 分頁的穩定識別已初步落地
- o runtime status、blocked page、throttling、tab discard 已可觀測
- o 單實例沿用已加 `/health` 與 `instance_id` 驗證
- o runtime 錯誤映射已改為型別導向
- o 背景排程與 `check-now` 已共用 per-watch 互斥
- o 單次 check 已改成單一 transaction 持久化
- o SQLite 已補 `WAL`、`busy_timeout` 與歷史查詢 index
- o migration 已改成明確鏈式升版
- o state-changing POST route 已補本機 `Origin/Referer` 驗證
- o notifier 外部 HTTP 請求已補顯式 timeout
- o runtime 啟動時會低速恢復 enabled 且未 paused 的 watch 分頁，輪詢時仍保留缺頁補建
- o 已引入正式 `WatchRuntimeState`，GUI 不再靠零散欄位拼湊目前狀態語意
- o 已補 server-side invariant：輪詢秒數下限、正數目標價、通知 URL 必須為合法 `http/https`

### Milestone 6.5 尚未完成

- 補更完整的長時間運作、節流與重試行為驗證
- 釐清 preview / runtime / notification 的更長時間失敗模式

### Milestone 6.5 近期已補的驗證

- o 已驗證通知通道冷卻會跨 runtime 重啟保留
- o 已驗證單一通知通道失敗不會中止整次 check，且其他通道仍可成功送出
- o 已驗證連續 timeout 會遞增 backoff，且 backoff 後成功檢查會清掉 failure 狀態
- o 已引入 `runtime_state_events`，把 blocked / paused / resumed / recovered transition 納入正式事件模型

## Milestone 7: Packaging（尚未開始）

- 建立 PyInstaller spec
- 建立 build 腳本
- 驗證無 Python 環境啟動

## 第二層整理（非第一線風險）

- 拆 `main.py`
- 拆 `web/views.py`
- 收斂 `ChromeCdpHtmlFetcher`
- 整理 state ownership

## 立即下一步

- 補更完整的長時間運作、節流與重試行為驗證
- 視結果決定是否再做一輪整體 review
- 若高風險項沒有新增，再進第二層結構整理：
  - 拆 `main.py`
  - 拆 `web/views.py`
  - 收斂 `ChromeCdpHtmlFetcher`
  - 整理 state ownership
