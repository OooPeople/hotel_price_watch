# hotel_price_watch

本專案是 `ikyu.com` 飯店價格監看器的 Python 版本。

## 目標

- 做出可在背景穩定運作的價格監看工具
- 第一版不依賴瀏覽器分頁常駐
- 先把監看、比價、通知與設定模型做穩
- GUI、打包、browser fallback 分階段補上

## 開發原則

- 優先保持 `HTTP-first`，只有在直接抓取失敗或資料不足時才引入瀏覽器 fallback
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

## 實作提醒

- 設定與 runtime state 要分離
- 監看結果要有歷史紀錄與最近一次解析摘要
- 如果 `ikyu` HTML 結構變動，先更新 fixture 與 parser 測試，再改正式解析器
- 讀取 `.md` 文件時，一律使用 PowerShell 搭配 UTF-8：
  - 先設定 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
  - 再使用 `Get-Content -Encoding UTF8`
  - 避免因預設編碼造成亂碼判讀錯誤
- review agent 可作為里程碑完成後的額外審查工具，但不可自行呼叫
  - 只有在使用者明確同意後，才可建立 review agent
  - 若判斷某個里程碑適合做 review，只能先提出建議，不可直接啟動
