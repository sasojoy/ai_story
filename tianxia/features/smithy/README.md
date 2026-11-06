# 鐵匠鋪（`tianxia/features/smithy/`）

帶地盤福利的城鎮裡的一間店：架上買、修、淬煉、換上、拆解（兵器頁、防具頁），一步一步打造與店面直接開爐，打造的隱藏配方與鐵匠順口，神器原品定名與以器配招，素材頁的收購與升階，打造頁爐火的看火候。全部拆包第 41 批搬進來（引擎那一半），行為一個字不變。網頁那一半（`web/` 的鐵匠鋪畫面）第 3 階才切，這一批不碰。

- 導覽：`docs/guide/裝備與店面.md`（鐵匠鋪、兵器、防具、神器、打造隱藏配方）。
- 設計稿：`docs/superpowers/specs/2026-10-29-鐵匠鋪與合成流程*`、兵器設計（`2026-10-09-兵器-design.md`）、裝備四欄設計、素材與經濟設計（第四、五節：升階與收購）、打造隱藏配方設計。
- 計畫：`docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md`。

## 裡面有什麼

- `smithing.py`（原 `tianxia/smithing.py`，舊名留成指到這裡的 `sys.modules` 別名）：打造與淬煉的規則——配方鍵、屬性、階、工錢、品質擲骰、名字、一步一步的單子（`SmithDraft`）、隱藏配方與神器原品、淬煉、定名、以器配招。**沒有模型**：整支的 docstring 寫「模型不碰打造」，神器定名是玩家自己打的名字（過 `naming.name_problem` 與 `forge_secrets.divine_name_problem`）或「沿用譜名」，不是三段式、沒有保底名，所以這一包不在鎖外、不用 `reset_model_budget`。
- `shelf_actions.py`：原本 `Game` 上的 8 個方法，第一個參數都是 ctx——`smith_options`（第二層選單：兵器頁、防具頁、素材頁，單子挑到一半換成那一步）、`dismantle_options`、`armor_options`、`smith_tail`、`trade_on`、`material_options`、`smith`（選單上的一下，做完擲一次鐵匠順口）、`smith_act`（切頁、買、修、換上、拆解、打造與淬煉的每一步、離開）；另外加一個 `enter`（`act:smith` 走進鐵匠鋪，原本 `Game._act` 中段那幾行）。
- `forge_actions.py`：`smith_forge_once`（一步一步的單子與店面直接開爐共用）、`smith_line`（打造頁預覽）、`smith_forge`（直接開爐，寫出爐卡 `ctx.smith_result`）、`smith_furnace`（看火候；叫同一支 `silver.furnace`）。
- `trade_actions.py`：`trade_sell`、`trade_upgrade`、`trade_open`、`smith_sell`、`smith_upgrade`（素材頁的收購與升階）。
- `gear_actions.py`：`repair_item`、`temper_item`、`gear_work`（修練頁裝備庫那一列的修與淬煉，走 `/api/menxia/…`）。
- `divine_actions.py`：`name_divine`、`bind_art`（`@_not_while_preparing` 裝飾器留在 `Game` 的委派上）。
- `clue.py`：`smith_clue`（鐵匠順口；包裡其餘各檔一律經 `ctx._smith_clue` 叫，因為測試換掉 `Game._smith_clue`）。
- `routes.py`：`/api/smith_line`（原本寫在 `server.py`；殼照 `FEATURES` 掛）。
- `bots.py`：假人看到 `smith:` 的選項怎麼按（原本 `bot_policy.score` 的 smith 那一段）與 `want`（原本 `bot_policy._smith_want`）。`act:smith`（進鐵匠鋪）的分數在 `bot_policy` 的 `act:` 那一段（前綴 `act` 是核心的），繼續呼叫 `_smith_want`（一行委派到這裡）。整季機器人與假人共用的底層（`bot.smith_want`、`forge_step`、`forge_ready`、`trade_at_smith`、`keep_book_names`）不搬，它們叫 `Game` 的公開方法。
- 掛鉤：`prefix = "smith"`；`choose` 接 `smith:*`（標題 `smithing.title(arg)`，在動作之前拿）；`verbs()` 一個 `Verb("smith")`（`run` 走進鐵匠鋪、`title` 是「鐵匠鋪・此地」）；`routes`；`content`（`forge_secrets.json`、`tier4_named.json`）；`bot_pick` 問 `bots.score`；`enabled`＝武器或防具開著、或此刻還坐在鐵匠鋪裡（開關在坐著時被關掉，離開還按得到；不看第一季開關）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`picking_smith`（店開著）、`smith_page`（停在哪一頁）、`smith_draft`（一步一步的單子）、`smith_rule`（這一次進門要講的神器規矩）、`smith_rules_told`（這一季講過的）。
- `carried = ()`：換季全部跟著新角色重來。
- 不認領：`shop_line`、`shop_line_seed`、`shop_hold`、`shop_clue`（七間店共用的掌櫃那一句，屬核心）、`furnace_day`／`furnace_ready`（看火候，銀兩出口包已認領）。`SmithDraft` 類別在核心 `state.py`。
- 共用規則層的 `atlas.travel_block` 直接讀 `picking_smith`（動身被擋的那一句；全部拆包第 50 批照實記下，第 56 批選單收接縫時改成掛鉤、一張先後表）。

