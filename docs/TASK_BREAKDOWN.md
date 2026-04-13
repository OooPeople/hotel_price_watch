# Task Breakdown

## Milestone 1: 專案初始化（已完成）

- o 建立專案目錄與基礎文件
- o 確認 Python `3.12` 與 `uv` 工作流
- o 定義資料夾結構
- o 建立基礎 lint / test 流程
- o 建立 `pytest` 設定與測試目錄骨架
- o 建立 `SiteAdapter` 抽象介面與 registry 骨架
- o 建立通知規則 domain model 骨架

## Milestone 2: Parser Proof（已完成）

- o 建立 `ikyu` URL normalizer
- o 建立 HTML fixture 收集方式
- o 定義 fixture 命名規則與期望值格式
- o 完成 `seed_url -> search_draft` 解析
- o 完成固定方案 URL 的預填驗證
- o 完成固定 `room-plan` 價格解析器
- o 完成 watch target canonicalization
- o 完成條件改變後的候選項重查
- o 完成 parser fixture tests
- o 驗證總價解析與 UI 衍生的每人每晚價格計算
- o 覆蓋正常可訂、無房、target missing、價格格式變化四類 fixture

## Milestone 3: Monitor Engine 模組（已初步接線）

- o 定義純設定用途的 watch item model
- o 定義單次檢查結果 model
- o 定義 `below_target_price` 的低價通知去重規則
- o 實作輪詢 scheduler
- o 實作價格比對規則
- o 實作通知規則 evaluator
- o 實作通知去重狀態
- o 實作錯誤退避與補掃策略
- o 實作 scheduler queue 與 worker state
- o 實作單實例所需的 port / lock file / PID 驗證與 stale lock recovery
- o 補齊 notification rule 與 compare engine 的單元測試

### Milestone 3 現況校正

- 上述項目目前代表 monitor domain / policy / scheduler 模組已存在
- o 已以 `lifespan` 將 monitor runtime 初步接到 app 啟動流程
- 目前仍缺單實例保護整合、穩定分頁識別策略與背景節流的完整策略反應

## Milestone 4: Persistence（已完成）

- o 建立 SQLite schema
- o 實作 watch item CRUD
- o 實作 `latest_check_snapshots` 分離儲存
- o 實作 `check_events` 歷史模型
- o 實作 price history persistence
- o 實作 `notification_states` persistence
- o 實作 debug artifact persistence 與每 watch item 保留上限
- o 實作 UI draft 與 watch target 分離儲存策略
- o 驗證 watch item 不混入 runtime 欄位
- o 建立 schema migration/versioning 基礎
- o 補齊 repository 與 migration 的整合測試

## Milestone 5: Notifications 模組（已初步接線）

- o 實作 desktop notification
- o 實作 `ntfy`
- o 實作 Discord webhook
- o 實作去重與通知節流
- o 實作 `parse_failed` 連續 `3` 次後僅通知一次的 degraded 流程

### Milestone 5 現況校正

- 目前 notifier、formatter、dispatcher、節流邏輯與全域通知通道設定頁都已存在
- o 已把它們初步接到 background monitor runtime
- 目前仍缺更完整的 runtime 驗證、失敗可觀測性與長時間運作穩定性確認

## Milestone 6: GUI

- o 做 watch item 列表頁
- o 做 watch item 刪除操作
- o 做新增 watch item 流程
- o 做 URL 預填 watch editor
- o 做 editor preview 的 browser fallback 補救路徑
- o 強化 browser fallback 為更接近人工操作的流程
- o 讓真實 `ikyu` URL 可穩定完成候選查詢
- o 做 GUI debug capture 檢視頁
- o 加入 preview 冷卻保護與 blocked-page stop
- o 做從專用 Chrome 分頁抓取與重新抓取
- o 做通知設定頁
- o 做主頁層級的全域通知通道設定頁
- o 做全域通知設定頁的測試通知按鈕，並走正式 dispatcher / notifier 路徑
- o 做最近歷史與錯誤摘要
- o 讓歷史頁顯示成功檢查、失敗檢查、availability 變化與通知結果
- o 在 UI 顯示由總價推算出的每人每晚價格
- o V1 editor 先只提供單一通知規則
- o 將建立 watch 的主流程改為專用 Chrome 分頁選取
- o 移除新增 Watch 主畫面的 Seed URL 手動輸入，改成只保留專用 Chrome 分頁抓取主入口
- o 將 debug 區補成可檢視成功與失敗 preview 摘要

### Milestone 6 風險註記

- `ikyu` 真站目前仍可能對同一出口 IP 做風控或短期封鎖
- V1 主線已改為專用 Chrome profile + CDP attach，不再把 HTTP-first 當正式可用路徑
- 後續背景輪詢需確認 Chrome 縮小至工作列時的刷新穩定性與節流訊號
- watch item 的背景監看將依賴專用 Chrome session，而非使用者當前前景分頁

## Milestone 6.5: Chrome-driven Runtime 收斂（交接優先）

