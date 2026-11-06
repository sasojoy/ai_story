# 招募同伴（`tianxia/features/hire/`）

- 做什麼：五項屬性的季（`attrset.on`：`Config.attributes.v2` 開著、開季蓋了章），歷史武將不再同行，同伴改在城裡的酒肆花銀兩招一般 NPC。五型：刀客、槍手、弓手、醫者、謀士（`Config.hire.types`，資質 2～9）。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「招募同伴」那一節
- 設計稿：屬性與跨季架構 v2 第九節（`docs/superpowers/specs/2026-11-04-屬性與跨季-架構方向v2.md`）；企劃者 2026-11-04 照建議（酒肆花銀兩、名字隨機）

## 裡面有什麼

- `actions.py`：「此地還能做」裡每一型一顆（此地酒肆那一型還沒有主的第一位）；銀兩不夠、名下滿了（`Config.companions.max_owned`）灰掉。按下去付 `Config.hire.cost` 兩、`try_recruit`（全服唯一、名下上限在同一筆寫入裡判）、配起始武學、入隊。
- 人：`content/hire.json`，`scripts/make_hirelings.py` 照 `Config.hire` 生（每間帶「酒肆」標籤的地點每型 `per_tavern` 位；名字姓加兩字隨機、種子固定；屬性照資質換成舊四項，跟人物表一樣 2～9）。改了型或酒肆就重跑；`--check` 比對。內容的 `hire_type`、`hire_at` 由 `content.validate` 驗。
- 放走：修練頁名冊的「放他回江湖」照舊（核心 roster）；換季跟其他同伴一樣重獲自由。
- 假人：按得下去就給 `BOT_SCORE`。

## 測試

- `tests/test_hire_smoke.py`（3 條，1 條 smoke）。
