# 慢慢長出來（`tianxia/features/unfold/`）

- 做什麼：新角色還用不到的分頁先不畫，玩到才長出來；長出來的那一塊亮紅點，點開才滅，長出來就不收回。
- 導覽：`docs/guide/地圖與介面.md` 的「慢慢長出來」那一節
- 設計稿：提案表 https://claude.ai/artifact/YUs4edGz4zdhy4pckYeYCv（Joy 2026-11-25 三個決定：商城越快越好、舊角色不要收、說明框一起換）
- 開關：`Config.unfold.enabled`（預設關，`tianxia/core/tuning/unfold.py`；三種設定都還沒開）；路由 `/api/unfold/seen` 關著 404。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：on_sync、after_action（看一次身上的東西，長出來的寫進本子）、on_season_start（照帶）、status（`main.unfold` = `{hide, fresh}`）、routes |
| `rules.py` | 純規則：哪幾塊會藏（`KEYS`）、各自什麼時候長出來（`reached`）、長出來（`grow`）、看過（`seen`） |
| `routes.py` | `POST /api/unfold/seen {keys}`：剛長出來的紅點滅 |
| `web/unfold.js` | 紅點：底部分頁、俠客頁子分頁、人像卡上那一顆連結（`registerDot`）；藏的那一步在 `web/app.js` 的 `shown()` |
| `tests/` | `test_unfold.py`、`test_unfold_smoke.py` |

**誰有這一本**：開關開著時、站在城門口還沒選路（核心服務 `ctx._opening_pending()`）的真人角色同步那一下開本。舊角色、假人沒有這一本＝全部照舊攤開（Joy 11/25「不要收」）。
**認領的欄位**：`PlayerState.unfold`（`UnfoldBook`：grown、fresh），標 QUIET，None 不寫進存檔；跟著帳號走、換季照帶。
**商城**：一開始就在（Joy 11/25「能越快出來越好」），不在 `KEYS`。
**江湖頁上的區塊**歸「重排江湖頁」那一條：讀同一本，要加的鍵另外列給這一包。
**緊急關**：`Config.unfold.enabled` 關掉：`main.unfold` 沒了、全部攤開；存檔那一格照留。
