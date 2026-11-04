# 列傳（`tianxia/features/zhuan/`）

一季的終點是一篇列傳：寫傳（鎖內開單、鎖外叫模型、鎖內重驗再存的三段式）、休季三顆（用列傳插畫、蓋紀念印、請人物親筆評曰）、行狀頁與分享。全部拆包第 29 批（計畫 `docs/superpowers/plans/2026-11-04-列傳包-第1批.md`）。

這份 README 是 Task 2 的骨架，Task 3～4 搬完補齊（導覽與設計稿、認領的欄位、還留在原位的接縫、另外要跑的混合檔）。

- 導覽：`docs/guide/大勢人物與賽季.md`、`docs/guide/核心與存檔.md`（行狀）。
- 認領的 `PlayerState` 欄位：無（`annals`、`annals_mark`、`xingshi_seen` 是行狀，核心 `annals.py` 管；列傳存在資料庫的 `biographies` 表、票在錢包裡）。
- 內容：`content/verdicts.json`（人物評曰的固定句，驗證在 `ZhuanFeature.check_content`）。
