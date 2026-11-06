# 裝備（`tianxia/features/gear/`）

修練頁的換上、拆解（含批量）、餵馬，馬市的買、餵、換上，寄放的重賞與贈禮補送，名將贈禮，名將本命兵器，見聞榜單的神器譜。全部拆包第 42 批搬進來（引擎那一半；網頁那一半 `web/` 第 3 階才切，`app.js` 的 `gearEffect`、`gearCell`、`horseImg`、`marketHtml`、`horseCard` 歸第 65 批）。

**包名 `gear` 跟兩個同字的東西不是同一件事**：`tests/gear/` 是舊的測試資料夾（兵器、防具、坐騎、寶物、鐵匠鋪一起放，下面「混合檔」），`Content.gear` 是 `content/gear.json` 讀進來的 `GearBook`（寶物、名駒、贈禮、本命兵器的內容表）。這裡的 `gear` 是功能包。

- 導覽：`docs/guide/裝備與店面.md`（兵器、防具、坐騎、寶物、馬市、神器、本命兵器）。
- 設計稿：裝備四欄設計（5.5 馬市、2.3 換上、5.4 餵馬、6.4 名將贈禮、6.5 寄放、4.8 拆解）；兵器設計（`2026-10-09-兵器-design.md` 4.7.1 拆解、4.10 本命兵器）；打造隱藏配方設計 5.5 神器譜；鐵匠鋪與合成流程 3.4 批量拆解。
- 計畫：`docs/superpowers/plans/2026-11-07-裝備包-第1批.md`。

## 裡面有什麼

- `signature_arms.py`（原 `tianxia/signature_arms.py`，舊名留成指到這裡的 `sys.modules` 別名）：名將本命兵器的規則（情誼到門檻他送你、打贏本人 `signature_wins` 次他讓你奪走、神器譜的行、名字照內容讀 `refresh_names`）。
- `market_actions.py`：`market_options`（馬市第二層選單：買、餵、換上、離開）、`market`（選單上的選擇）、`enter`（`act:market` 進門）。
- `bench_actions.py`：`wield_weapon`、`feed_mount`、`dismantle_weapon`、`dismantle_many`（修練頁；`dismantle_many` 的 `@not_while_preparing` 在包的函式上）。
- `gift_actions.py`：`deliver_held_gear`（寄放補送）、`general_gifts`（名將贈禮）、`people_here`（此刻在身邊的人物）、`gift_entry`（贈禮另起一則江湖紀錄）、`signature_arms_due`（本命兵器）。
- `views.py`：`gear_rows`（修練頁裝備那一塊）、`divine_book_view`（見聞榜單的神器譜）。
- `bots.py`：假人看到 `market:` 的選項怎麼按（原本 `bot_policy.score` 的 market 兩行）；`MARKET_SCORE` 在這裡重寫一份同值常數（8.0），`bot_policy.MARKET_SCORE` 名字照舊。
- 掛鉤：`prefix = "market"`（`market:buy`、`market:feed`、`market:wield:<id>`、`market:back`）；`choose` 接 `market:*`（標題「馬市」）；`verbs()` 一個 `Verb("market")`（`run` 走進馬市、`title` 是「馬市・此地」，照舊寫江湖紀錄、不宣告 `picks`）；`content = ("gear.json",)`；`bot_pick`。**沒有路由**：`/api/menxia` 的 `wield`、`dismantle`、`feed`、`dismantle_many`、`menxia_view` 的 `gear` 鍵、`/api/boards` 的神器譜、`/api/board_card` 的裝備卡都留在殼，叫 `Game` 的委派。
- `enabled`：兵器、防具、坐騎、寶物四欄各看自己的 `enabled`（不看第一季開關，裝備四欄設計 2.6），**或此刻還坐在馬市裡**（開關在坐著的時候被關掉，照樣按得到離開）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields = ("picking_market",)`（馬市第二層選單開著）。
- `carried = ()`：換季全部跟著新角色重來。
- 不認領：`held_gear`（核心的 `PlayerState` 與共用層 `treasures` 都讀）、`figure_wins`（大勢人物包的）、`shop_line`／`shop_clue`／`shop_hold`（七間店共用，屬核心）。`Game._affinity_before`（`choose` 與核心 `event_check` 的 `answer_event`、`answer_branch` 寫、`people_here` 讀的暫時旗標）列在 `core/services.py` 四、寄放，屬性留在 `Game.__init__`。
- 動身被擋（`atlas.travel_block`）：第 56 批選單收接縫起這一包登記 `MENU_ORDER["block"]` 自己那一格，讀 `picking_market` 的只剩包裡；字與先後一字不動（`atlas` 不再讀）。

## 委派與留在原位的接縫

`Game` 留 11 個一行委派（`_market_options` 第 56 批換成 `take` 那一格，拿掉）：`_market`、`_people_here`（測試直接叫）、`wield_weapon`、`feed_mount`、`dismantle_weapon`、`dismantle_many`（server 的 `MENXIA_ACTIONS`、假人 `bot.feed_mount`／`bot.wear_better`）、`_general_gifts`、`_signature_arms`、`_gift_entry`（`choose` 後半與核心事件檢定叫；`_signature_arms` 還有大勢人物包的挑戰本人經 `ctx` 叫，列在 `core/services.py` 二、查詢服務）、`gear_rows`、`divine_book_view`（server）。

**店面登記（`Shop`）不登記，走 `MENU_ORDER`**（第 56 批選單收接縫定案，計畫第四節，理由同鐵匠鋪、懸賞榜）：入口先後 懸賞榜 → 鐵匠鋪 → 馬市是行為，`_shops` 照 `FEATURES` 走、酒肆與銀兩出口會排到前面；`close_shops` 只收坐著的，出發那一行不看坐不坐著（`shop_line` 不坐在店裡也要清）。所以這一包登記 `menus()` 的格：`take`、`here`、`idle`、`open`、`depart`、`block`，先後在 `MENU_ORDER`；`shop_view` 的 market 分支、`sync.close`、`stale.mid` 的收店（第 55 批）與 `choose` 裡 FB-195 被搶的那一句（`mounts.stale_problem`，在 `choose` 掛鉤之前）不動。

核心原位碰這一包的，邊界測試（`tests/core/test_feature_boundaries.py` 的 `# gear` 段）逐條記理由：
- `GAME_DELEGATE_CALLERS`：`choose → _general_gifts`、`_signature_arms`、`_gift_entry`（位置固定）。
- `CORE_DELEGATE_CALLERS`：`event_check.answer_event`、`answer_branch` 各叫 `_general_gifts`、`_signature_arms`、`_gift_entry`（事件檢定是核心本體，贈禮在效果套完之後）。
- `GAME_DIRECT`：`_drop_stale_references` 讀 `signature_arms.refresh_names`（經舊名別名；會改 `item.name`、要讀 `owned`）。接不了 `on_drop_stale` 的原因是開關、不是位置：`core/features.py` 的 `on_drop_stale` 只問開著的包，原位的 `refresh_names` 不看開關，四欄都關著時 `GearFeature.enabled` 是 False，接進掛鉤就不跑了（第 42 批 PM 認定第 1 條）；歸第 55 批（補算與換季收接縫），照第 40 批 `smith_base` 的前例把 `refresh_names` 放進共用層或核心的 `*_base` 再收。

