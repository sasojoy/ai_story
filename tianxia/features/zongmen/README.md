# 門派（`tianxia/features/zongmen/`）

- 做什麼：門派是一群人一起寫的。這一包管拜入、叛出、門派身分跨季帶著走，與師門武譜（同門獻式、試練、入譜、學式；第三批收武學、重學打折、外人截殺親傳撿殘頁）。開關 `Config.zongmen.enabled`（`tianxia/core/tuning/zongmen.py`，預設關）。
- 導覽：`docs/guide/散人與玩家互動.md` 的「門派」那一節
- 設計稿：門派重想 v6 卷二（Artifact 9oVGtgs9mFApXsqVqf9Kis；Joy 2026-11-08「不錯，按照設計稿動工」）
- 模組：`rules.py`（拜入、叛出、山門、第一式）、`book.py`（武譜的純規則：要幾人試練、入譜、學到的那份低一品）、`actions.py`（選項、動作、換季帶身分、畫面資料）、`bots.py`（假人照雜湊拜入與試練）、`routes.py`（`zongmen_offer`、`zongmen_learn`）。
- 畫面：`web/zongmen.js` 的 `zongmenHtml` 畫在俠客頁「門下」（`web/cultivation.js` 叫一次，沒有 `zongmen` 資料就不畫）。
- 掛鉤：事件 `raid_win` 的 `zongmen` 格（`actions.raid_win`，撿殘頁）。
- 測試：`tests/test_zongmen.py`、`tests/test_zongmen_book.py`、`tests/test_zongmen_pages.py`。
