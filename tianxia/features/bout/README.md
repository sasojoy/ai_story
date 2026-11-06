# 單挑（`tianxia/features/bout/`）

單人頭目戰（在有頭目的地點探索時撞上，三招、放手一搏、抽身）與擂台（報名留分身、別人隨時來挑、名次與稱號、每天的俸、季末前三名，加上台下的場邊事件）。全部拆包第 12 批搬進來（計畫 `docs/superpowers/plans/2026-11-03-單挑包-第1批.md`）。

- 導覽：`docs/guide/戰鬥.md` 的「擂台賽」「江湖水漲」與末尾「單挑（功能包）」那一節。
- 設計稿：擂台 `docs/superpowers/specs/2026-10-14-擂台賽-design.md`（沒有版本號；配套是 PM 轉述 Joy 2026-10-14～16：名次制、哪裡都能挑、俸、看不出還要等多久）、名聲 4.7、場邊事件（Joy 2026-10-17，`Config.arena.crowd`）、擂台動畫與擂台形象（企劃者 2026-10-31 設計稿第三版、形象包 `features/looks`）、FB-615、FB-625；頭目戰沒有設計稿（Joy 2026-10-10 的原話寫在 `duel_rules.py` 開頭），配套散在正式季整合 2.5（21 天季一週兩次）、名聲 4.4、江湖水漲、本命戰法第二批、鐵匠鋪與合成流程 3.9（防具）、M-05（鎖外評好的單子重驗）。

## 裡面有什麼

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`BoutFeature`）：`prefix = ("duel", "arena")`；`enabled`＝內容有頭目、或擂台開著、或此刻還在頭目戰／擂台上／坐在擂台邊（開關在坐著、打著的時候被關掉照樣出得去，同酒肆）；`content` 宣告 `duels.json`、`arena_crowd.json`（`content.py` 照舊讀）；掛鉤 `menu`、`choose`、`bot_pick`、`check_content`、`shops`、`verbs`（下面） |
| `duel_rules.py` | 頭目戰的純規則（原 `tianxia/duel.py`；舊名留成 `sys.modules` 別名）：次數與冷卻的帳、遇得上哪一隻、面貌、他的招與架勢、出一招、放手一搏、勝負、`SETTING`／`PLACE`／`STALE`／`RESEND`、`COUNTER_WORDS`；鎖外三段式的單子 `DuelTextRequest` 與輸入框底下那一句 `DUEL_GAMBLE_NOTE`（原本寫在 `engine.py`） |
| `arena_rules.py` | 擂台的純規則（原 `tianxia/arena.py`；別名）：守擂的分身、挑得到誰、冷卻與次數、一場的推進、俸、收季排名、擂台那一頁的字 |
| `arena_crowd.py` | 場邊事件（原 `tianxia/arena_crowd.py`；別名）：底細、候選、擲、套用、模型判觀眾反應與重寫那一句；`check_content`（原 `content.check_arena_crowd`） |
| `duel_actions.py` | 原本 `Game` 上頭目戰的 16 個方法（名字去掉前導底線）＋頭目的查詢 `boss_ready`（只有三選一的練功問的三個第 13 批一起拿掉）＋打到一半的選單 `duel_menu`（三招與抽身；審查修正從 `_everyday_options` 搬來）；頭目戰、擂台共用的放手一搏輸入框與重驗、本命戰法的亂數、陣營名也在這裡 |
| `arena_actions.py` | 原本 `Game` 上擂台的 22 個方法（`_arena` → `arena_choice`、`_arena_crowd` → `roll_crowd`）＋原位接上掛鉤的那幾段（`fight_menu`、`entry_option`、`close`、`arena_open`、`arena_sign`、`arena_title`、`arena_fight_problem`） |
| `bots.py` | 假人看到 `duel:`、`arena:` 怎麼按（原 `bot_policy.score` 那兩段：頭目戰的招在 `take_turn` 前面就照架勢出了、一律 None；擂台只按返回）。報名、更新分身、挑一場（`bot_policy._arena`）與打到一半的出招（`duel_move`）是 `take_turn` 的步驟，照舊在 `bot_policy`。第 60 批：`act:arena` 的 `Verb.bot` 回 None、`bot_skip`；`idle`（`Feature.bot_idle`）整季機器人不按 `duel:flee`、`arena:yield` |

**留在核心的兩塊**（別包也在用，包不能 import 包）：單挑底層 `tianxia/core/duel_base.py`（剋、推力、挨打、防具、放手一搏擲一次、勝負、架勢、氣勢的字、選單上的一招、`Scene`：頭目戰、擂台、奪璽單挑共用；奪璽單挑 `seal_duel.py`、店面 `shopview.py` import 它）、擂台的名次與稱號 `tianxia/core/arena_ranks.py`（查詢服務：酒肆包的名氣、名帖、玩家卡、榜單、事件分級、江湖史的歷屆擂主、本週卡讀）。`duel_rules`、`arena_rules` 從這兩份 re-export 同一批函式物件，`tianxia.duel.push_of`、`tianxia.arena.title_of` 照舊拿得到。

