# 見聞（`tianxia/features/news/`）

- 做什麼：見聞頁的畫法。籤只有一排五顆：戰況、傳聞、江湖史、榜單、紀錄。同一件事只放在一個地方，說明收起來，能點的排在前面，長的清單照日子分段、只攤開最近兩天。Joy 2026-11-08 對設計稿說「好」。
- 導覽：`docs/guide/地圖與介面.md` 的「見聞」那一節。
- 設計稿：https://claude.ai/artifact/9VhnyRHvSUWWST6iDgYtEx（沒有寫進 `docs/superpowers/specs/`）。
- 開關：沒有（`enabled` 回 `True`，跟戰記包一樣）。這一包只管畫法，不多一個遊戲行為、不多一個欄位。
- 內容：沒有內容檔。選項前綴：沒有。`player_fields = ()`、`carried = ()`。

## 東西在哪

- `web/news.js`：殼 `app.js` 的 `pageNews` 會叫這裡的小工具，包括 `newsDaysHtml`、`newsReportsHtml`、`newsFrontsHtml`、`newsXingshiHtml`、`newsRumorLayersHtml`、`newsChronicleHtml` 和 `newsJournalHtml`。頁面本身和籤還是留在殼裡。
- `web/news.css`：樣式一律用 `nw-` 開頭，顏色都讀 `style.css` 的變數。
- 伺服器那一半在核心 `tianxia/core/page_view.py`：
  - 江湖史的這一季照日子分段（`#### 第 N 週・週X`，後面每一行是「時刻　事」）。同一件事如果在江湖史和天下傳聞各記了一次，只留字多的那一句（`_history_days`、`_same_event`）。
  - 紀錄只留自己的事，去掉「江湖大事」，連著的前往併成一行「走了 N 段路」（`own_journal`）。

## 測試

`tianxia/features/news/tests/test_news_smoke.py`。畫面的測試寫在原本測那一塊的檔裡，例如 `test_rumor_layers.py`、`test_week7_season.py`、`test_conquest_web.py`、`test_showdown_full_report.py`、`test_engine.py`。

same_behavior 的軌是 facade、drape（讀到 `web/news.js`；Python 那一半每一軌都碰到、被共同組扣掉），兩軌都在 ALWAYS 六軌裡，`pick --covers news` 挑到 sortie、battle、progress、drape、facade、switchboard（第 111 批量的）。
