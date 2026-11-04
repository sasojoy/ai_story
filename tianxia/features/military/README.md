# 軍情（`tianxia/features/military/`）

- 做什麼：軍令卡（江湖頁「本週軍令」）與押糧（接下糧車、走到終點交軍令）、第 2 階行動、第 3／4 階行動（黃巾煽動起事、豪強修築塢堡與趁亂占據郡縣）、第 4 階席次的抄帳、
  管理者重發軍令／輪替席次／替人發召見。全部拆包第 33 批從 `Game` 搬來（17 個方法）；包名不叫 `orders`：`tianxia/orders.py`（軍令的規則）留在原位。
- 導覽：`docs/guide/大勢人物與賽季.md` 的軍令與晉升那幾節
- 設計稿：`docs/superpowers/specs/2026-10-04-第一季陣營內容-軍令.md`、第一季正式版計畫戊（第 3、4 階行動）、丁（第 4 階席次）

## 檔案

（Task 3 搬進來之後補。）

## 認領的欄位（`PlayerState`，換季全部跟著新角色重來，沒有帶走的）

`convoy`（押著的糧車；只有這一包寫）、`rank2_days`（第 2 階行動今天做了幾次）、`rank_action_weeks`（第 3、4 階行動這週做了幾次；`rank_rules.count` 寫）。
`donations`（押糧與捐糧效果都寫）、`summons`、`qualified`、`rank`、`contrib_weeks`、`rank_hinted` 是共用或階級、席次規則層的，不認領。

## 還留在核心原位的接縫

（Task 3 搬進來之後補。）
