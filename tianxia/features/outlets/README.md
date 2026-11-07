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
- `bots.py`：假人看到 `donate:`、`dadian:` 的選項怎麼按（原本 `bot_policy.score` 的 dadian、donate 兩段）——萬一停在店裡只會離開。`act:donate`、`act:dadian`（第 60 批接進 Verb）：`bot` 回 None（假人不進）、`bot_skip`（整季機器人不按）；`silver_donate`、`mentor`、`furnace`、`buy_legend`、`bribe:` 不寫，照舊落到 `ACT_SCORES` 的 0.0（隨機挑得到，不是不按）。
- 數字與字不在包裡：`tianxia/silver.py`（銀兩出口）、`tianxia/economy.py`（捐軍備）、店面那一頁的資料 `shopview.dadian_view`、`donate_view` 中 `shopview` 還沒收進 `registry.SHARED`（邊界測試的 SHARED_LATER），是過渡 import。
- 掛鉤：`prefix = ("donate", "dadian")`；`choose` 接 `donate:*`、`dadian:*`（標題在動作之前拿）；`bot_pick` 問 `bots.score`；`bot_always = ("donate:", "dadian:")`；
  `enabled`＝捐軍備開著、銀兩出口開著、或此刻還坐在其中一間店裡（開關在坐著時被關掉，離開還按得到）。
  `shops()` 兩間店（`donate`、`dadian`：坐在店裡的選單、哪一間開著、動身與此地不開了收店；`entry` 回 None）；`verbs()` 六個 act 子動詞（`donate`、`dadian`、`silver_donate`、`mentor`、`furnace`、`buy_legend`；
  標題只接 `donate`、`dadian` 兩間店的招牌，其餘四樣與 `bribe:<人物>` 的標題留在 `_action_title`）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`picking_donate`、`picking_dadian`（兩間店開著沒）、`donate_day`、`donated_today`（捐素材今天捐了多少點）、`silver_donate_day`、`silver_donated`（捐銀兩今天捐了幾兩）、`mentor_day`、`mentor_ready`（名師指點）、
  `furnace_day`、`furnace_ready`（看火候）、`legend_silver_bought`（這一季用銀兩買了幾顆破境丹）、`bribed`（今天打點過誰）。
- `carried = ("donate_day", "donated_today")`：換季不能多捐一輪（`season.carry` 的 `outlets` 那一格照帶，第 55 批；不看開關）；其餘換季跟著新角色重來。
- 不認領：`legend_items`（破境丹的數量）屬修練包、商城也帶；`shop_line`、`shop_clue`、`shop_hold`（七間店共用的掌櫃那一句）屬核心。
- `World.armaments`（各陣營軍備存量）是全服帳：由這一包的 `credit` 寫、狀態列的 `armament` 那一格（`status_slots`）經 `armament_view` 讀；沒有 `PlayerState` 欄位。
- 動身被擋（`atlas.travel_block`）：第 56 批選單收接縫起這一包登記 `MENU_ORDER["block"]` 自己那一格，讀 `picking_dadian`、`picking_donate` 的只剩包裡；字與先後一字不動（`atlas` 不再讀）。

## 委派與留在原位的接縫

`Game` 上的名字掛在 `game_api.py` 的表（`can_donate_here`、`_donate_option`、`donate`、`donate_items`、`_silver_options`、`_bribe_targets`、`_silver_act`；`armament_view` 第 66 批拿掉）；其餘 9 個方法只有包裡叫，沒有委派。**沒有新增 `GAME_DIRECT`**。
核心原位接掛鉤的：`sync` 與 `_drop_stale_references`（`drop_shops`）、`_depart`（`close_shops`）、`_shop_open`、`_everyday_options` 坐在店裡的選單（`shop_menu`）、`_act`（`Verb.run`）、`choose`（`Outcome`）、`_action_title`（`Outcome.title`、`Verb.title`）。
留委派、記進 `GAME_DELEGATE_CALLERS` 的：

