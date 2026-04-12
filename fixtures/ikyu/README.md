# ikyu Fixtures

本目錄保存 `ikyu` parser 測試用的固定樣本，必須可在完全脫網的情況下重跑。

## 命名規則

- HTML fixture 使用 `<scenario>_<name>.html`
- 期望值檔使用與 fixture 同名的 `<scenario>_<name>.json`
- `scenario` 目前固定使用：
  - `available`
  - `sold_out`
  - `target_missing`
  - `format_variation`

## 收集與整理方式

- 先保留可重現 parser 行為所需的最小 HTML / hydration 內容
- 移除不必要或敏感 query 參數後再納入版本控制
- 每個 fixture 需搭配同名 `.json`，保存測試需要比對的最小期望值

## 目前已建立樣本

- `available_basic`
- `sold_out_basic`
- `target_missing_basic`
- `format_variation_basic`
