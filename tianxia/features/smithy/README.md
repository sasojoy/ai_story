# 鐵匠鋪（`tianxia/features/smithy/`）

帶地盤福利的城鎮裡的一間店：架上買、修、淬煉、換上、拆解（兵器頁、防具頁），一步一步打造與店面直接開爐，打造的隱藏配方與鐵匠順口，神器原品定名與以器配招，素材頁的收購與升階，打造頁爐火的看火候。全部拆包第 41 批搬進來（引擎那一半），行為一個字不變。網頁的畫法在 `web/smithy.js`（第 65 批）。

- 導覽：`docs/guide/裝備與店面.md`（鐵匠鋪、兵器、防具、神器、打造隱藏配方）。
- 設計稿：`docs/superpowers/specs/2026-10-29-鐵匠鋪與合成流程*`、兵器設計（`2026-10-09-兵器-design.md`）、裝備四欄設計、素材與經濟設計（第四、五節：升階與收購）、打造隱藏配方設計。
- 計畫：`docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md`。

## 裡面有什麼

- `smithing.py`（原 `tianxia/smithing.py`）：打造與淬煉的規則——配方鍵、屬性、階、工錢、品質擲骰、名字、一步一步的單子（`SmithDraft`）、隱藏配方與神器原品、淬煉、定名、以器配招。**沒有模型**：整支的 docstring 寫「模型不碰打造」，神器定名是玩家自己打的名字（過 `naming.name_problem` 與 `forge_secrets.divine_name_problem`）或「沿用譜名」，不是三段式、沒有保底名，所以這一包不在鎖外、不用 `reset_model_budget`。
- `shelf_actions.py`：原本 `Game` 上的 8 個方法，第一個參數都是 ctx——`smith_options`（第二層選單：兵器頁、防具頁、素材頁，單子挑到一半換成那一步）、`dismantle_options`、`armor_options`、`smith_tail`、`trade_on`、`material_options`、`smith`（選單上的一下，做完擲一次鐵匠順口）、`smith_act`（切頁、買、修、換上、拆解、打造與淬煉的每一步、離開）；另外加一個 `enter`（`act:smith` 走進鐵匠鋪，原本 `Game._act` 中段那幾行）。
- `forge_actions.py`：`smith_forge_once`（一步一步的單子與店面直接開爐共用）、`smith_line`（打造頁預覽）、`smith_forge`（直接開爐，寫出爐卡 `ctx.smith_result`）、`smith_furnace`（看火候；叫同一支 `silver.furnace`）。
- `trade_actions.py`：`trade_sell`、`trade_upgrade`、`trade_open`、`smith_sell`、`smith_upgrade`（素材頁的收購與升階）。
- `gear_actions.py`：`repair_item`、`temper_item`、`gear_work`（修練頁裝備庫那一列的修與淬煉，走 `/api/menxia/…`）。
- `divine_actions.py`：`name_divine`、`bind_art`（`@_not_while_preparing` 裝飾器留在 `Game` 的委派上）。
- `clue.py`：`smith_clue`（鐵匠順口；包裡其餘各檔一律經 `ctx._smith_clue` 叫，因為測試換掉 `Game._smith_clue`）。
- `shop_view.py`：鐵匠鋪那一頁（第二輪第 93 批從 `shopview` 切來：`forged_card`、`next_rule`、`smith_line`、`trade_view`，`page` 是組法），`Feature.shop_view` 認 `smith`。
- `routes.py`：`/api/smith_line`（原本寫在 `server.py`；殼照 `FEATURES` 掛）與動作表（見最後一段）。
- `bots.py`：假人看到 `smith:` 的選項怎麼按（原本 `bot_policy.score` 的 smith 那一段）與 `want`（原本 `bot_policy._smith_want`）。`act:smith`（進鐵匠鋪）的分數第 60 批搬來（`enter`，`Verb.bot` 問；`bot.pick` 不按是 `Verb.bot_skip`）；`bot_policy._smith_want` 名字留著（一行委派到這裡，測試讀）。改 `bots.py` 的 `act:` 分數時另外跑 `tests/bots/test_bot_policy.py`、`tianxia/features/sortie/tests/test_bot_policy_conquest.py`、`tests/bots/test_bot_policy_stuck.py`（`test_for` 挑不到，第 60 批）。整季機器人與假人共用的底層（`bot.smith_want`、`forge_step`、`forge_ready`、`trade_at_smith`、`keep_book_names`）不搬，它們叫 `Game` 的公開方法。
- `web/smithy.js`（檔照手冊 G9 在 `web/`，`web = ("smithy.js",)`）：鐵匠鋪的畫法（全部拆包第 65 批從 `app.js` 逐行切出來，519 行；計畫 `2026-11-06-網頁殼化-第65批.md`）——`smithHtml`、架上 `shelfHtml`、打造 `forgePageHtml`（看火候 `furnace*`、就地熬 `brew*`、開爐與出爐卡 `revealHtml`、神器定名 `divineFormHtml`）、裝備庫 `rackHtml`、素材頁 `tradeHtml`、神器頁 `divineHtml`。點擊分派第二輪第 84 批進這支 js（`registerClicks`）；留在 `app.js`（殼）的：店面的框（`SHOP_ATTR`、`shopHtml`、`shopNoteHtml`、`shopDo`、`renderShop`、`shopPolled`）、`reduceMotion`。合成流程的樣子在 `web/smithy.css`（第 67 批，載入先後在 `index.html`）；架上的樣子在 `web/shop.css`（第 86 批整段切出來；殼，五包共用）。
- 掛鉤：`prefix = "smith"`；`choose` 接 `smith:*`（標題 `smithing.title(arg)`，在動作之前拿）；`verbs()` 一個 `Verb("smith")`（`run` 走進鐵匠鋪、`title` 是「鐵匠鋪・此地」）；`routes`；`content`（`forge_secrets.json`、`tier4_named.json`）；`bot_pick` 問 `bots.score`；`enabled`＝武器或防具開著、或此刻還坐在鐵匠鋪裡（開關在坐著時被關掉，離開還按得到；不看第一季開關）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`picking_smith`（店開著）、`smith_page`（停在哪一頁）、`smith_draft`（一步一步的單子）、`smith_rule`（這一次進門要講的神器規矩）、`smith_rules_told`（這一季講過的）。
- `carried = ()`：換季全部跟著新角色重來。
- 不認領：`shop_line`、`shop_line_seed`、`shop_hold`、`shop_clue`（七間店共用的掌櫃那一句，屬核心）、`furnace_day`／`furnace_ready`（看火候，銀兩出口包已認領）。`SmithDraft` 類別在核心 `state.py`。
- 動身被擋（`atlas.travel_block`）：第 56 批選單收接縫起這一包登記 `MENU_ORDER["block"]` 自己那一格，讀 `picking_smith` 的只剩包裡；字與先後一字不動（`atlas` 不再讀）。

