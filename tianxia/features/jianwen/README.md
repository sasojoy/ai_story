# 見聞頁重排（`tianxia/features/jianwen/`）

- 做什麼：見聞頁照江湖頁、俠客頁的元件重排——圖頭滿版蓋「邸報」印、一句形勢、眼下一張卡、五面牌（戰況那面寬、畫三條戰線拔河，傳聞、江湖史、榜單、紀錄），點一面從底下拉起那一塊。戰況（大戰蓋印、一天一疊、勝敗印）、江湖史（凌煙閣與論劍壁並排、玉璽七片）、榜單（前三名站台、你那一行釘在底）換了新排法；點開一場戰報、一篇戰記照舊是原本那一頁。只換畫法，規則不動。
- 開關：`Config.jianwen.enabled`（`tianxia/core/tuning/jianwen.py`），預設關，每個設定都還關著（Joy 2026-11-27「好」是看了示意稿要做；打開要 Joy 看過真畫面）。
- 導覽：`docs/guide/地圖與介面.md` 的「見聞頁重排」那一節
- 設計稿：示意稿 https://claude.ai/artifact/GCMDJegGkmJWVHfpLFeeg7（原始檔 `/mnt/project-files/ui/news-redraw/`）
- 畫面：`web/jianwen.js`、`web/jianwen.css`；伺服器那一半只有 `status()` 回 `main.jianwen = {on: true}`（假人不帶）。沒有欄位、選項、路由。
- 殼的掛鉤：`web/app.js` 的 `pageNews()` 一行 `typeof jwOn`（自己的頁〔`selfNews`〕照舊）。
- 測試：`tests/test_jianwen_smoke.py`、`tests/test_jianwen_web.py`。