## 認領的欄位（手冊 3.5：留在原地）

- `PlayerState`：頭目戰 `duel`、`duel_tally`、`duel_last`；擂台 `arena`、`arena_last`、`picking_arena`、`arena_day`、`arena_today`、`arena_crowd_seen`、`arena_crowd_note`（換季全部跟著新角色重來，`carried` 是空的）。
- `WorldState`（照季存）：`arena`（守擂的分身）、`arena_pairs`（同一對的冷卻）、`arena_seq`、`arena_closed`（季末前三名排過了）、`arena_day`（俸發到哪一天）。型別在 `state.py` 的 `ArenaEntry`、`ArenaFight`、`ArenaSide`、`ArenaReport`、`ArenaResult`、`CrowdNote`、`CrowdSide`、`DuelState`）；`models.py` 的 `Config.duel`（`DuelTuning`）、`Config.arena`（`ArenaTuning`、`ArenaCrowdTuning`）、`DuelBoss`、`DuelFoe`。
- 動身被擋（`atlas.travel_block`）：第 56 批選單收接縫起這一包登記 `MENU_ORDER["block"]` 自己那一格，讀 `duel`、`arena`、`picking_arena` 的只剩包裡；字與先後一字不動（`atlas` 不再讀）。

## 委派與留在原位的接縫

`Game` 留 25 個一行委派（17 個私有；第 13 批拿掉三選一少了 `_boss_here`、`_boss_wait_text`、`_boss_used_up` 三個）：搬來的 22 個（`_duel_start`、`_duel_scene`、`duel_free_text_prompt`、`duel_free_text_note`、`duel_text_request`、`_duel_side`、`duel_gamble`、`_duel_act`、`_duel_finish`、`_duel_cut`、`_boss_face`、`_arena_bare`、`arena_power`、`arena_left`、`_arena_entry`、`_arena_options`、`_arena_join`、`_arena_scene`、`arena_crowd_request`、`apply_arena_crowd`、`_arena_act`、`_deliver_arena`）、新開的 2 個一行查詢（`_boss_ready`、`_arena_fight_problem`：原位的接縫不直接碰包，不新增 `GAME_DIRECT`），與審查修正補的 `_duel_menu`（頭目戰打到一半的選單，本體原本留在 `_everyday_options`）。只有包裡叫的 16 個不留。`Game.DUEL_GAMBLE_NOTE` 指到 `duel_rules` 同一句。