- `_everyday_options` 叫 `_donate_option`、`_silver_options`：「此地還能做」裡捐軍備與打點兩顆入口排在療傷之後，順序是行為（`/api/main` 的選項一顆一顆逐位元組）；若放進 `Shop.entry` 會跑到療傷前面。
- `act:bribe:<人物>`：第 57 批接進 `Verb` 的 `tail_run`、`tail_title`（走銀兩四樣同一支 `press`），四樣的標題也接進 `Verb.title`，核心不再有銀兩那幾行。
- `shop_view` 叫 `_bribe_targets`。
- 外面（server、假人）叫的：`donate`、`donate_items`（`/api/do/donate`）、`can_donate_here`（`bot.donate_spare`）。
- 網頁的畫法（`donatePicks`、`dadianHtml`、`donateHtml`、`donateCell`、`donateStep`、`donateTierOne`、`donateGo`）在 `web/outlets.js`（全部拆包第 65 批從 `app.js` 逐行切出來，110 行；`web = ("outlets.js",)`；計畫 `2026-11-06-網頁殼化-第65批.md`）。點擊分派第二輪第 84 批進這支 js（`registerClicks`）；留在 `app.js`（殼）的：店面的框（`shopHtml`、`shopNoteHtml`、`renderShop`）。樣子在 `web/shop.css`（第 86 批整段切出來，排在 `style.css` 正後面；殼，五包共用）。

## 測試

`tianxia/features/outlets/tests/`（整檔屬於這一包的，原樣搬來，只改路徑字串；`test_econ_donate` 多一個 `@pytest.mark.smoke`——手冊 4.1 每一包至少一條煙霧）：

- `test_silver_outlets.py`（15 條）：銀兩出口五樣（捐銀兩、名師指點、買破境丹、看火候、打點門路與帳簿）。
- `test_dadian_shop.py`（12 條）：「打點」那一間店（進、離開、五樣收在店裡、店面那一頁）；兩條讀 `web/shop.css` 的字斷言規則，只讀不改。
- `test_econ_donate.py`（11 條）：捐軍備（軍需官那一串、每天上限、推大本營、江湖頁的軍備存量、假人只離開）。
- `test_silver_gates.py`（14 條）：**釘的是內容、不是這一包的程式**——真實內容裡選了就扣銀兩的事件選項都要帶 `min_stats.silver`，只讀 `content/events/`（總表附錄丙點名歸這一包；改事件內容時 `scripts/test_for.py` 照檔名挑到它）。
- `outlets_stage.py`：契約測試的擺局面（坐在軍需官那一串前）。「打點」那一間店不擺：它的選單有核心 `act:` 前綴的銀兩出口幾樣，契約測試要求這一包給的選項都帶自己的前綴。

**另外要跑的混合檔**（含這一包的測試，但檔案不屬於這一包，不拆）：

- `tianxia/features/smithy/tests/test_shop.py`：店面那一頁混合檔（鐵匠鋪、馬市、打點、軍需帳都在裡面）。
- `tests/bots/test_bot_policy_stuck.py`：假人卡在店裡那一類（含坐在軍需官、打點店裡只會離開）。
- 網頁：`test_econ_web.py`（捐軍備與軍備存量）第 61 批搬進這一包的 `tests/`。改 `web/outlets.js` 時 `test_for` 照檔名挑得到它、`test_shop_width`、`test_shell_web`；挑不到、要另外跑的：`tests/server/test_server.py -k "page or version or scripts"`（那個檔太大，檔名刻意不寫進去；第 61 批搬走的 18 條只是名字帶 page，測的是各包自己的資料，不用跟）、`tests/bots/test_server_bots.py`（掃字）。
- `tests/figures/test_gentry_allied.py`：一條（`test_donate_goes_to_the_side_stock`，豪強捐軍備進依附那一軍的存量）。

## 過渡（手冊 3.11）

過渡 import 共 1 處（全部拆包第 40 批合完重印）：`donate_actions` 到 `shopview`。`silver_actions` 到 `figures` 那一處第 40 批 `figures` 收進共用規則層，不算過渡（原本 2 處）。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`season.carry` 的 `outlets`（今天捐過的照帶，不看開關）。

**第 56 批（選單收接縫，核心批）**：`here/donate`、`here/dadian`、`idle/outlets`、`block/outlets` 是這一包登記的格；先後在 `core/features.py` 的 `MENU_ORDER`；委派 `_donate_option`、`_silver_options` 拿掉；上面寫「留委派」「原位」的以這一句為準。

**第 57 批（分派與標題收接縫，核心批）**：委派 `_silver_act` 拿掉（上面「留 8 個」以這一句為準），engine 不再 import `silver`。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（「素材的出路」那一節），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`status` 表 `armament`。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`donate`（`shell.donate_items` 整理網頁送來的 `items`，留在殼：測試叫 `server.donate_items`）。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_econ_web.py`（原 `tests/web/`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- `bots.py` 多 `donate_want`、`donate_spare`（第 101 批）；`econ_day` 走服務清單。另外要跑的：改這一包的 `bots.py` 時 `test_for` 挑不到 `tests/bots/test_bot.py`、`test_bot_policy.py`、`test_bot_runner.py`。
