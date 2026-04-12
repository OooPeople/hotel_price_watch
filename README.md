# hotel_price_watch

以 Python 開發的飯店價格監看工具專案，長期目標為支援多個訂房網站；目前第一版僅支援 `ikyu.com`。

目前階段以規劃與專案骨架為主，目標是先做出可長時間背景運作的 Python 版價格監看器，再逐步補上 GUI、通知、封裝與瀏覽器 fallback。

## 當前定位

- 長期目標為支援多站，但第一版先限定在 `ikyu.com`
- V1 目前以附著專用 Chrome profile 為主，透過真人 session 讀取與刷新 `ikyu` 頁面
- V1 先支援精確監看單一 `hotel + room + plan + occupancy + date`
- GUI 建立 watch 與後續背景輪詢，都以可附著的專用 Chrome session 為目前主線

## 專案結構

- `docs/`
  - 規劃、規格與任務拆分文件
- `src/`
  - 後續 Python 實作主程式碼
- `tests/`
  - 測試程式
- `fixtures/`
  - 後續保存網站 HTML fixture 與解析樣本

## 先看哪些文件

- [docs/V1_SPEC.md](/e:/P3/xx/ticket/hotel_price_watch/docs/V1_SPEC.md)
- [docs/ARCHITECTURE_PLAN.md](/e:/P3/xx/ticket/hotel_price_watch/docs/ARCHITECTURE_PLAN.md)
- [docs/TASK_BREAKDOWN.md](/e:/P3/xx/ticket/hotel_price_watch/docs/TASK_BREAKDOWN.md)
- [docs/HANDOFF_PLAN.md](/e:/P3/xx/ticket/hotel_price_watch/docs/HANDOFF_PLAN.md)