- **接上第 11 批掛鉤的**：店面登記 `shops()`（`Shop("arena", …)`：坐在擂台邊的選單、此地還能做裡「擂台」那一顆、`_shop_open`、`_depart`、`sync` 與 `_drop_stale_references` 收店；排在 `FEATURES` 最後＝酒肆後面）、act 子動詞 `verbs()`（`Verb("arena", …)`：打開擂台、「擂台・此地」）、`choose`（`arena:join`／`fight:<名號鍵>`／`back`，標題照原本 `_action_title` 的 arena 那一支）、`menu`（擂台打到一半的三招與認輸，排在宴客後面＝原本那一行）、`check_content`（場邊事件的固定句；`content.validate` 裡排在 `check_art` 前面，只有兩樣同時寫壞時錯誤的先後不一樣）。
- **還在原位叫委派的**（沒有對應的掛鉤，邊界測試 `GAME_DELEGATE_CALLERS` 寫了理由）：灰掉的挑擂鈕（`_arena_fight_problem`：回 `Refused`〔只在 engine〕、還不寫 `_log`，第 57 批量過位置不動）；`_everyday_options` 閉關中、在路上的入口（`_arena_entry`）；頭目戰打到一半的三招與抽身（`_everyday_options` → `_duel_menu`：排在 `menu` 掛鉤前面一行，接上掛鉤會排到宴客的席位後面）；場景卡（`_own_scene_text` → `_duel_scene`、`_arena_scene`）；`sync` 的擂台補送（`_deliver_arena`）；店面那一頁（`shop_view` → `arena_left`，第 41 批）；戰力快照抄防具（`_battle_gear` → `_duel_cut`；奪璽單挑的 `_seal_spectators`、`_seal_side_of` 也在**別人的** `Game` 上叫 `kin._duel_cut()`、`game._duel_cut()`——邊界測試只掃 `self.<名>`，名單記不到這兩處。**第 28 批**把那兩個方法搬進玉璽包時，要先把 `_duel_cut` 登記成服務清單二、查詢服務〔主人：單挑包〕）；奪璽單挑的陣營名（`seal_text_request` → `_duel_side`，第 28 批）；舊探索撞上頭目（`_boss_ready`、`_boss_face`、`_duel_start`；舊探索留著，不再有下一批收）。只讀存檔的照舊在原位：`_idle`、`_shop_open` 的「擂台打到一半」、`_own_scene_text` 的判斷、`LEAVE_SHOP_IDS`／`ARENA_YIELD`（寫字面）。
- **別包怎麼問**：探索包的出門一趟撞上頭目經 `ctx._boss_ready()`、`ctx._boss_face(boss)`、`ctx._duel_start(boss)`（服務清單二、查詢服務）；酒肆包的名氣讀核心 `arena_ranks`。這一包經 `ctx` 叫形象包的 `arena_look`、`arena_move`（查詢服務）。
- **舊模組 → 包**（過渡，3.11）：`bot_policy`（`arena`、`duel`）、`shopview`、`tiers`（`tests/core/test_event_tiers.py` 換掉 `tianxia.arena.entry_of`，所以照舊經別名）照舊 import 別名（`world` 收季的 `close_season` 全部拆包第 25 批換成世界層 `close` 的 `arena` 那一格：`__init__.py` 的 `world()` → `arena_rules.world_close`，判斷照原位只看擂台開著沒，不問 `enabled`；第 12 批 PM 認定第 2 條）；只讀名次與稱號的 `mingtie`（名帖）、`social`（玩家卡）、`leaderboard`（榜單）改讀核心的 `arena_ranks`（審查修正，邊界測試 `ARENA_RANK_READERS` 守）；`server.py`（`duel.Scene`、`SETTING`、`PLACE`，`arena_crowd` 的鎖外重寫與看台）、`scripts/` 也是。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組 2 處：`duel_actions.py`、`arena_actions.py` 各一行 `annals`（行狀）。其餘 import 的都是核心本體與共用規則層（`battle_instance`、`battlelog`、`encounter`、`materials`、`renown`、`rise`、`rounds`、`tactics`、`treasures`、`prologue`、`week_unlock`、`zh`……）。
- 服務清單（`tianxia/core/services.py`）這一包加的（`# bout`）：二、查詢服務 `ctx._boss_ready()`、`ctx._boss_face(boss)`、`ctx._duel_start(boss)`（探索包問；原本在三、過渡 explore 那一段）、`ctx.arena_look()`、`ctx.arena_move()`（主人：形象包）；三、過渡 `ctx._arena_bare()`（`tianxia/features/seal/tests/test_seal_revamp_hidden.py` 換掉）、`ctx._duel_finish(tier, line)`（`scripts/sim_season_one.py` 換掉）——這兩個是這一包自己的委派，包裡經 `ctx` 叫才打得到。

## 測試

