# 凌煙閣（`tianxia/features/lingyan/`）

- 做什麼：跨季的名人堂。每一季收季之後，把那一季最出眾的人掛上閣（一季一卷、一個人一格），往後每一季都看得到。開關 `Config.lingyan.enabled`（`tianxia/core/tuning/lingyan.py`）預設關，week7、season21 都還沒開。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「凌煙閣」那一節
- 設計稿：玩家一起玩設計稿第三節甲「凌煙閣」（https://claude.ai/artifact/J2hWqymn9SXRgw1qashgKb，Joy 2026-11-26「做」）

## 不另存一份

閣裡的東西全部從**已經跨季存著**的紀錄算出來（`hall.py`），不開收季掛鉤、不加存檔欄位、不加資料表、資料庫不升版：

| 事蹟 | 讀哪裡 |
|---|---|
| 天下第一 | 那一季 `seasons` 列的 `WorldState.arena` 季末名次 `place == 1`（擂台包收季時寫） |
| 論功第一 | 那一季的 `WorldState.final_tiers` 每一本帳第一名、有階（四勝利開著的季才有） |
| 決戰首功 | 那一季收場的決戰（`battles` 表，`season_ended_battles`），兩軍各自的首功同決戰包 `instance.top_merit`（`hall.top_merit` 照核心 `battle_base.merit` 另寫一份），次數最多的那一位 |
| 名動天下、一代宗師、武冠群倫、仁義第一、惡名第一 | 收季時寫進江湖史的榜單那一行（`leaderboard.chronicle_lines`）的第一名 |
| 絕學首成 | 那一季江湖史第一則「某某把【甲】練成絕學，為之定名【乙】。」（修練包 `cultivation.py`） |
| 評曰 | 那一季的列傳（`biographies` 表）公開分享中的，取「評曰」那一段，連到 `/zhuan/<代碼>` |

所以以前收過的季也排得出來，程式上線前就收掉的季上線後照樣掛上去。江湖史的兩種句子（榜單那一行、絕學那一句）改寫法要連這一包的 regex 一起改（`hall.BOARD_LINE`、`MASTER_LINE`，`tests/test_lingyan.py` 寫死了樣子）。同一個人（名號 casefold）一季一格，第幾次上閣照季數往前數。假人跟真人一樣排、畫面看不出來；閣上只寫名號與事蹟，不寫等級與身家。

## 畫面

- `/lingyan`：整頁 HTML（`hall_html.py`，同列傳公開頁的做法，讀 `/static/style.css` 的色票，深色自動跟）。**沒登入也看得到**（Joy 2026-11-26 在決定卡上選「沒登入也看得到」，可以直接貼網址給朋友）：開關先問，關著 404；登入的人頂上是「‹ 回江湖」，沒登入的是「也去江湖走一遭 ›」。登記在 `tests/core/shell_tables.py` 的 `NO_LOGIN_ROUTES`。頁上只有名號與事蹟，不寫任何看得出是誰在玩的東西。
- 入口：見聞「江湖史」最上面一張（`web/lingyan.js` 的 `lingyanEntryHtml`，`web/app.js` 江湖史那一支照 `typeof` 叫；`web/lingyan.css`）。江湖畫面開著時多一格 `lingyan: true`（`Feature.status`），關著一個鍵都不多。
- 頁首圖暫用 `web/img/events/academy.webp`，之後要一張凌煙閣本身的圖（`hall_html.HERO`）。

## 測試

`tests/test_lingyan.py`（排法、第二次上閣、換季之後舊季照讀、評曰與連結、首功、跳脫、路由）、`tests/test_lingyan_smoke.py`。另外要跑：`tests/core/test_shell_stays_thin.py`、`tests/web/test_webqa.py -k coverage`（`web/lingyan.js` 列在 `scripts/webqa/gate.py` 的 `NOT_ON_TABLE`：開關關著沒有回合走得到，打開時重建 coverage.json）。
