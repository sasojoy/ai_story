# 結義（`tianxia/features/jieyi/`）

- 做什麼：玩家跟玩家結義（最多 5 人），跟陣營、門派無關，換季不散。邀在玩家卡、回在江湖頁「結義之邀」、名冊、義聚與割袍斷義在名帖匣裡的金蘭帖。結義能幹嘛（義不相殘、替兄出頭、名分、義聚、並肩作戰）看導覽「結義」那一節。
- 導覽：`docs/guide/散人與玩家互動.md` 的「結義」那一節
- 設計稿：宗門系統設計稿 v2 卷一 https://claude.ai/artifact/9oVGtgs9mFApXsqVqf9Kis（Joy 2026-11-07「甲先不做……先做丙，跨季保留關係」）
- 開關：`Config.jieyi.enabled`（預設關；數字在 `tianxia/core/tuning/jieyi.py`）

## 裡面有什麼

- `rules.py`：純規則（誰在哪一組、能不能邀、答應、割袍斷義、名號與排行、義譜）。
- `actions.py`：玩家卡「邀他結義」（載入這一包就登記進核心 `cards.ACTIONS`，order 18）、選單上的答應／婉拒（`options`）、`choose` 的回話、割袍斷義、給畫面的 `view`。
- `bots.py`：假人收到結義邀請的回法（`bot_pick`）。
- `routes.py`：`/api/do/jieyi_leave`（`main_actions`）。
- 畫面：`web/jieyi.js`（`jieyiHtml` 俠客頁門下那一段、`jieyiOfferHtml` 江湖頁的結義之邀）、`web/jieyi.css`。

## 認領的欄位

- 沒有 `PlayerState` 欄位。全服帳：`SharedWorldState.jieyi`（`JieyiBook`，核心 `world_state.py`；不分季，換季不清，空的不寫鍵）。

## 接在別處的

- `web/peers.js`：名帖匣（`mingtieBoxHtml`）接 `jieyiHtml`（`typeof` 擋）；玩家卡、名帖畫 `jieyi`（義名排行）。
- `web/main.js`：介面重整版面在場景卡底下接 `jieyiOfferHtml`；`FIG_ACT` 濾掉 `jieyi:yes:`、`jieyi:no:`（義聚照常進此地可為）。
- 核心 `core/jieyi_base.py`：玩家互動包（截殺、名帖、玩家卡）、懸賞榜包（通緝）、決戰包（戰報）、`core/combat.battle_marks`、`core/battle_base.merit` 讀它。
- 設伏包 `ambush_actions`：伏兵打贏記仇。
- `tianxia/features/peers/tests/test_social.py`：卡上動作的排序多一格 `(18, "jieyi")`。

## 測試

- `tests/test_jieyi_uses.py`（12 條）：義不相殘、通緝、替兄出頭與追回銀兩、仇過期、義名排行、江湖史與列傳、義聚、並肩作戰。
- `tests/test_jieyi.py`（8 條）：互換名帖才邀得了、關著不出聲、婉拒、第三人入義與滿員、割袍斷義的冷卻與剩一人就散、換季不清、空帳不寫鍵、假人的回法。
- same_behavior 一軌 oath（`scripts/sb/tracks/oath.py`）。