## 讀 `content/gear.json` 的人

`content.py` 的 `check_gear`、`check_signature_arms` 留在 `content.py`、不接 `check_content`（第 34 批認定第 2 條：會動第一個錯誤的先後）。誰在讀 `Content.gear`：共用層 `treasures`、`tactics`；核心 `team`、`naming`、`content`；`SHARED_LATER` 的 `leaderboard`（`gear_card` 讀 `signature_arms`，函式裡經舊名別名）；`mounts` 不讀。

## 測試

- 包裡：`tests/test_gear_where.py`（修練頁每一段「哪裡買得到」，從內容讀地點）、`tests/test_gear_smoke.py`（煙霧：進馬市、買、離開，包的宣告，假人分數，修練頁委派）。
- **留原處**（被別的測試用裸名 import，照第 41 批認定第 6 條歸第 61 批）：`tests/gear/test_shop2.py`、`test_treasures.py`、`test_signature_arms.py`、`tests/web/test_shop2_web.py`。
- **網頁類，留原處**（第 3 階）：`tests/gear/test_horse_art.py`（import `server` 查 `web/`）、`test_shop_polish.py`（走網頁 harness）。
- **混合檔不拆**（一個檔裡有這一包的也有別包的）：`tests/gear/test_mounts.py`、`test_weapons.py`、`test_armor.py`、`test_board_cards.py`、`test_forge_divine.py`、`test_shop.py`，`tests/bots/test_bot_policy.py`、`tests/core/test_shop_width.py`、`tests/server/test_server.py`（`/api/boards` 的神器譜）、`tests/seal/test_seal.py`（`dismantle_weapon`）、`tests/season/test_sim_scripts.py`（量表腳本）。
- **另外要跑的**（`test_for` 不會因為改這一包挑到）：`tests/season/test_sim_scripts.py` 的 `measure_mounts`、`measure_treasures` 兩條 slow（量表腳本換掉的是 `mounts.buy`／`mounts.feed`、`treasures.gifts_due`／`treasures.deliver_held` 與 `Game.wield_weapon`，包裡一律照模組屬性叫，換得到）；`tests/server/test_server.py`、`tests/web/test_shop2_web.py`（殼與網頁）。
- 一起跑（包的 tests、上面的混合檔與「另外要跑的」；venv 的 python）：`python -m pytest -q -n 4 tianxia/features/gear/tests tests/gear/test_mounts.py tests/gear/test_weapons.py tests/gear/test_armor.py tests/gear/test_board_cards.py tests/gear/test_forge_divine.py tests/gear/test_shop.py tests/bots/test_bot_policy.py tests/core/test_shop_width.py tests/server/test_server.py tests/seal/test_seal.py tests/web/test_shop2_web.py`；量表兩條是 slow，另跑 `python -m pytest -q tests/season/test_sim_scripts.py -m "slow or not slow" -k "mounts_measure or treasures_measure"`。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.close`、`stale.mid` 的 `gear` 收馬市（`market_actions.close_gone`）；`sync.deliver`、`advance.held` 的 `held_gear` 補寄放（`gift_actions.deliver_held_gear`，位置固定在 `_deliver_big_events` 之後）。
