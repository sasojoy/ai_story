# 酒肆（`tianxia/features/tavern/`）

帶「酒肆」標籤的城鎮裡的一間：聽消息、查人、打聽交情與素材、題壁、請全店喝一輪、藏行跡、反查、託酒家留意、買殺手與保鏢、問酒家（鎖外三段式）、鄰桌閒談。主動搬六包第 10 批搬進來的是引擎那一半（計畫 `docs/superpowers/plans/2026-10-31-酒肆包-第1批.md`）；網頁的畫法在 `web/tavern.js`（全部拆包第 65 批從 `app.js` 逐行切出來，116 行；`web = ("tavern.js",)`；計畫 `2026-11-06-網頁殼化-第65批.md`）：`tavernHtml` 與四頁、`tavDo`。點擊分派第二輪第 84 批進這支 js，樣子在 `web/tavern.css`（第 67 批；`.shop-layer.shop-tavern` 那一條與多的 `}`（FB-9441）第 86 批一起搬進 `web/shop.css` 檔尾，兩者不能拆開，拆開那一條就活過來、畫面會變）。

- 導覽：`docs/guide/裝備與店面.md` 的酒肆那一條。
- 設計稿：沒有版本號——https://claude.ai/artifact/3CfrzfpT1HzCxy6S985Q5W（企劃者 2026-10-18 核可；第三節託付留意、第六節買殺手、第八節問酒家）。

## 裡面有什麼

- `rules.py`：純規則（原 `tianxia/tavern.py`）。`ask.py`：問酒家照問句找事實（原 `tianxia/tavern_ask.py`）。兩個舊名都留成 `sys.modules` 別名（同一個模組物件）：`howto`（名望來源）、`server`（第 69 批起殼已經不用，留著只為了 import 順序，見 `server.py` 頂上那行註解）、`scripts/try_tavern_ask.py` 與測試照舊 import 舊名，`monkeypatch.setattr(tavern, ...)` 照樣打得到包裡。
- `actions.py`：原本 `Game` 上酒肆的 43 個方法，加 `tavern_sign`（`act:tavern` 那一下紀錄的標題）。
- `bots.py`：假人看到 `tavern:*` 怎麼按（原 `bot_policy.score` 那一段：只按出酒肆）。打聽那一步第 60 批搬來（`visit`、`TAVERN_RESERVE`、`TAVERN_ASKS`）：`bot_policy._tavern` 留一行、`TAVERN_CHANCE` 留在 `bot_policy`（叫的那一下才讀，`test_tavern`、`scripts/same_behavior.py` 換的是它的屬性）。`act:tavern`：`Verb.bot` 回 None、`bot_skip`。模組層不准碰 engine、`bot_policy`（`bot_policy` 模組層 import 這個檔）。改 `bots.py` 的 `act:` 分數時另外跑 `tests/bots/test_bot_policy.py`、`tianxia/features/sortie/tests/test_bot_policy_conquest.py`、`tests/bots/test_bot_policy_stuck.py`（`test_for` 挑不到，第 60 批）。
- 掛鉤：`enabled`（`rules.on` 或此刻還坐在酒肆裡）、`choose`（`tavern:*`）、`bot_pick`、`bot_always = ("tavern:",)`（`bot.py` 的排除清單原本也寫了一個，第 11 批拿掉那一個，只剩這裡）；第 11 批的接縫掛鉤見下面「委派與留在原位的接縫」。

- 題壁、問酒家的禁字 `BANNED_WORDS` 合 develop 時（2026-11-01，PM 定）搬進核心 `tianxia/naming.py`：探索包的走一趟留言也擋同三個字，包不能 import 別的包。`rules.py` 從 `naming` re-export，`tavern.BANNED_WORDS` 照舊拿得到。

## 認領的欄位（手冊 3.5：留在原地）

- `PlayerState`：`picking_tavern`、`tavern_notes`、`tavern_heard`、`tavern_known`、`tavern_treat_day`、`whispers`、`hidden_until`、`tavern_watches`、`tavern_guard_until`、`tavern_shield_until`（換季全部跟著新角色重來，`carried` 是空的）。
- `WorldState`：`tavern_walls`、`tavern_whispers`、`tavern_treats`、`tavern_hits`、`tavern_hit_seq`、`tavern_chatter`（照季存）。
- `state.py` 的 `TavernNote`、`Whisper`、`WallNote`、`TavernWatch`、`TavernHit`；`models.py` 的 `Config.tavern`（`TavernTuning`）。
- 動身被擋（`atlas.travel_block`）：第 56 批選單收接縫起這一包登記 `MENU_ORDER["block"]` 自己那一格，讀 `picking_tavern` 的只剩包裡；字與先後一字不動（`atlas` 不再讀）。

## 委派與留在原位的接縫

