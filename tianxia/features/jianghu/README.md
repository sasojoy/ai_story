# 江湖頁重排（`tianxia/features/jianghu/`）

- 做什麼：江湖頁閒著時的新排法（Joy 2026-11-25「方向對」、決定卡「開始做，先不上線」）：滿版場景圖、圖上的狀態一行、地名與小印、旁白、眼下一張卡、四顆行動牌、這裡的人、這裡的去處。開關 `Config.jianghu.enabled` 預設關、三種設定都不開；開著時伺服器送 `main.jianghu`，`web/main.js` 的 `pageJianghu` 問 `jhOn`，是真就交給 `web/jianghu.js` 的 `jhPageHtml`（序章、初入江湖、路上、決戰、事件與對話照舊）。
- 分批：施工單 `/mnt/project-files/ui/jianghu-redraw/施工單-江湖頁重排-2026-11-25.md`（專案共用資料夾）。第一批骨架做完；第二批眼下卡、第三批人、第四批去處與軍務與行路、第五批事件與趕路、第六批其餘時刻與新角色。
- 導覽：`docs/guide/地圖與介面.md` 的「江湖頁重排」那一節
- 設計稿：畫面稿 v5（Artifact UuBPHmxo3KXiieCL5qaixh；原始檔在專案共用資料夾 `ui/jianghu-redraw/mock.html`，h～n 是定案方向）
- 測試：`tests/test_jianghu_web.py`（開著換排法、關著與路上照舊、假人不送）
