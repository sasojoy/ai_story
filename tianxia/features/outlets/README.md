# 銀兩出口與捐軍備（`tianxia/features/outlets/`）

大本營的軍需官那一串（捐素材、記貢獻與軍備存量、推大本營那一條線）、21 天季的「打點」那一間店（捐銀兩、醫館的名師指點與買破境丹、鐵匠鋪的看火候、此地大勢人物的打點門路與帳簿）。全部拆包第 43 批搬進來，行為一個字不變。

- 導覽：`docs/guide/裝備與店面.md`（打點與銀兩出口）、`docs/guide/行動與地盤.md`（捐軍備推大勢）。
- 設計稿：素材與經濟設計第六節（捐軍備）；正式季整合 6.5（銀兩出口）。
- 計畫：`docs/superpowers/plans/2026-11-05-銀兩出口包-第1批.md`。

## 裡面有什麼

- `donate_actions.py`：原本 `Game` 上的 9 個方法，第一個參數都是 ctx——`can_donate_here`（人在自家大本營、閒著或軍需官那一串開著）、`donate_option`（「此地還能做」裡的「捐軍備」）、
  `donate_options`（軍需官那一串）、`donate_choice`（`donate:back`、`donate:<素材>:<個數>`）、`donate`、`donate_items`（寫一則「捐軍備」紀錄）、`take`（收下：扣背包、記今天的點數）、
  `credit`（捐素材、捐銀兩共用：軍備存量、貢獻、推大本營那一條線）、`armament_view`（江湖頁的陣營軍備存量）。
- `silver_actions.py`：原本 `Game` 上的 8 個方法——`silver_options`（打點那一間店裡的幾樣）、`bribe_targets`、`silver_act`（五樣的分派）、`close_dadian`、`bribe`、`furnace`、`mentor`、`silver_donate`。
  `_at_clinic_town`（附錄甲裁核心）留在 `Game`，包裡經 ctx 叫。
- `bots.py`：假人看到 `donate:`、`dadian:` 的選項怎麼按（原本 `bot_policy.score` 的 dadian、donate 兩段）——萬一停在店裡只會離開。`act:donate`、`act:dadian` 的分數（None）是 act 子動詞，前綴 `act` 是核心的，留在 `bot_policy` 原位。
- 數字與字不在包裡：`tianxia/silver.py`（銀兩出口）、`tianxia/economy.py`（捐軍備）、店面那一頁的資料 `shopview.dadian_view`、`donate_view` 中 `shopview` 還沒收進 `registry.SHARED`（邊界測試的 SHARED_LATER），是過渡 import。
- 掛鉤：`prefix = ("donate", "dadian")`；`choose` 接 `donate:*`、`dadian:*`（標題在動作之前拿）；`bot_pick` 問 `bots.score`；`bot_always = ("donate:", "dadian:")`；
  `enabled`＝捐軍備開著、銀兩出口開著、或此刻還坐在其中一間店裡（開關在坐著時被關掉，離開還按得到）。
  `shops()` 兩間店（`donate`、`dadian`：坐在店裡的選單、哪一間開著、動身與此地不開了收店；`entry` 回 None）；`verbs()` 六個 act 子動詞（`donate`、`dadian`、`silver_donate`、`mentor`、`furnace`、`buy_legend`；
  標題只接 `donate`、`dadian` 兩間店的招牌，其餘四樣與 `bribe:<人物>` 的標題留在 `_action_title`）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`picking_donate`、`picking_dadian`（兩間店開著沒）、`donate_day`、`donated_today`（捐素材今天捐了多少點）、`silver_donate_day`、`silver_donated`（捐銀兩今天捐了幾兩）、`mentor_day`、`mentor_ready`（名師指點）、
  `furnace_day`、`furnace_ready`（看火候）、`legend_silver_bought`（這一季用銀兩買了幾顆破境丹）、`bribed`（今天打點過誰）。
- `carried = ("donate_day", "donated_today")`：換季不能多捐一輪（`Game._reset_player_for_new_season` 照帶，不看開關）；其餘換季跟著新角色重來。
- 不認領：`legend_items`（破境丹的數量）屬修練包、商城也帶；`shop_line`、`shop_clue`、`shop_hold`（七間店共用的掌櫃那一句）屬核心。
- `World.armaments`（各陣營軍備存量）是全服帳：由這一包的 `credit` 寫、狀態列的 `armament` 那一格（`status_slots`）經 `armament_view` 讀；沒有 `PlayerState` 欄位。
- 共用規則層的 `atlas.travel_block` 直接讀 `picking_dadian`、`picking_donate`（動身被擋的那一句；全部拆包第 50 批照實記下，第 56 批選單收接縫時改成掛鉤、一張先後表）。

