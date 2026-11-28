# 鐵匠鋪重排（`tianxia/features/tiepu/`）

- 做什麼：鐵匠鋪那一層照江湖頁、俠客頁的元件重排——圖頭（鋪子內景滿版、出店、銀兩、大字「鐵匠鋪」與朱印「鐵匠」）、鐵匠那一句、眼下一張卡（身上那件磨到一半以下→修；身上空著→架上配得上的那一件直接買；還能淬煉→淬煉；鈕都在卡上）、五面牌（打造是寬牌、畫爐口主料輔料兩格；架上、裝備庫、素材、神器譜），點一面從底下拉起那一塊。架上換成兩欄貨卡、身上那件的耐久與淬煉都畫長條（不畫小格子）、神器收藏冊是方格；打造、素材、裝備庫的列、神器的江湖已見沿用 smithy.js 畫的。只換畫法，規則不動。
- 開關：`Config.tiepu.enabled`（`tianxia/core/tuning/tiepu.py`），預設關，每個設定都還關著（Joy 2026-11-28「開始寫」是看了示意稿要做；打開要 Joy 看過真畫面）。
- 導覽：`docs/guide/地圖與介面.md` 的「鐵匠鋪重排」那一節
- 設計稿：示意稿 https://claude.ai/artifact/YZis3D5YXAbGCNWLD5KWZ6（原始檔 `/mnt/project-files/ui/smithy-redraw/`）
- 畫面：`web/tiepu.js`、`web/tiepu.css`；伺服器那一半只有 `status()` 回 `main.tiepu = {on: true}`（假人不帶）。沒有欄位、選項、路由。
- 殼的掛鉤：`web/app.js` 的 `shopHtml()` 一行 `typeof tpOn`。
- 測試：`tests/test_tiepu_smoke.py`、`tests/test_tiepu_web.py`。