`Game` 上的名字掛在 `game_api.py` 的表（公開 6：`tavern_do`、`tavern_view`、`tavern_ask_request`、`tavern_ask`、`tavern_chatter_request`、`apply_tavern_chatter`；私有 10：`_tavern_open`、`_tavern_enter`、`_tavern_price`、`_tavern_run`、`_tavern_hit_problem`、`_tavern_hit_check`、`_tavern_hit_fight`、`_tavern_ask_facts`、`_deliver_watches`、`_deliver_hits`）。第 10 批留在 `Game` 原位的接縫，**全部拆包第 11 批（核心收接縫，計畫 `docs/superpowers/plans/2026-11-01-核心收接縫.md`）換成了接縫掛鉤**，掛在原本那一行（`_tavern_options`、`_tavern_sign`、`_deliver_whispers` 三個委派沒人叫了，拿掉）：

- 店面登記 `shops()`（`Shop("tavern", …)`）：坐在酒肆裡時選單整個是酒肆那一串（`_everyday_options` 擂台之後）、「此地還能做」裡的 `act:tavern` 入口（馬市之後）、`_shop_open`、`_depart` 收店、`sync` 與 `_drop_stale_references` 的「人不在酒肆了就收店」。
- act 子動詞 `verbs()`（`Verb("tavern", …)`）：`_act` 的 `act:tavern` → `actions.tavern_enter`、`_action_title` 的招牌。
- `on_away`（`sync` 下線那一段的殺手）、`deliver_notices`（三個 deliver：照舊不看酒肆開關，關掉之後雇主照樣領退款、風聲照樣送到）、`after_action`（`choose` 最後那一下殺手檢查）。
- 店面那一頁第二輪第 93 批接 `Feature.shop_view`，轉交 `actions.tavern_view`（本體留 `actions.py`）。
- 還在原位的：`_hint_triggers`、`_newbie_go`（引導，第 22 批）、`_idle`（只讀 `picking_tavern`）、`LEAVE_SHOP_IDS`（寫字面 `"tavern:back"`）；`server.py` 的 `MAIN_ACTIONS["tavern"]`（第 68 批進 `routes.py`）；`tavern_ask` 三段式、鄰桌閒談的背景執行緒（`write_chatter`、`chatter_once`）第 69 批也進 `routes.py`。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組（全部拆包第 40 批合完重印 **3 處**：`actions.py` → `bounties`、`shopview`，`rules.py` → `atlas`；`figures`〔`rules.py`、`ask.py` 函式裡〕、`figure_life`〔`rules.py` 函式裡三處〕第 40 批收進共用規則層，不算過渡，原本 8 處；`annals` 第 29 批之二改 import 核心；以下是更早的寫法）12 處：`actions.py` 4（`annals`、`bounties`、`shopview`、`social`）、`rules.py` 7（`annals`、`atlas`、`figures`，函式裡的 `arena`、`figure_life` 三處）、`ask.py` 1（`figures`）。原本 24 處；`battlelog`、`encounter`、`equipment`、`renown`、`roster`、`territory`、`treasures`、`prologue`、`allied`、`zh` 全部拆包第 15 批登記進共用規則層（`tianxia/core/registry.py` 的 `SHARED`），那幾行行尾改註「共用規則層」，不算過渡。
- 第 45 批合完重印 **1 處**：`actions.py` → `shopview`；`actions.py` 讀懸賞榜（`BOARD`、`board_here`、`visible`、`open_bounties`）改讀核心 `core/bounty_base`，`tavern:board` 直接寫 `picking_bounty` 第 56 批收。
- 第 50 批合完重印 **2 處**：`actions.py` → `bounties`、`shopview`；`rules.py` 讀 `atlas` 的大區第 50 批收進共用規則層，改註。
- 第二輪第 93 批：`actions.py` → `shopview` 清了（`line_text`、`attribute_rank` 改讀 `core/shop_base`）。
- 服務清單（`tianxia/core/services_list.md`）這一包加的：`_shop_say`、`_shop_after`、`_idle`、`_last_wear`（共用）、`_battle_now`（過渡，決戰）、`_tavern_seek_exact`、`_tavern_reply`（寄放）。

## 測試