## 委派與留在原位的接縫

`Game` 留 7 個一行委派（`can_donate_here`、`_donate_option`、`donate`、`donate_items`、`_silver_options`、`_bribe_targets`、`_silver_act`；`armament_view` 第 66 批拿掉）；其餘 9 個方法只有包裡叫，沒有委派。**沒有新增 `GAME_DIRECT`**。
核心原位接掛鉤的：`sync` 與 `_drop_stale_references`（`drop_shops`）、`_depart`（`close_shops`）、`_shop_open`、`_everyday_options` 坐在店裡的選單（`shop_menu`）、`_act`（`Verb.run`）、`choose`（`Outcome`）、`_action_title`（`Outcome.title`、`Verb.title`）。
留委派、記進 `GAME_DELEGATE_CALLERS` 的：

- `_everyday_options` 叫 `_donate_option`、`_silver_options`：「此地還能做」裡捐軍備與打點兩顆入口排在療傷之後，順序是行為（`/api/main` 的選項一顆一顆逐位元組）；若放進 `Shop.entry` 會跑到療傷前面。
- `_act` 叫 `_silver_act`：`act:bribe:<人物>` 帶後綴，`Verb` 認不得（總表第 57 批才擴）。
- `shop_view` 叫 `_bribe_targets`。
- 外面（server、假人）叫的：`donate`、`donate_items`（`/api/do/donate`）、`can_donate_here`（`bot.donate_spare`）。
- 網頁的畫法（`donatePicks`、`dadianHtml`、`donateHtml`、`donateCell`、`donateStep`、`donateTierOne`、`donateGo`）在 `web/outlets.js`（全部拆包第 65 批從 `app.js` 逐行切出來，110 行；`web = ("outlets.js",)`；計畫 `2026-11-06-網頁殼化-第65批.md`）。留在 `app.js`（殼）的：點擊分派的 `case`、店面的框（`shopHtml`、`shopNoteHtml`、`renderShop`）。樣子在 `style.css` 的店面那一段（`@media (min-width: 641px)` 用 `:where(.shop-layer)` 壓權重、靠先後蓋手機那幾條，第 67 批搬不動）。

## 測試

`tianxia/features/outlets/tests/`（整檔屬於這一包的，原樣搬來，只改路徑字串；`test_econ_donate` 多一個 `@pytest.mark.smoke`——手冊 4.1 每一包至少一條煙霧）：

- `test_silver_outlets.py`（15 條）：銀兩出口五樣（捐銀兩、名師指點、買破境丹、看火候、打點門路與帳簿）。
- `test_dadian_shop.py`（12 條）：「打點」那一間店（進、離開、五樣收在店裡、店面那一頁）；兩條讀 `web/style.css` 的字斷言規則，只讀不改。
- `test_econ_donate.py`（11 條）：捐軍備（軍需官那一串、每天上限、推大本營、江湖頁的軍備存量、假人只離開）。
- `test_silver_gates.py`（14 條）：**釘的是內容、不是這一包的程式**——真實內容裡選了就扣銀兩的事件選項都要帶 `min_stats.silver`，只讀 `content/events/`（總表附錄丙點名歸這一包；改事件內容時 `scripts/test_for.py` 照檔名挑到它）。
- `outlets_stage.py`：契約測試的擺局面（坐在軍需官那一串前）。「打點」那一間店不擺：它的選單有核心 `act:` 前綴的銀兩出口幾樣，契約測試要求這一包給的選項都帶自己的前綴。

**另外要跑的混合檔**（含這一包的測試，但檔案不屬於這一包，不拆）：

- `tests/gear/test_shop.py`：店面那一頁混合檔（鐵匠鋪、馬市、打點、軍需帳都在裡面）。
- `tests/bots/test_bot_policy_stuck.py`：假人卡在店裡那一類（含坐在軍需官、打點店裡只會離開）。
- `tests/web/test_econ_web.py`：捐軍備與軍備存量的網頁測試（網頁類，留原處）。改 `web/outlets.js` 時 `test_for` 照檔名挑得到它、`test_shop_width`、`test_shell_web`；挑不到、要另外跑的：`tests/server/test_server.py -k "page or version or scripts"`（那個檔太大，檔名刻意不寫進去）、`tests/bots/test_server_bots.py`（掃字）。
- `tests/figures/test_gentry_allied.py`：一條（`test_donate_goes_to_the_side_stock`，豪強捐軍備進依附那一軍的存量）。

## 過渡（手冊 3.11）

過渡 import 共 1 處（全部拆包第 40 批合完重印）：`donate_actions` 到 `shopview`。`silver_actions` 到 `figures` 那一處第 40 批 `figures` 收進共用規則層，不算過渡（原本 2 處）。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`status` 表 `armament`。