## 委派與留在原位的接縫

`Game` 留 12 個一行委派：`_smith_options`（核心原位選單叫）、`_smith`（`tests/gear/test_shop2.py` 直接叫）、`_smith_clue`（測試換掉它）、`smith_line`、`smith_forge`、`smith_furnace`、`smith_sell`、`smith_upgrade`（`server.py` 的 `MAIN_ACTIONS`、整季機器人與假人、測試叫）、`repair_item`、`temper_item`、`name_divine`、`bind_art`（`MENXIA_ACTIONS`、假人、測試叫）；其餘 11 個方法只有包裡叫，沒有委派。

**店面登記（`Shop`）這一批不登記**（計畫 1.9 量出四條）：「此地還能做」的入口順序是 懸賞榜 → 鐵匠鋪 → 馬市 → 搬成包的店，搬進登記就排到馬市後面（`/api/main` 的選項順序變）；選單順序同；`here` 有兩個意思（`_shop_open` 要單子沒開著，收店要 `smith_open`），`Shop.here` 只有一個；同一排的懸賞榜（第 45 批，`features/bounties`）、馬市（第 42 批，`features/gear`）成了包但同樣不登記，三間排給第 56 批。這些留在 `Game` 原位：`_everyday_options` 的 `picking_smith` 選單與 `act:smith` 入口、`_shop_open`、`shop_view` 的 smith 分支、`_drop_stale_references`／`sync` 的收店、`_depart` 的 `close_smith`、`_idle`。**PM 定案**（第 41 批 PM 認定第 1 條）：第 42 批（馬市）與第 45 批（懸賞榜）比較晚合的那一批，把懸賞榜、鐵匠鋪、馬市三間一起排進 `Shop`，入口先後維持 懸賞榜 → 鐵匠鋪 → 馬市（先後就是行為）；若非得讓 `Shop` 分兩個「此地」判斷（改核心）才行，先回報 PM。

核心原位讀 `smithing`（經舊名別名）的三處記在邊界測試的 `GAME_DIRECT`：`choose`（打造那幾步併成一則：`GO_VERB`、`is_forge_step`、`is_step_line`；切頁不寫紀錄），`_drop_stale_references`、`sync`（`draft_here`、`draft_stale`，單子那一欄關了就清）。位置在寫紀錄與收店的中段，沒有對應的掛鉤。這三筆先認（第 41 批 PM 認定第 4 條）；**全部拆包第 40 批（核心批）收了**：五個純函式連同它們讀的常數（`ARMOR_KIND`、問句與回報那幾句）與 `here` 抽到核心小模組 `tianxia/core/smith_base.py`（照 `omen_base`），`smithing.py` 照原名 re-export 同一個物件；`engine` 的 `choose`、`_drop_stale_references`、`sync` 三處改讀 `smith_base`、不再 import `smithing`，邊界測試那三筆 `GAME_DIRECT` 還原（11 → 8）、`GAME_IMPORTS` 拿掉 `tianxia.smithing`（84 → 83）。

## 測試

`tianxia/features/smithy/tests/`（整檔屬於這一包、而且沒有別的測試檔 `from test_… import` 它的，原樣搬來，只改路徑字串）：

- `test_armor_forge.py`（47 條）：防具的打造與淬煉（一步一步的單子、直接開爐、品質、淬煉上限）。
- `test_weapons_forge.py`（73 條）：兵器的打造與淬煉、鐵匠鋪各頁。
- `test_econ_smith.py`（11 條）：素材與經濟第四、五節——鐵匠鋪的升階與收購（規則與選單、店面的資料）。
- `test_econ_clues.py`（10 條）：鑄譜線索拆成種類、主料、輔料三片，照天機分給各家鐵匠鋪（鐵匠順口那一擲）。
- `test_smithy_smoke.py`（2 條，`smoke`）：走進鐵匠鋪、買一把、切頁、離開；`/api/smith_line` 掛在殼上；假人的分數。

