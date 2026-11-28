# 萬寶閣重排（`tianxia/features/wanbao/`）

- 做什麼：萬寶閣那一層照江湖頁、俠客頁的元件重排（漆黑描金，淺色深色同一套）——頂上出店與錢袋（元寶拆兩種時金錠元寶、銀錠五銖，點了看紀錄）、圖頭（櫃上三件鎮店之寶、兩盞燈籠、大字「萬寶閣」與朱印「寶號」）、掌櫃那一句、眼下一張卡（月卡今天的份還沒領→領；手上沒丹→買最便宜的那一包，鈕在卡上）、五面牌（月卡是寬牌、畫還剩幾天的長條；丹藥、江湖帖、列傳、形象），點一面從底下拉起那一類。貨一件一張大卡、圖當主角，按下去照舊走 mall.js 的購買確認；只收儲值元寶的蓋「儲」。形象、紀錄沿用 looks.js、mall.js 畫的。只換畫法，規則不動；元寶拆不拆（`Config.mall.two_coins`）兩種都對。
- 開關：`Config.wanbao.enabled`（`tianxia/core/tuning/wanbao.py`），預設關，每個設定都還關著（Joy 2026-11-28「開始寫」是看了示意稿要做；打開要 Joy 看過真畫面）。
- 導覽：`docs/guide/商城.md` 的「萬寶閣重排」那一節
- 設計稿：示意稿 https://claude.ai/artifact/CDHtTZW5yKHQAQbferUPGz（原始檔 `/mnt/project-files/ui/mall-redraw/`）
- 畫面：`web/wanbao.js`、`web/wanbao.css`；伺服器那一半只有 `status()` 回 `main.wanbao = {on: true}`（假人不帶）。沒有欄位、選項、路由。
- 殼的掛鉤：`web/app.js` 的 `shopHtml()` 一行 `typeof wbOn`。
- 測試：`tests/test_wanbao_smoke.py`、`tests/test_wanbao_web.py`。