## 委派與留在原位的接縫

`Game` 上的名字掛在 `game_api.py` 的表（`_smith_options` 第 56 批換成 `take` 那一格，拿掉）：`_smith`（`tianxia/features/gear/tests/test_shop2.py` 直接叫）、`_smith_clue`（測試換掉它）、`smith_line`、`smith_forge`、`smith_furnace`、`smith_sell`、`smith_upgrade`（`server.py` 的 `MAIN_ACTIONS`、整季機器人與假人、測試叫）、`repair_item`、`temper_item`、`name_divine`、`bind_art`（`MENXIA_ACTIONS`、假人、測試叫）；其餘 11 個方法只有包裡叫，沒有委派。

**店面登記（`Shop`）不登記，走 `MENU_ORDER`**（第 41 批計畫 1.9 量過，第 56 批選單收接縫定案，計畫第四節）：入口先後 懸賞榜 → 鐵匠鋪 → 馬市 → 搬成包的店是行為，`_shops` 照 `FEATURES` 走、酒肆與銀兩出口會排到前面；`here` 有兩個意思（`_shop_open` 要單子沒開著，收店要 `smith_open`），`Shop.here` 只有一個；`close_shops` 只收坐著的，出發那一行不看坐不坐著（`smith_page`、`smith_rule` 不坐在店裡也要清）。所以這一包登記 `menus()` 的格：`take`、`here`、`idle`、`open`、`depart`、`block`，先後在 `MENU_ORDER`；`shop_view` 的 smith 分支與 `sync.close`、`stale.mid` 的收店（第 55 批）不動。