- 這一包的：`tests/test_tavern.py`（32 條，1 條 smoke）、`test_tavern_seek_presence.py`（7，查人的「此刻就在…」不比「此地還有」寬）、`test_tavern_web.py`（4，假瀏覽器跑整支 `app.js` 的酒肆那幾頁）、`test_tavern_package.py`（6，別名、開關關著時出得去、掛鉤的標題、同一對人的冷卻、題壁擋禁字〔合 develop 時補的〕）、`test_tavern_seams.py`（4，整檔 slow；接縫掛鉤走公開的路：下線那一段殺手得手存回季、一次同步收護衛／風聲／殺手單／託付的先後、在城外做完一件事經 `choose` 殺手找上門、進店那一顆只有一顆——第 11 批審查補的，以前只有 `same_behavior` 抓得到）。`pytest tianxia/features/tavern/tests -n 4 -m "slow or not slow"`。
- **`test_for` 挑不到的混在別人檔裡的**（這一輪不拆）：`tianxia/features/seal/tests/test_seal_acts.py`（FB-643 併進來的玉璽 × 酒肆）、`test_seal_acts3.py`、`tianxia/features/seal/tests/test_seal_acts_hidden.py`、`test_seal_revamp.py`（`_tavern_hit_fight`）、`tianxia/features/seal/tests/test_seal_revamp_hidden.py`、`tests/bots/test_zh.py`（`ask_clean`、`chatter_clean`）、`tianxia/features/sortie/tests/test_sortie_duel_bots.py`（換掉 `bot_policy._tavern`）、`tianxia/features/guide/tests/test_explain2.py`（名望來源）、`test_hints.py`（`h_tavern`）、`tests/server/test_server.py`、`tests/season/test_real_content.py`。改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/tavern/actions.py tianxia/features/seal/tests/test_seal_acts.py tianxia/features/seal/tests/test_seal_acts3.py tianxia/features/seal/tests/test_seal_acts_hidden.py tianxia/features/seal/tests/test_seal_revamp.py tianxia/features/seal/tests/test_seal_revamp_hidden.py tests/bots/test_zh.py tianxia/features/sortie/tests/test_sortie_duel_bots.py tianxia/features/guide/tests/test_explain2.py tianxia/features/guide/tests/test_hints.py tests/server/test_server.py`（`--slow` 連整檔 slow 的那幾個；`test_real_content` 改內容時 `test_for` 自己會挑）。
- **改 `rules.py`、`actions.py` 時 `test_for` 挑的比搬之前窄**（審查量的）：搬之前改 `tianxia/tavern.py` 會挑到 import `tavern` 的 `test_zh` 與五個 seal 檔（8 個檔 120／176 條）；現在程式在包裡，改 `rules.py` 或 `actions.py` 只挑包的 4 個檔＋核心契約與邊界（7 個檔 118／119 條，不含／含 slow）。例：`rules.chatter_clean` 拿掉 `zh.stray_latin` 那一關只有 `test_zh` 紅、`tavern_hit_fight` 的 `hit_win_fame` 加倍只有 `test_explain2` 紅——上面這條指令兩個都抓得到，`test_for` 只給包的檔抓不到。這一輪不讓 `test_for` 把混合檔算進包（同出陣 README），交 PM 定。
- 網頁：改 `web/tavern.js` 時 `test_for` 挑得到包裡的 `test_tavern_web`、`test_shop_width`、`test_shell_web`；挑不到、要另外跑的：`tests/server/test_server.py -k "page or version or scripts"`（那個檔太大，檔名刻意不寫進去；第 61 批搬走的 18 條只是名字帶 page，測的是各包自己的資料，不用跟）、`tests/bots/test_server_bots.py`（掃字）。
- 前後一字不變：`scripts/same_behavior.py` 的 `tavern` 一軌（`--tracks tavern`）。

**行狀記一筆改 import 核心**（全部拆包第 29 批之二）：本包原本「包 → `tianxia.annals`」的過渡 import 改成 `from tianxia.core import annal_base as annals`（核心本體，不算過渡，行尾註拿掉「過渡：待搬」）；上面各處寫到 `annals` 的過渡句（含處數）是這一批之前的舊寫法，現在那幾處不算過渡，數字一律以 `python tests/core/test_feature_boundaries.py` 重印為準（舊名 `tianxia/annals.py` 是指到列傳包 `standing.py` 的別名，那一份 re-export 核心那一半）。

**第 56 批（選單收接縫，核心批）**：`idle/tavern`、`block/tavern` 是這一包登記的格；`tavern:board` 改叫核心 `bounty_base.sit_at_board`；先後在 `core/features.py` 的 `MENU_ORDER`；上面寫「留委派」「原位」的以這一句為準。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（別節中間的插句（`fame_tavern`，核心 `HOWTO_INSERTS`）），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`tavern`。問酒家（`tavern_ask`）是鎖外三段式，第 69 批也搬進來（見下一段）。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：`routes.py` 的 `tavern_ask`（`/api/do/tavern_ask`，`outlock` 掛鉤）、鄰桌閒談 `_chatter_waiting`、`write_chatter`、`chatter_once`、`CHATTER_RUNNING`（那一格 `chatter`，`waiting` 回地點 id、交給 `write_chatter`；殼留一行包裝 `chatter_once`）。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。另外要跑的（`test_for` 挑不到）：`tests/server/test_server.py`、`tests/arts/test_in_lock_model_timeout.py`、`tests/server/test_outlock.py`。