- o 正式接上 background monitor runtime，而不是只停在 GUI / preview / CRUD
- o 以 `lifespan` 或同等 app-level runtime 方式啟動 scheduler / worker
- o 將 `SiteAdapter` 契約先收斂成正式支援 Chrome-driven preview，不再依賴 `hasattr()` 特例
- o 將 `SiteAdapter` 契約初步延伸到 Chrome-driven snapshot 介面
- o 將 `SiteAdapter` 契約進一步收斂到 Chrome-driven runtime 單一路徑
- o 清理舊的 `preview_from_form_inputs()` 與 create flow 殘留的 form-based 假設
- o 讓 watch polling 初步採用「附著專用 Chrome -> 找或重建分頁 -> refresh -> parse」路徑
- o 接上 notifier / dispatcher 與全域通知通道設定，讓設定不再是 write-only
- o 將單實例保護初步接到啟動流程
- o 初步改成使用 session 內較穩定的 Chrome page key，而非 index 型 `tab_id`
- o 將 `ikyu` 分頁比對補強為 query-aware，納入 `rm/pln/cid/ppc/rc` 等訊號
- o 初步落地 watch item 對應 Chrome 分頁的穩定識別策略
- o 補背景節流、站方阻擋頁、tab discard 的初步 runtime 寫入與 UI 顯示
- o 補首頁與 `/health` 的 runtime 狀態摘要，讓 background monitor 是否運行、註冊幾筆 watch、Chrome session 是否可附著可直接觀測
- o 決定 preview captures 與 runtime `debug_artifacts` 是否整併或明確分工
- o 補 background runtime 的 `403/blocked page` 暫停與成功恢復重置測試
- o 補 runtime 啟停與 active watch 同步測試，確認只註冊 enabled/unpaused watch，且停止後會清空 scheduler 狀態
- o 補多 watch 與 runtime 啟動後新增 watch 的 loop 測試，確認後續 tick 會持續同步並執行檢查
- o 將 blocked page / throttling / tab discard 整理成 watch 詳細頁可直接判讀的 runtime 訊號摘要
- o 深化單實例與既有實例導向整合，沿用既有實例前會先探測 `/health`
- o 深化單實例與既有實例導向整合，沿用既有實例前會比對 lock file 與 `/health` 的 `instance_id`
- o 將 runtime 錯誤映射改為型別導向，不再依賴字串比對
- o 補 watch 的啟用 / 停用 / 暫停 / 手動立即檢查 GUI 與 route
- o 接上睡眠恢復後的補掃邏輯
- o 為 Chrome 分頁比對加入最低分門檻與保守 fallback
- o 將通知節流狀態持久化，避免 app 重啟後通道冷卻歸零
- o 收斂 `NotificationDispatcher` 生命週期，避免每次 dispatch 重新建立

### Milestone 6.5 驗收條件

- 啟動 app 後，monitor runtime 會正式啟動且可持續輪詢
- 單一 watch item 能在不需手動重按 preview 的情況下，依排程刷新頁面並寫入歷史
- 全域通知通道設定能真正影響通知發送
- 不再存在 `HTTP-first` 與 Chrome-driven 雙重主線互相打架的情況
- 文件、GUI 行為與實際 runtime 狀態一致

## Milestone 7: Packaging

- 建立 PyInstaller spec
- 建立 build 腳本
- 驗證無 Python 環境啟動

## 建議實作順序

1. 先完成 parser proof，不先做 GUI
2. 先完成固定 `room-plan` 監看，再做候選列表重查
3. 先完成本機通知，不先做所有遠端通知
4. 先完成本機 web UI，不先做原生桌面 UI
5. 先完成 `onedir` 打包，不先做 `onefile`
6. 先完成可擴充的通知規則 evaluator，再讓 V1 UI 只接單規則

## 立即下一步

- o 用 `uv` 建立專案與 Python `3.12` 執行環境
- o 建立 `app/sites/base.py` 的抽象介面
- o 建立通知規則 domain model
- o 開始做 `ikyu` URL normalizer
- o 存第一批 fixture
- o 寫第一版 parser test
- o 完成條件改變後的候選項重查
- o 驗證總價解析與 UI 衍生的每人每晚價格計算
- o 定義單次檢查結果 model
- o 實作通知規則 evaluator
- o 實作通知去重狀態
- o 實作價格比對規則
- o 實作錯誤退避與補掃策略
- o 實作輪詢 scheduler
- o 實作 scheduler queue 與 worker state
- o 開始做 Persistence 所需的 SQLite schema 與 repository 骨架
- o 開始做通知通道與通知節流骨架
- o 開始做 GUI 的 watch item 列表頁與新增流程
- o 做 watch item 刪除操作
- o 強化 browser fallback 為更接近人工操作的流程
- o 讓真實 `ikyu` URL 可穩定完成候選查詢
- o 做 GUI debug capture 檢視頁
- o 加入 preview 冷卻保護與 blocked-page stop
- o 開始做 watch editor 的 Chrome 分頁抓取與重新抓取
- o 做最近歷史與錯誤摘要
- o 做通知設定頁
- o 做主頁層級的全域通知通道設定頁
- o 更新文件，將 V1 主線改為附著專用 Chrome profile
- o 正式接上 background monitor runtime
- o 先重整 `SiteAdapter` 契約，讓 Chrome-driven preview 成為正式介面
- o 將 Chrome-driven snapshot 也收斂成正式介面
- o 清理 `preview_from_form_inputs()` 與舊的 form-based create flow 假設
- o 將 notifier / dispatcher 接到 runtime，讓全域通知設定真正生效
- o 補 runtime 狀態摘要與 health/homepage 可觀測性
- o 決定並整理 preview captures 與 runtime `debug_artifacts` 的分工
- o 補 background runtime 的 `403/blocked page` 暫停與成功恢復重置測試
- o 將 runtime 錯誤映射改為型別導向，不再依賴字串比對
- o 補 watch 的啟用 / 停用 / 暫停 / 手動立即檢查 GUI 與 route
- o 接上睡眠恢復後的補掃邏輯
- o 為 Chrome 分頁比對加入最低分門檻與保守 fallback
- o 將通知節流狀態持久化
- o 收斂 `NotificationDispatcher` 生命週期，避免每次 dispatch 重新建立