核心原位讀 `smithing` 的三處記在邊界測試的 `GAME_DIRECT`：`choose`（打造那幾步併成一則：`GO_VERB`、`is_forge_step`、`is_step_line`；切頁不寫紀錄），`_drop_stale_references`、`sync`（`draft_here`、`draft_stale`，單子那一欄關了就清）。位置在寫紀錄與收店的中段，沒有對應的掛鉤。這三筆先認（第 41 批 PM 認定第 4 條）；**全部拆包第 40 批（核心批）收了**：五個純函式連同它們讀的常數（`ARMOR_KIND`、問句與回報那幾句）與 `here` 抽到核心小模組 `tianxia/core/smith_base.py`（照 `omen_base`），`smithing.py` 照原名 re-export 同一個物件；`engine` 的 `choose`、`_drop_stale_references`、`sync` 三處改讀 `smith_base`、不再 import `smithing`，邊界測試那三筆 `GAME_DIRECT` 還原（11 → 8）、`GAME_IMPORTS` 拿掉 `tianxia.smithing`（84 → 83）。

第二輪第 92 批：`choose` 那一處不再讀 `smithing`（切頁不寫、打造併成一則、開爐只留結果改由 `Outcome` 三格給：`shelf_actions.page_quiet`、`forge_merges`、`forged_fold`），只剩 `_drop_stale_references`、`sync` 兩處；`smith_result` 由這一包的 `scratch()` 宣告。

## 測試

`tianxia/features/smithy/tests/`（整檔屬於這一包、而且沒有別的測試檔 `from test_… import` 它的，原樣搬來，只改路徑字串）：

- `test_armor_forge.py`（47 條）：防具的打造與淬煉（一步一步的單子、直接開爐、品質、淬煉上限）。
- `test_weapons_forge.py`（73 條）：兵器的打造與淬煉、鐵匠鋪各頁。
- `test_econ_smith.py`（11 條）：素材與經濟第四、五節——鐵匠鋪的升階與收購（規則與選單、店面的資料）。
- `test_econ_clues.py`（10 條）：鑄譜線索拆成種類、主料、輔料三片，照天機分給各家鐵匠鋪（鐵匠順口那一擲）。
- `test_smithy_smoke.py`（2 條，`smoke`）：走進鐵匠鋪、買一把、切頁、離開；`/api/smith_line` 掛在殼上；假人的分數。

**第 61 批整檔搬來的**（被別的測試檔用裸名 `from test_… import` 拿 helper；`tests/conftest.py` 與 `tianxia/features/conftest.py` 都把每包的 `tests/` 放上 `sys.path`，照舊拿得到）：

- `test_shop.py`（59 條；`tests/core/test_shop_width.py`、`test_forge_divine.py`、`test_shop2.py`、`test_shop_polish.py`、`tianxia/features/smithy/tests/test_shop_web.py`、`test_shop2_web.py` 用它的 `_smith`、`_fire`）。
- `test_forge_secrets.py`（19 條；`test_forge_divine`、`test_shop`、`test_weapons` 用它的 `BLADE`、`_smith`、`forge_content`）、`test_forge_divine.py`（36 條；`test_board_cards`、`test_weapons`、`test_shop` 用它的 `_forger`、`divine_content`、`STAR`）。
- `test_divine_rotation.py`（14 條）與 `test_divine_collect.py`（6 條）；`test_shop2.py`、`tianxia/features/smithy/tests/test_smith_divine_web.py` 用 `test_divine_rotation` 的 `_smith`、`_forge_sword`。

這五個檔共 134 條，附錄甲歸這一包（第 44 批先搬 4 個檔，其餘第 61 批搬來）。`test_kiln_round.py`（讀全部的樣式與 `app.js`，煉製頁的開爐鈕）附錄甲也歸鐵匠鋪，第 61 批一起搬來。

**另外要跑的混合檔**（含這一包的測試，但檔案不屬於這一包，不拆）：

