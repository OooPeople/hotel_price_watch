# Task Breakdown

## Milestone 1: 專案初始化

- 建立專案目錄與基礎文件
- 確認 Python `3.12` 與 `uv` 工作流
- 定義資料夾結構
- 建立基礎 lint / test 流程
- 建立 `pytest` 設定與測試目錄骨架
- 建立 `SiteAdapter` 抽象介面與 registry 骨架
- 建立通知規則 domain model 骨架

## Milestone 2: Parser Proof

- 建立 `ikyu` URL normalizer
- 建立 HTML fixture 收集方式
- 定義 fixture 命名規則與期望值格式
- 完成 `seed_url -> search_draft` 解析
- 完成固定方案 URL 的預填驗證
- 完成固定 `room-plan` 價格解析器
- 完成 watch target canonicalization
- 完成條件改變後的候選項重查
- 完成 parser fixture tests
- 驗證總價解析與 UI 衍生的每人每晚價格計算
- 覆蓋正常可訂、無房、target missing、價格格式變化四類 fixture

## Milestone 3: Monitor Engine

- 定義純設定用途的 watch item model
- 定義單次檢查結果 model
- 定義 `below_target_price` 的低價通知去重規則
- 實作輪詢 scheduler
- 實作價格比對規則
- 實作通知規則 evaluator
- 實作通知去重狀態
- 實作錯誤退避與補掃策略
- 實作 scheduler queue 與 worker state
- 實作單實例所需的 port / lock file / PID 驗證與 stale lock recovery
- 補齊 notification rule 與 compare engine 的單元測試

## Milestone 4: Persistence

- 建立 SQLite schema
- 實作 watch item CRUD
- 實作 `latest_check_snapshots` 分離儲存
- 實作 `check_events` 歷史模型
- 實作 price history persistence
- 實作 `notification_states` persistence
- 實作 debug artifact persistence 與每 watch item 保留上限
- 實作 UI draft 與 watch target 分離儲存策略
- 驗證 watch item 不混入 runtime 欄位
- 建立 schema migration/versioning 基礎
- 補齊 repository 與 migration 的整合測試

## Milestone 5: Notifications

- 實作 desktop notification
- 實作 `ntfy`
- 實作 Discord webhook
- 實作去重與通知節流
- 實作 `parse_failed` 連續 `3` 次後僅通知一次的 degraded 流程

## Milestone 6: GUI

- 做 watch item 列表頁
- 做新增 watch item 流程
- 做 URL 預填 watch editor
- 做日期 / 人數 / 房型變更後重查
- 做通知設定頁
- 做最近歷史與錯誤摘要
- 讓歷史頁顯示成功檢查、失敗檢查、availability 變化與通知結果
- 在 UI 顯示由總價推算出的每人每晚價格
- V1 editor 先只提供單一通知規則

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

- 用 `uv` 建立專案與 Python `3.12` 執行環境
- 建立 `app/sites/base.py` 的抽象介面
- 建立通知規則 domain model
- 開始做 `ikyu` URL normalizer
- 存第一批 fixture
- 寫第一版 parser test
