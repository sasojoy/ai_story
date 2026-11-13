# 江湖錄（`tianxia/features/codex/`）

- 做什麼：俠客頁多一顆分頁「江湖錄」。**奇遇**：這一季開過的奇事與主線（正在走的寫下一步去哪、還有幾天，點進去看走過的每一幕、重讀全文；收了的寫結局，女子寫她留在哪、一顆鈕帶你去），往季收過的，還沒遇上的只留剪影＋地名。**圖鑑**：人物（有立繪的；見過才亮）、器物（寶物、坐騎、名兵、素材；拿過就算）、神品意境（十路四型一張表，寫你取的名字）、結局。紅點三層：俠客分頁、江湖錄分頁（＋奇遇／圖鑑那一段、那一類）、那一件那一格。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「江湖錄」那一節
- 設計稿：https://claude.ai/artifact/NjCLieeD5AgvWhpL5y3zL2（v1；Joy 2026-11-13「做」，三個決定照建議：跟帳號走、剪影＋地名、收滿給頭銜〔頭銜那一條還沒做，要跟稱號包接〕）
- 開關：`Config.codex.enabled`（預設關，`tianxia/core/tuning/codex.py`）；路由 `/api/codex`、`/api/codex/scene`、`/api/codex/seen` 關著 404。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：on_sync、after_action（讀新的江湖紀錄與身上的東西）、on_season_start（整本照帶）、status（只帶紅點）、routes |
| `rules.py` | 純規則：從江湖紀錄的標題（「事件・選項」「事件・隨口應對」）認出是哪一條線哪一段選了第幾個（`scan_journal`）、線新開與收了（`scan_lines`）、見過的人、拿過的東西、神品（`scan_owned`）；重讀照內容檔重組全文（`scene_text`，記號用那一下存的那一份） |
| `view.py` | 畫面資料：奇遇（`quests`）、一幕（`scene`）、結局全文（`ending_text`）、圖鑑四類、紅點（`status`、`seen`） |
| `routes.py` | `GET /api/codex`、`GET /api/codex/scene?i=` 或 `?line=&end=`、`POST /api/codex/seen {keys}` |
| `web/codex.js`、`web/codex.css` | 畫面（俠客頁的分頁由 `web/cultivation.js` 照 `S.main.codex` 加在最後） |
| `tests/` | `test_codex.py`（引擎）、`test_codex_web.py`（網頁）、`test_codex_smoke.py` |

**認領的欄位**：`PlayerState.codex`（`CodexBook`：scenes、ended、people、things、gods、upto、upto_keys、fresh）。存的是序號與 id，全文從內容檔重組；隨口應對存那一下的全文（模型寫的，重組不回來）。
**跟著帳號走**：開關開著時在 `on_season_start` 整本照帶（不在 `carried`：`season.carry` 那一格是核心的表）。**開關關著的那一次換季不帶**（退版風險寫在 PR）。
**第一次打開**：照存檔補（江湖紀錄裡還在的最近 30 則、這一季的線、身上的東西、交情有分數的人），不亮紅點。補不回來的是開關打開之前、已經不在江湖紀錄裡的那幾幕選了哪一句。
**不寫進**：行狀、列傳、傳聞。假人不記。
**緊急關**：`Config.codex.enabled` 關掉：分頁消失、路由 404、存檔的那一格照留。