- `tests/gear/` 底下上面那七個，加 `test_armor.py`（44）、`test_weapons.py`（109）、`test_four_tiers.py`（47）、`test_board_cards.py`（11）、`test_renown_discount.py`（3）、`test_signature_arms.py`（25）、`test_shop2.py`、`test_shop_polish.py`。
- `tests/bots/test_bot_policy.py`（鐵匠鋪的分數、`_smith_want`）、`tests/core/test_economy.py`、`tests/core/test_shop_width.py`、`tests/season/test_sim_scripts.py`。
- `tianxia/features/cultivation/tests/test_ultimates.py`（`bind_art`）、`tests/server/test_server.py`（`/api/do/smith_*`、`/api/menxia/…`）、`tests/server/test_action_tables.py`（動作表的主人與先後）。
- 網頁（第 61 批搬進這一包的 `tests/`）：`tianxia/features/smithy/tests/test_kiln_round.py`、`tianxia/features/smithy/tests/test_smith_labels_web.py`（8）、`test_shop_web.py`（第 220 批起 slow 只剩兩條：`test_a_brew_cell_that_cannot_brew_only_says_why`、`test_a_furnace_you_cannot_afford_is_grey_and_says_why_when_tapped`）、`test_shop2_web.py`、`test_tier4_shop_web.py`（7）、`test_smith_divine_web.py`。改 `web/smithy.js` 時 `test_for` 照檔名挑得到 `test_shop_web`、`test_smith_divine_web`、`test_tier4_shop_web`、`test_shop2_web`、`test_econ_web`、`test_shop_width`、`test_shell_web`；挑不到、要另外跑的：`tests/server/test_server.py -k "page or version or scripts"`（那個檔太大，檔名刻意不寫進去；第 61 批搬走的 18 條只是名字帶 page，測的是各包自己的資料，不用跟）、`tests/bots/test_server_bots.py`（掃字）。

`scripts/same_behavior.py` 的 `smithy` 軌（`--tracks smithy`，三種設定）：整段、半舊半新、軌裡的假人段都跟搬之前一樣。

## import 的規矩（手冊 3.11）

包只 import 核心、共用層、自己這一包（第二輪第 102 批硬規矩，手冊 3.11，寫註也放行不了），沒有過渡 import。`smithing` 讀共用層 `fusion`（合成與揣摩；兩行，一行是 `QualityOdds`）。

**行狀記一筆讀核心**（第 41 批 PM 認定第 10 條）：`from tianxia.core import annal_base as annals`（包裡只用 `annals.note`、`annals.DEED`，都在記一筆那一半）。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.close` 的 `smithy`（`shelf_actions.sync_close`）、`stale.mid` 的 `smithy`（`shelf_actions.drop_stale`）：收店與清單子，**兩段條件不一樣，不合併**。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（「鐵匠鋪與神器」那一節），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`smith_forge`、`smith_sell`、`smith_upgrade`、`smith_furnace`；`menxia_actions`：`name_divine`、`bind_art`、`repair_item`、`temper_item`。`api_do` 回 `forged` 那一格（`op == "smith_forge"`）留在殼。 `name_divine`、`bind_art` 的 `Game` 的委派上掛著 `@_not_while_preparing`、包裡的函式沒有，所以表上那一條包 `not_while_preparing(lambda g, b: …)`（同一支裝飾器），籌備中的擋法不丟。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

- 改 `shop_view.py` 另外跑 `git grep -l smithy_shop -- tests tianxia/features` 列的那幾個（`test_for` 挑不到）。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_divine_collect.py`（原 `tests/gear/`）、`test_divine_rotation.py`（原 `tests/gear/`）、`test_forge_divine.py`（原 `tests/gear/`）、`test_forge_secrets.py`（原 `tests/gear/`）、`test_kiln_round.py`（原 `tests/core/`）、`test_shop.py`（原 `tests/gear/`）、`test_shop_web.py`（原 `tests/web/`）、`test_smith_divine_web.py`（原 `tests/web/`）、`test_smith_labels_web.py`（原 `tests/web/`）、`test_tier4_shop_web.py`（原 `tests/web/`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- `bots.py`：`smith_want`、`forge_step`、`_forge_plans`、`forge_ready`、`FORGE_SILVER_RESERVE`（第 89 批）、`visit_smith`、`trade_want`、`trade_at_smith`、`keep_book_names`、`_name_originals`、`TIER3_WANT`、`TIER4_WANT`、`TRADE_SILVER_RESERVE`、`DIVINE_NAME_CHANCE`（第 101 批）從 `bot` 搬來，舊名 re-export，換的要換 `smithy.bots` 那一份。
- `BIND_LINE`、`NAMED_LINE`、`bind_options`、`bound_alive`、`bond_lines` 第 88 批搬進 `core/smith_base`（`art_cards.gear_rows` 要讀），寫的 `bind_problem`、`bind_art` 留包裡，包 re-export。
- 另外要跑 `tests/gear/test_armor.py`（`bot.smith_want`）。另外要跑的：改這一包的 `bots.py` 時 `test_for` 挑不到 `tests/bots/test_bot.py`、`test_bot_policy.py`、`test_bot_runner.py`。
