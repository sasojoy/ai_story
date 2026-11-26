# 俠客頁重排（`tianxia/features/xiake/`）

- 做什麼：俠客頁照江湖頁重排的元件重排——人像滿版、眼下一張卡、六面牌（武學、裝備、同伴、師門、屬性、江湖錄），點一面從底下拉起那一塊；同伴排成立繪方格、點一位拉起他的卡。只換畫法，規則不動。
- 開關：`Config.xiake.enabled`（`tianxia/core/tuning/xiake.py`），預設關，三種設定都不開；上正式站等 Joy 說。
- 導覽：`docs/guide/地圖與介面.md` 的「俠客頁重排」那一節
- 設計稿：示意稿 https://claude.ai/artifact/QYC9xRw99gfH3ULcRLxLJC（Joy 2026-11-26「好 很棒」；原始檔 `/mnt/project-files/ui/hero-redraw/mock/index.html`）
- 畫面：`web/xiake.js`、`web/xiake.css`；伺服器那一半 `view.py`（`main.xiake`）。
- 測試：`tests/test_xiake_smoke.py`、`tests/test_xiake_web.py`。
