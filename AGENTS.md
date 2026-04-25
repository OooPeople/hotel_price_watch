# hotel_price_watch

本專案是以 Python 開發的飯店價格監看器，架構上預留多站擴充能力；目前第一版僅實作 `ikyu.com`，優先先把單站監看流程做穩。

## 目標

- 做出可在背景穩定運作的價格監看工具
- 第一版以附著專用 Chrome profile 為主，讓監看與預覽共用穩定 session
- 先把監看、比價、通知與設定模型做穩
- GUI、打包與背景輪詢分階段補上

## 開發原則

- V1 以附著專用 Chrome profile 讀取與刷新頁面為主，不再把 `HTTP-first` 視為正式主線
- 優先監看精確的 `room-plan` 目標，不做模糊最低價比對
- 所有監看條件都要 canonicalize，避免只靠原始 URL 判定
- 解析器必須可測試，HTML fixture 要能脫離網路重跑
- 通知行為保持 opt-in，避免預設對外發送

## 範圍邊界

- 不做自動訂房
- 不做帳號登入、搶房、點數最佳化
- V1 不做多站通用框架
- V1 不做 Windows Service

## 文件順序

- `docs/V1_SPEC.md`
- `docs/ARCHITECTURE_PLAN.md`
- `docs/TASK_BREAKDOWN.md`
- `docs/HANDOFF_PLAN.md`

## 實作規則

- 設定與 runtime state 要分離
- 監看結果要有歷史紀錄與最近一次解析摘要
- 如果 `ikyu` HTML 結構變動，先更新 fixture 與 parser 測試，再改正式解析器
- 之後新增或修改程式碼時，函式需補上繁體中文註解或 docstring，簡要說明該函式的用途
  - 以讓人快速理解職責為主，不需要寫成冗長逐行解說
  - 函式、類別、模組的用途說明優先使用 `"""..."""` docstring
  - 只有在補充局部邏輯、特殊條件或實作原因時，才使用 `# ...` 單行註解

## 協作規則

- 當使用者要求生成 commit message 時，必須先遵守 `GIT_COMMIT_RULES.md`
  - `type` 與 `scope` 使用英文
  - `summary`、`body`、`footer` 一律使用繁體中文
  - 不可預設輸出英文版 `summary`
- 更新 `docs/TASK_BREAKDOWN.md` 時，已完成項目需同步標示為已完成
  - 完成項目標為 `- o ...`，未完成項目不加任何前綴，直接使用一般清單 `- ...`
  - 避免計劃表與實際進度脫節
- 讀取 `.md` 文件時，一律使用 PowerShell 搭配 UTF-8：
  - 先設定 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
  - 再使用 `Get-Content -Encoding UTF8`
  - 避免因預設編碼造成亂碼判讀錯誤
- 執行 `uv` 相關命令時，優先使用專案 wrapper：
  - 例如 `.\scripts\uv.ps1 run pytest`
  - wrapper 會把 `UV_CACHE_DIR` 指向專案內 `.uv-cache`，避免使用者全域 uv cache 權限或污染問題
- 執行 `pytest` 時不要用 parallel tool 同時跑多組 pytest
  - 目前測試共用 `.pytest_tmp_active`，並行 pytest 可能互相刪除或鎖住 SQLite 暫存資料庫
  - 若需要跑 targeted tests 與全量 tests，請依序執行
- 若某個問題已持續排查一段時間仍無法收斂，需及時停損並改用外部搜尋或官方資料確認
  - 避免長時間盲試或只在本地反覆猜測
  - 搜尋後若找到更直接的解法，應優先採用較省時且可驗證的方案
- review agent 可作為里程碑完成後的額外審查工具，但不可自行呼叫
  - 只有在使用者明確同意後，才可建立 review agent
  - 若判斷某個里程碑適合做 review，只能先提出建議，不可直接啟動

## Chrome MCP 操作規則

- 操作 Chrome 前需先用 `tool_search` 載入完整 Chrome DevTools MCP 工具
  - 不可只依初始工具列表判斷功能是否缺失
  - 至少確認 `click`、`fill`、`evaluate_script`、`navigate_page`、`select_page`、`wait_for` 是否可用
- 測試一般 Chrome MCP 互動能力時，優先使用 `chrome-devtools`
  - 可用無害的 `data:` 測試頁驗證 click、fill、evaluate 是否正常
  - 不需要連到專用 Chrome profile 或 `127.0.0.1:8000`
- 測試本專案 GUI、專用 profile、既有 ikyu session 時，優先使用 `chrome-devtools-dedicated`
  - 使用前先檢查 `http://127.0.0.1:9222/json/version` 是否可連線
  - 若 `9222` 不通，表示目前沒有可附著的專用 Chrome，需請使用者用一般 PowerShell 啟動
- 目前 Codex shell 無法可靠自行啟動專用 Chrome
  - 從 Codex shell 啟動 `app.tools.chrome_profile` 或直接呼叫 `chrome.exe` 可能因 Windows IPC / sandbox 權限失敗
  - 需要專用 Chrome 時，請使用者先執行安全模式：
    - `$env:HOTEL_PRICE_WATCH_RUNTIME_ENABLED="0"`
    - `.\scripts\uv.ps1 run python -m app.tools.dev_start`
- 安全測試本機 GUI 時，不可主動操作 ikyu 分頁
  - 不重新整理 ikyu
  - 不執行 preview
  - 不按「立即檢查」
  - 不建立、刪除或修改監視，除非使用者明確要求