- 這一包的：`tests/test_duel.py`（頭目戰 28 條，1 條 smoke；`tests/gear/test_mounts.py`、`tests/seal/test_seal_revamp.py` 照舊 `from test_duel import _boss`）、`test_arena.py`（擂台 37 條，1 條 smoke）、`test_arena_crowd.py`（場邊事件 13 條，1 條 smoke；從 `test_arena` 拿 `ring` 那幾個輔助）、`bout_stage.py`（契約測試擺局面：坐在擂台邊、擂台打到一半）。全部拆包第 12 批從 `tests/battle/` 整檔搬來，斷言一字沒改（`test_arena_crowd` 讀 `content/arena_crowd.json` 的路徑從 `parents[2]` 換成 `parents[4]`）。審查修正另加 `test_bout_seams.py`（14 條：接上掛鉤的收店與動身收店、假人在擂台邊只按返回、坐著時開關被關掉照樣開著、更新分身照此刻的形象、單挑底層勝負的門檻、戰績那一句的連勝——以前只有 `same_behavior` 守，審查的變異 M14、M6、M7、M8、C3、C4 包加混合檔一條都不紅）。一共 92 條、沒有 slow，`-n 4` 約 15 秒。`pytest tianxia/features/bout/tests -n 4 -m "slow or not slow"`。
- **`test_for` 挑不到的混在別人檔裡的**（這一輪不拆，同出陣、酒肆）：
  - 頭目戰：`tests/battle/test_rise.py`（江湖水漲浮頭目的難度）、`test_tactics_bouts.py`（頭目戰、擂台的本命戰法）、`test_maxed_xinde.py`（滿級換心得）、`tests/core/test_precise_actions.py`（一類一顆）、`tests/gear/test_mounts.py`（`from test_duel import _boss`）、`tests/seal/test_seal_revamp.py`（同上，碎片不浮頭目）、`tests/server/test_server.py`（`/api/do/duel_text` 的鎖外三段式）、`tests/bots/test_zh.py`。
  - 擂台：`tests/battle/test_renown_arena.py`（名聲 4.7）、`tests/core/test_event_tiers.py`（擂主的分級）、`tianxia/features/guide/tests/test_onboard.py`（原 `tests/core/`，第 22 批搬進引導包，合進 develop 時改路徑）、`tests/figures/test_week7_season.py`、`test_week_unlock.py`（第 2 週才開擂台）、`tianxia/features/seal/tests/test_seal_revamp_hidden.py`（換掉 `Game._arena_bare`）、`tianxia/features/seal/tests/test_seal_revamp_sidedoor.py`、`tests/seal/test_seal_duel.py`（奪璽單挑用單挑底層）、`tests/server/test_web_push.py`。
  - 奪璽單挑的接縫（`seal_duel.py` 改讀核心的 `duel_base`、engine 的 `_seal_options`／`seal_gamble` 改叫 `duel_base`、`seal_text_request` 改叫委派 `_duel_side`、`_seal_spectators`／`_seal_side_of` 叫 `_duel_cut`）：`same_behavior` 沒有一軌走奪璽單挑，只靠 `tests/seal/test_seal_duel.py` 與 `tests/seal/test_seal_engine.py`（唯一叫到 `seal_text_request`／`seal_gamble` 的測試檔；審查修正補進來）。
  - 接縫與名單：`tests/core/test_contract_features.py`、`test_feature_boundaries.py`（改包的檔 `test_for` 會帶）、`tests/arts/test_explain2.py`（名望來源的那四行）。
  - 一起跑：`python scripts/test_for.py --base HEAD tianxia/features/bout/arena_actions.py tests/battle/test_rise.py tests/battle/test_tactics_bouts.py tests/battle/test_maxed_xinde.py tests/core/test_precise_actions.py tests/gear/test_mounts.py tests/seal/test_seal_revamp.py tests/server/test_server.py tests/bots/test_zh.py tests/battle/test_renown_arena.py tests/core/test_event_tiers.py tianxia/features/guide/tests/test_onboard.py tests/figures/test_week7_season.py tests/figures/test_week_unlock.py tianxia/features/seal/tests/test_seal_revamp_hidden.py tianxia/features/seal/tests/test_seal_revamp_sidedoor.py tests/seal/test_seal_duel.py tests/seal/test_seal_engine.py tests/server/test_web_push.py tests/arts/test_explain2.py --slow`（27 個檔 1,163 條；只改包的檔 `test_for` 挑 211／212 條〔不含／含 slow：包 92＋核心契約與邊界〕；合進 develop〔合了第 17、22、8 批，契約多了引導包那幾條〕之後 219／220 條，改 `tests/bout_stage.py` 也是這 219／220 條）。
- 前後一字不變：`scripts/same_behavior.py` 的 `bout`（切在擂台報名之後、被挑之前；同一刻頭目戰打到一半）、`ring`（切在擂台寫到一半：擂台打到一半、場邊那一句等著重寫、守擂的那一筆沒補、坐在擂台邊、記下的俸沒領；審查修正取代原本的 `boss`）兩軌（`--tracks bout,ring`）。

**行狀記一筆改 import 核心**（全部拆包第 29 批之二）：本包原本「包 → `tianxia.annals`」的過渡 import 改成 `from tianxia.core import annal_base as annals`（核心本體，不算過渡，行尾註拿掉「過渡：待搬」）；上面各處寫到 `annals` 的過渡句（含處數）是這一批之前的舊寫法，現在那幾處不算過渡，數字一律以 `python tests/core/test_feature_boundaries.py` 重印為準（舊名 `tianxia/annals.py` 是指到列傳包 `standing.py` 的別名，那一份 re-export 核心那一半）。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.deliver` 的 `arena`（`arena_actions.deliver_arena`；`Game._deliver_arena` 留給測試）。

**第 56 批（選單收接縫，核心批）**：`take/duel`、`busy/arena`、`road/arena`、`idle/duel`、`idle/arena`、`open/arena`、`block/bout` 是這一包登記的格；先後在 `core/features.py` 的 `MENU_ORDER`；委派 `_duel_menu`、`_arena_entry` 拿掉；上面寫「留委派」「原位」的以這一句為準。

**第 57 批（分派與標題收接縫，核心批）**：`choose` 不建紀錄的 `duel:`、`arena:<招>`／認輸是 `MENU_ORDER["quick"]` 的 `duel`、`arena` 兩格（`arena` 那一格只接招式與認輸，`arena:join`、`fight`、`back` 回 None 照舊走 `choose` 掛鉤）。委派 `_duel_act`、`_arena_act` 拿掉；engine 不再 import `MOVES`，`ARENA_YIELD` 留（`bot.py` 從 engine 拿）。