**整檔屬於這一包、卻留在 `tests/gear/` 的**（被別的測試檔用裸名 `from test_… import` 拿 helper：搬走之後單獨跑 `tests/gear/test_shop2.py` 這類檔會找不到；`tianxia/features/conftest.py` 只在收 `tianxia/features` 底下的測試時才把每包的 `tests/` 放上 `sys.path`）：

- `test_shop.py`（59 條；`tests/core/test_shop_width.py`、`test_forge_divine.py`、`test_shop2.py`、`test_shop_polish.py`、`tests/web/test_shop_web.py`、`test_shop2_web.py` 用它的 `_smith`、`_fire`）。
- `test_forge_secrets.py`（19 條；`test_forge_divine`、`test_shop`、`test_weapons` 用它的 `BLADE`、`_smith`、`forge_content`）、`test_forge_divine.py`（36 條；`test_board_cards`、`test_weapons`、`test_shop` 用它的 `_forger`、`divine_content`、`STAR`）。
- `test_divine_rotation.py`（14 條）與 `test_divine_collect.py`（6 條）；`test_shop2.py`、`tests/web/test_smith_divine_web.py` 用 `test_divine_rotation` 的 `_smith`、`_forge_sword`。

這五個檔共 134 條，附錄甲歸這一包，這一批只搬了 4 個檔；其餘留到第 61 批（照第 44 批 PM 認定第 5 條「只搬一部分、其餘留到第 61 批」；第 41 批 PM 認定第 6 條認了）。`tests/core/test_kiln_round.py`（讀 `web/style.css` 與 `app.js`，煉製頁的開爐鈕）附錄甲也歸鐵匠鋪，屬網頁類，隨網頁第 3 階處理；歸屬（鐵匠鋪或 craft）待定，跟上面五個檔一起歸第 61 批（第 41 批 PM 認定第 6 條）。

**另外要跑的混合檔**（含這一包的測試，但檔案不屬於這一包，不拆）：

- `tests/gear/` 底下上面那七個，加 `test_armor.py`（44）、`test_weapons.py`（109）、`test_four_tiers.py`（47）、`test_board_cards.py`（11）、`test_renown_discount.py`（3）、`test_signature_arms.py`（25）、`test_shop2.py`、`test_shop_polish.py`。
- `tests/bots/test_bot_policy.py`（鐵匠鋪的分數、`_smith_want`）、`tests/core/test_economy.py`、`tests/core/test_shop_width.py`、`tests/season/test_sim_scripts.py`。
- `tests/arts/test_ultimates.py`（`bind_art`）、`tests/server/test_server.py`（`/api/do/smith_*`、`/api/menxia/…`）。
- 網頁（第 3 階才切）：`tests/core/test_kiln_round.py`、`tests/web/test_smith_labels_web.py`（8）、`test_shop_web.py`（61，slow 7）、`test_shop2_web.py`、`test_tier4_shop_web.py`（7）、`test_smith_divine_web.py`。

`scripts/same_behavior.py` 的 `smithy` 軌（`--tracks smithy`，三種設定）：整段、半舊半新、軌裡的假人段都跟搬之前一樣。

## 過渡（手冊 3.11）

過渡 import 共 5 行（shopview 兩處、fusion 兩行、bot；邊界測試的「包 → 舊模組」列 5 行）：`shelf_actions`、`forge_actions` 到 `shopview`（店面的畫面資料，邊界測試的 SHARED_LATER）、`smithing` 到 `fusion`（合成與揣摩，SHARED_LATER；兩行，一行是 `QualityOdds`）、`bots` 到 `bot`（整季機器人與假人共用的底層，總表歸「假人三支不搬」；函式裡延後 import）。

**行狀記一筆 import 核心**（第 41 批合併時改，第 41 批 PM 認定第 10 條）：開發時 `smithing` 是 `from tianxia import annals, fusion` 一行；第 29 批之二把行狀拆兩半之後，舊名 `tianxia.annals` 是指到列傳包 `standing.py` 的別名（經別名 import 就是包 import 包，邊界測試擋），合併時拆成兩行：`from tianxia import fusion`（過渡）與 `from tianxia.core import annal_base as annals`（核心本體，不算過渡；包裡只用 `annals.note`、`annals.DEED`，都在記一筆那一半）。
