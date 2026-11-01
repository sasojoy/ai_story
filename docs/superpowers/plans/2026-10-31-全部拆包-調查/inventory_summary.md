# 架構盤點：數字總表

工作樹 `C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\splitwt`，develop `5fccb11a`（detached）。完整資料在 `inventory.json`（同資料夾）；這份只放數字。
抽法：Python ast（server、engine、tianxia 全部）；web/*.js 用自寫的掃描器（字串、樣板、註解、正規式），每一段頂層宣告再用 node vm.Script 單獨編譯驗過。

## 一、總表

| 項目 | 數 | 行數 |
|---|---:|---:|
| `tianxia/` 底下所有 .py（含 features 的 tests） | 205 | 97,326 |
| 　其中非測試 | 188 | 93,762 |
| 　　`tianxia/*.py`（頂層模組） | 169 | 90,945 |
| 　　`tianxia/core/` | 6 | 504 |
| 　　`tianxia/features/**`（不含 tests） | 13 | 2,313 |
| 　其中 `tianxia/features/*/tests`（含 conftest） | 17 | 3,564 |
| `engine.py` | 1 | 17,650 |
| 　`class Game`（第 449～17645 行） | 方法 1033 | 類別 17,197；方法合計 15,997 |
| 　engine.py 裡 Game 以外的頂層函式／類別 | 9 函式／9 類別 | 137 |
| `server.py` 路由 | 55 | handler 合計 489 |
| 功能包的路由（`features/*/routes.py`） | 6 | 66 |
| 　路由合計 | **61** | |
| `server.py` 其餘頂層函式（不是路由） | 144 | 2,169 |
| `server.py` 動作表（op → lambda） | 3 張、92 個 op | |
| `web/` 檔案 | 142 | 文字檔合計 15,405 |
| `web/app.js` | 1 | 6,846 |
| 　app.js 頂層 `function` 宣告 | **336** | 4,568 |
| 　app.js 頂層 `const x = () =>`／function 運算式 | 61 | 86 |
| 　app.js 頂層 `const` 物件 | 26 | 221 |
| 　app.js 頂層宣告合計（function、const、let、class） | 537 | |
| `content/` 檔案 | 93 | 1,815,427 bytes |
| 測試檔（test_*.py，`tests/` ＋ `features/*/tests`） | 438 | `def test_` 9,827（slow 1,082） |
| 選項 id 的前綴（選項類別） | 38 | |
| 功能包（registry 登記） | 3 | |

JS 驗證：web/*.js 抽出的 1147 段頂層宣告各自用 node `vm.Script` 編譯，失敗 0 段；app.js 掃到檔尾的深度 0、狀態 code（括號全部對上）。Game 方法數（1033）跟 engine.py 裡 `^    def` 的行數（1036）差 3：`OutingPlan.foe_note`，與兩個裝飾器（`_not_while_preparing`、`_outing_watch`）裡的內層函式；工作樹 `git status` 照舊是乾淨的。

### inventory.json 的鍵

| 鍵 | 筆數 | 內容 |
|---|---:|---|
| `game_methods` | 1033 | Game 每個方法：行號、裝飾器、calls_self、called_by、mod_refs、ext_callers、ext_test_*、patched_in、touches_removal |
| `engine_other` | 18 | engine.py 裡 Game 以外的頂層函式與類別 |
| `modules` | 205 | tianxia 底下每個 .py：package、區塊、行數、imports_tianxia（含 lazy、type_checking）、imported_by、imported_by_tests、頂層函式清單 |
| `feature_packages` | 3 | 現有功能包：prefix、bot_always、檔案 |
| `server_routes` | 61 | 每一條路由：路徑、方法、handler、行號、calls_game、calls_game_via_tables、calls_game_via_helpers、sub_ops（/api/do 的 op 分支） |
| `server_other` | 147 | server.py 其餘頂層函式（含 calls_game） |
| `server_tables` | 4 | MAIN_ACTIONS、ADMIN_ACTIONS、MENXIA_ACTIONS 每個 op 叫哪個 Game 方法 |
| `server_plumbing` | 14 | 殼的共用管線 |
| `option_prefixes` | 38 | 選項類別：處理方法、分派位置與 phase、子動詞、做出 id 的方法、提到它的模組 |
| `other_prefix_like` | 17 | 像前綴但不是選項類別的字串 |
| `choose_dispatch` | 50 | Game.choose 的每一個分派條件（含 phase） |
| `act_dispatch` | 28 | Game._act 的每一個分派條件 |
| `bot_policy` | 25 | score 的段與 act 子分支；bot_policy／bot／bot_runner 其他函式裡的前綴字串 |
| `tests` | 448 | dirs（每個資料夾）、files（每個檔：test 數、slow 數、import 的 tianxia 模組） |
| `content` | 93 | content 每個檔：大小、JSON 型別與筆數 |
| `web` | 142 | 每個檔的行數；app_js 與 other_js 的頂層宣告 |

## 二、Game 方法照名字前綴分組（前 60 組）

前綴＝去掉開頭底線之後、第一個底線前的字（`_battle_choose` → `battle`；沒有底線的整個名字算一組）。照方法數排，同數照行數。

共 371 組；前 60 組涵蓋 573 個方法、9,235 行（全部 1033 個、15,997 行）。

| # | 前綴 | 方法數 | 行數 | 例 |
|---:|---|---:|---:|---|
| 1 | `admin` | 52 | 946 | `admin_schedule`、`admin_seal_mandate`、`admin_seal_duel`、`admin_resolve_event` |
| 2 | `tavern` | 38 | 637 | `_tavern_hit_fight`、`tavern_view`、`_tavern_seek_once`、`_tavern_ties` |
| 3 | `duel` | 34 | 592 | `_duel_report`、`_duel_finish`、`_duel_result`、`duel_gamble` |
| 4 | `battle` | 33 | 560 | `_battle_scene_text`、`_battle_choose_in`、`_battle_rewards`、`_battle_options` |
| 5 | `seal` | 19 | 462 | `_seal_settle`、`seal_use`、`_seal_find`、`seal_gamble` |
| 6 | `outing` | 19 | 316 | `_outing_walk`、`_outing_fight`、`outing_say`、`_outing_watched` |
| 7 | `parley` | 19 | 315 | `_parley_answer`、`_parley_do`、`_parley_decide`、`_parley_options` |
| 8 | `arena` | 19 | 276 | `_arena_finish`、`_arena_start`、`_arena_crowd`、`_arena_gamble` |
| 9 | `sortie` | 18 | 296 | `sortie_card`、`sortie_cards`、`sortie_go`、`sortie_answer` |
| 10 | `deliver` | 14 | 373 | `_deliver_seal_results`、`_deliver_arena`、`_deliver_conquest`、`_deliver_hits` |
| 11 | `raid` | 11 | 193 | `_raid_record`、`raid`、`raid_refusal`、`_raid_spoils` |
| 12 | `road` | 11 | 143 | `_road_sight`、`_road_say`、`_road_task_options`、`_road_gather` |
| 13 | `discuss` | 11 | 136 | `_discuss`、`discuss_item_problem`、`discuss_invite_problem`、`discuss_refusal` |
| 14 | `create` | 11 | 62 | `create_name`、`create_intent`、`create_request`、`create_reread_request` |
| 15 | `smith` | 10 | 200 | `_smith_act`、`_smith_options`、`smith_forge`、`smith_upgrade` |
| 16 | `story` | 10 | 89 | `_story_act`、`story_card_view`、`_story_bout`、`_story_tick` |
| 17 | `spar` | 9 | 132 | `_spar_record`、`_spar`、`spar_refusal`、`_spar_problem` |
| 18 | `train` | 9 | 123 | `_train`、`_train_option`、`_train_line`、`train_trend_push` |
| 19 | `mall` | 9 | 19 | `_mall_owner`、`_mall_grant`、`mall_buy`、`mall_entry` |
| 20 | `explore` | 8 | 224 | `_explore_one`、`_explore_mode`、`_explore_outcome`、`_explore_mode_options` |
| 21 | `apply` | 8 | 129 | `_apply_battle_outcome`、`apply_arena_crowd`、`apply_battle_tales`、`_apply_outcome_trends_and_flags` |
| 22 | `xingshi` | 8 | 84 | `_xingshi_open`、`_xingshi_finish`、`_xingshi_grace`、`xingshi_request` |
| 23 | `settle` | 7 | 180 | `_settle_showdown`、`_settle_siege`、`_settle_partings`、`_settle_duel` |
| 24 | `showdown` | 7 | 174 | `_showdown_pay`、`_showdown_lines`、`_showdown_status`、`_showdown_tier4` |
| 25 | `gather` | 7 | 126 | `_gather`、`_gather_fight`、`gather_say`、`gather_text_request` |
| 26 | `zhuan` | 7 | 87 | `_zhuan_options`、`_zhuan_act`、`_zhuan_extra`、`_zhuan_past` |
| 27 | `map` | 7 | 80 | `map_state`、`_map_foes`、`map_mostly`、`map_base` |
| 28 | `escort` | 7 | 58 | `_escort_step`、`_escort_of`、`_escort_carry`、`_escort_options` |
| 29 | `ambush` | 6 | 181 | `_ambush_record`、`_ambush_fight`、`_ambush_spoils`、`_ambush_check` |
| 30 | `donate` | 6 | 97 | `_donate`、`_donate_options`、`donate_items`、`_donate_option` |
| 31 | `practice` | 6 | 96 | `_practice_option`、`_practice`、`_practice_line`、`practice` |
| 32 | `silver` | 6 | 78 | `_silver_options`、`_silver_donate`、`_silver_act`、`_silver_bribe` |
| 33 | `event` | 6 | 76 | `_event_battle`、`event_option_view`、`event_tier`、`_event_progress` |
| 34 | `mingtie` | 6 | 76 | `mingtie_view`、`mingtie_send_problem`、`mingtie_send`、`_mingtie_swap` |
| 35 | `forge` | 6 | 73 | `forge`、`forge_request`、`_forge_clue`、`forge_preview` |
| 36 | `siege` | 6 | 59 | `_siege_guards`、`_siege_join`、`_siege_you`、`siege_banner` |
| 37 | `challenge` | 5 | 117 | `_challenge`、`_challenge_options`、`_challenge_draw`、`challenge_odds` |
| 38 | `fight` | 5 | 80 | `fight_request`、`_fight_gate`、`_fight_squad`、`_fight_with` |
| 39 | `sense` | 5 | 70 | `sense_draw`、`_sense_apply`、`_sense`、`_sense_here` |
| 40 | `figure` | 5 | 68 | `_figure_tier4`、`figure_view`、`_figure_tier3`、`_figure_squad` |
| 41 | `shop` | 5 | 64 | `shop_view`、`_shop_open`、`_shop_live`、`_shop_say` |
| 42 | `socialize` | 5 | 55 | `_socialize`、`socialize_is_futile`、`_socialize_option`、`_socialize_figure` |
| 43 | `pill` | 5 | 29 | `_pill_find`、`pill_cap`、`_pill_card_bonus`、`pill_now` |
| 44 | `answer` | 4 | 193 | `_answer_branch`、`answer_event`、`answer_invite`、`answer_on_card` |
| 45 | `hint` | 4 | 93 | `_hint_triggers`、`_hint_box`、`_hint_up`、`_hint` |
| 46 | `conquest` | 4 | 92 | `conquest_view`、`_conquest_tick`、`conquest_letter`、`_conquest_side` |
| 47 | `biography` | 4 | 71 | `biography_request`、`biography_view`、`biography_list`、`biography_entry` |
| 48 | `enlist` | 4 | 67 | `_enlist`、`_enlist_options`、`_enlist_sides`、`enlist_glow` |
| 49 | `errand` | 4 | 67 | `_errand_persuade`、`_errand_act`、`_errand_reward`、`_errand_options` |
| 50 | `season` | 4 | 65 | `season_result`、`_season_grant`、`season_scale`、`_season_closed` |
| 51 | `drill` | 4 | 59 | `_drill_gains`、`_drill`、`_drill_push`、`drill_scale` |
| 52 | `join` | 4 | 50 | `_join_refusal`、`join_refusal`、`_join_lean`、`_join` |
| 53 | `now` | 4 | 46 | `now_entry_html`、`_now_entry`、`now_front`、`_now_start` |
| 54 | `peer` | 4 | 34 | `peer_act`、`_peer`、`peer_request`、`peer_card` |
| 55 | `check` | 4 | 33 | `check_in`、`_check_cost_note`、`_check_hints`、`_check_newbie` |
| 56 | `recruit` | 4 | 33 | `_recruit_targets`、`_recruit_one`、`_recruit_target`、`_recruit` |
| 57 | `letter` | 4 | 29 | `letter_problem`、`letter_view`、`letter_request`、`_letter_key` |
| 58 | `trade` | 4 | 25 | `_trade_sell`、`_trade_upgrade`、`_trade_on`、`_trade_open` |
| 59 | `epiphany` | 4 | 24 | `_epiphany_begin`、`epiphany_request`、`epiphany_names`、`_epiphany_name` |
| 60 | `heal` | 4 | 23 | `_heal_option`、`heal`、`heal_button`、`_heal_msgs` |

## 三、最大的 Game 方法（前 25）

| 方法 | 行 | 行數 | self 呼叫數 | 被誰叫（數） | 測試檔數 |
|---|---|---:|---:|---:|---:|
| `_everyday_options` | 1322～1564 | 243 | 55 | 1 | 0 |
| `choose` | 3389～3604 | 216 | 63 | 4 | 167 |
| `_drop_stale_references` | 860～1003 | 144 | 8 | 1 | 8 |
| `_action_title` | 4148～4272 | 125 | 3 | 2 | 0 |
| `sync` | 1034～1147 | 114 | 46 | 0 | 107 |
| `_reset_player_for_new_season` | 712～818 | 107 | 3 | 1 | 9 |
| `status_data` | 16839～16944 | 106 | 14 | 1 | 39 |
| `_act` | 4731～4828 | 98 | 28 | 1 | 1 |
| `_explore_one` | 5362～5456 | 95 | 13 | 1 | 0 |
| `_seal_settle` | 8245～8335 | 91 | 2 | 1 | 4 |
| `_file_showdown` | 8763～8852 | 90 | 8 | 1 | 3 |
| `_battle_scene_text` | 9171～9256 | 86 | 11 | 1 | 6 |
| `_answer_branch` | 3743～3818 | 76 | 16 | 1 | 0 |
| `_duel_report` | 10906～10979 | 74 | 10 | 0 | 0 |
| `_duel_finish` | 14399～14471 | 73 | 4 | 2 | 3 |
| `answer_event` | 3672～3741 | 70 | 17 | 0 | 10 |
| `__init__` | 452～520 | 69 | 1 | 0 | 0 |
| `push_trend` | 11424～11492 | 69 | 6 | 9 | 9 |
| `_squad_encounter` | 9829～9895 | 67 | 22 | 7 | 8 |
| `_hint_triggers` | 4447～4511 | 65 | 6 | 1 | 1 |
| `_battle_choose_in` | 9616～9680 | 65 | 22 | 1 | 1 |
| `dialogue_request` | 2404～2465 | 62 | 7 | 1 | 8 |
| `_tavern_hit_fight` | 2997～3058 | 62 | 5 | 1 | 1 |
| `_challenge` | 11171～11230 | 60 | 24 | 1 | 0 |
| `_parley_answer` | 7032～7089 | 58 | 6 | 1 | 0 |

## 四、最大的模組（非測試，前 30）

| 模組 | 行數 | 區塊 | 被 import（非測試／測試） | import tianxia 模組數 |
|---|---:|---|---:|---:|
| `tianxia/engine.py` | 17,650 | — | 49／255 | 151 |
| `tianxia/models.py` | 5,234 | 核心與存檔 | 151／151 | 1 |
| `tianxia/content.py` | 3,604 | — | 50／102 | 29 |
| `tianxia/battle_instance.py` | 2,367 | 戰鬥 | 26／52 | 6 |
| `tianxia/state.py` | 2,091 | — | 148／217 | 4 |
| `tianxia/tactics.py` | 1,671 | 戰鬥 | 25／12 | 2 |
| `tianxia/team.py` | 1,512 | 戰鬥 | 40／109 | 25 |
| `tianxia/bounties.py` | 1,481 | 散人與玩家互動 | 19／29 | 27 |
| `tianxia/howto.py` | 1,329 | — | 2／30 | 26 |
| `tianxia/bot_policy.py` | 1,311 | 模型與假人 | 10／57 | 33 |
| `tianxia/sqlite_world.py` | 1,279 | — | 36／107 | 15 |
| `tianxia/rules.py` | 1,242 | 核心與存檔 | 91／108 | 29 |
| `tianxia/skillview.py` | 1,151 | 武學與成長 | 3／38 | 34 |
| `tianxia/conquest.py` | 1,024 | — | 25／27 | 8 |
| `tianxia/tavern.py` | 1,006 | 裝備與店面 | 6／6 | 18 |
| `tianxia/opportunities.py` | 973 | — | 4／7 | 13 |
| `tianxia/world.py` | 963 | 核心與存檔 | 15／32 | 33 |
| `tianxia/bot.py` | 939 | 模型與假人 | 20／51 | 39 |
| `tianxia/atlas.py` | 922 | 地圖與介面 | 25／44 | 16 |
| `tianxia/create.py` | 906 | 武學與成長 | 6／8 | 18 |
| `tianxia/shopview.py` | 884 | 裝備與店面 | 2／14 | 21 |
| `tianxia/world_state.py` | 850 | 核心與存檔 | 62／52 | 10 |
| `tianxia/smithing.py` | 825 | 裝備與店面 | 7／16 | 19 |
| `tianxia/mapview.py` | 802 | 地圖與介面 | 2／14 | 10 |
| `tianxia/foreshadow.py` | 770 | 大勢人物與賽季 | 10／12 | 12 |
| `tianxia/seal_acts.py` | 753 | 玉璽碎片 | 12／5 | 14 |
| `tianxia/timetable.py` | 708 | 大勢人物與賽季 | 16／24 | 7 |
| `tianxia/companion_agent.py` | 703 | — | 7／25 | 17 |
| `tianxia/renown.py` | 686 | — | 26／23 | 6 |
| `tianxia/mapdata.py` | 677 | — | 2／13 | 22 |

CLAUDE.md 功能區塊表沒列到的非測試模組：71 個（`modules[].block` 是 null；照 CLAUDE.md「沒列在表上的照它做的事歸到最近的那一塊」，分配時要補）。

## 五、選項 id 前綴 → 處理的 Game 方法

`Game.choose` 照 `kind`（id 第一個冒號前）分派；phase 寫在 `option_prefixes[].dispatch`。`act:` 的子分派在 `Game._act`（見下一段）。

| 前綴 | 處理（pre／main） | 做出 id 的地方 | 備註 |
|---|---|---|---|
| `act:` | `_act` | `_arena_entry`、`_challenge_options`、`_cost_option`、`_donate_option`… | 有兩分頁搶的 Refused 守門；做完補記：_guide |
| `aid:` | `_aid_act` | `_aid_options`、`_cost_option` |  |
| `ambush:` | `_ambush_act` | `_cost_option`、`_stamina_play_options` |  |
| `arena:` | `_arena_act`、`_arena` | `_arena_options`、`_everyday_options` | 有兩分頁搶的 Refused 守門 |
| `battle:` | `_battle_choose` | `_battle_options`、`_enlist_options`、`_escort_options` |  |
| `bounty:` | `_bounty` | `_bounty_options`、`bounties.hand_in_options` | 有兩分頁搶的 Refused 守門 |
| `call:` | `_call` | `_audience_options`、`_cost_option`、`_everyday_options` | 做完補記：_guide |
| `choice:` | — | `_everyday_options` | 做完補記：_guide |
| `dadian:` | `_close_dadian` | `_everyday_options` |  |
| `defect:` | `_defect_step` | `_everyday_options`、`options` |  |
| `donate:` | `_donate_choice` | `_donate_options` |  |
| `duel:` | `_duel_act` | `_everyday_options` |  |
| `dunwu:` | `_epiphany_name` |  |  |
| `errand:` | `_errand_act` | `_cost_option`、`_errand_options` |  |
| `explore:` | `_explore_mode` | `_cost_option`、`_explore_mode_options`、`_gather_branch_options`、`_practice_option`… | 整套拿掉（探索三選一）；做完補記：_guide |
| `faction:` | `_faction_step` | `_ally_options`、`_everyday_options`、`_lean_options` | 有兩分頁搶的 Refused 守門 |
| `feast:` | `tianxia.features.feast（features_core.choose，Game.choose 第 3390 行起的 taken）` | `features.feast.actions.menu`、`features.feast.actions.options` | 功能包 `tianxia.features.feast` |
| `fs:` | `_foreshadow` | `foreshadow.asking_options`、`foreshadow.final_options` |  |
| `invite:` | `_invite` | `_cost_option`、`_invite_options` |  |
| `learn:` | `library.learn` | `_everyday_options` |  |
| `market:` | `_market` | `_market_options` | 有兩分頁搶的 Refused 守門 |
| `move:` | `_move` | `_move_option` |  |
| `opp:` | `opportunities.act` | `opportunities._plot_options`、`opportunities.place_options` |  |
| `parley:` | `_road_say` | `_parley_road_option` |  |
| `plan:` | `_plan_act` |  |  |
| `road:` | `_road` | `_back_option`、`_road_task_options` |  |
| `seal:` | `_seal_act` | `_seal_options` |  |
| `season:` | — | `_everyday_options`、`options` |  |
| `sect:` | `_present` | `_sect_options` |  |
| `sense:` | `_sense` |  |  |
| `smith:` | `_smith` | `_armor_options`、`_dismantle_options`、`_material_options`、`_smith_options`… |  |
| `sortie:` | `_duel_choice` |  |  |
| `step:` | `step_rules.skip` |  |  |
| `story:` | `_story_act` |  |  |
| `talk:` | `_talk` | `_cost_option`、`_everyday_options`、`_parley_options`、`foreshadow.talk_options`… |  |
| `tavern:` | `_tavern_choice` | `_tavern_options` |  |
| `works:` | `_works_act` | `_cost_option`、`_stamina_play_options` |  |
| `zhuan:` | `_zhuan_act` | `_zhuan_options` |  |

`Game._act` 子分派 28 條：

| 行 | id | 處理 |
|---:|---|---|
| 4732 | `act:explore` | `_explore_one` |
| 4734 | `act:explore` | （就地處理） |
| 4736 | `act:break` | `_finish_seclusion` |
| 4738 | `act:halt` | `_halt` |
| 4740 | `act:part` | `_part_ways` |
| 4742 | `act:recruit` | `_recruit` |
| 4744 | `act:recruit:*` | `_recruit_one` |
| 4746 | `act:rest` | `_rest` |
| 4748 | `act:duty` | `_duty` |
| 4750 | `act:rank2` | `_rank2` |
| 4755 | `act:convoy` | `_take_convoy` |
| 4757 | `act:bounties` | `_shop_say` |
| 4763 | `act:smith` | `_shop_say` |
| 4769 | `act:market` | `_shop_say` |
| 4774 | `act:arena` | arena.standing |
| 4778 | `act:heal` | `_heal_msgs` |
| 4780 | `act:dadian` | `_shop_say` |
| 4785 | `act:silver_donate`、`act:mentor`、`act:furnace`、`act:buy_legend`、`act:bribe:*` | `_silver_act`、`_shop_say` |
| 4790 | `act:donate` | `_shop_say` |
| 4794 | `act:tavern` | `_tavern_enter` |
| 4796 | `act:drill` | `_town_drill` |
| 4798 | `act:call` | （就地處理） |
| 4801 | `act:challenge:*` | `_challenge` |
| 4804 | `act:summons` | `_present` |
| 4806 | `act:train` | `_duel_entry` |
| 4809 | `act:explore`、`act:socialize` | `_present` |
| 4812 | `act:explore` | `_explore` |
| 4814 | `act:train` | `_parley_backing_here`、`_sortie`、`_train` |

## 六、`bot_policy.score`（第 809～965 行，157 行）照前綴分的段

| 行 | 前綴 | 行數 |
|---|---|---:|
| 812～813 | `defect:` | 2 |
| 814～815 | `aid:`、`ambush:`、`works:` | 2 |
| 816 | （`features_core.bot_pick`：功能包先答） | 1 |
| 819～820 | `opp:` | 2 |
| 821～822 | `battle:` | 2 |
| 823～824 | `seal:` | 2 |
| 825～826 | `duel:` | 2 |
| 827～828 | `sect:` | 2 |
| 829～833 | `choice:` | 5 |
| 834～860 | `explore:` | 27 |
| 861～862 | `talk:` | 2 |
| 863～869 | `bounty:` | 7 |
| 870～871 | `smith:` | 2 |
| 872～873 | `arena:` | 2 |
| 874～875 | `tavern:` | 2 |
| 876～877 | `market:` | 2 |
| 878～881 | `call:` | 4 |
| 882～890 | `move:` | 9 |
| 891～960 | `act:` | 70 |
| 961～962 | `dadian:` | 2 |
| 963～964 | `donate:` | 2 |

`act:` 那一段的子分支 22 條：act:tavern@892、（plan is not None）@895、act:explore@897、act:challenge:*@899、act:challenge:*@901、act:call@907、act:bounties@909、act:smith@911、act:arena@915、act:market@917、act:heal@919、act:explore@921、act:socialize@923、act:train@925、act:drill@940、act:duty@942、act:rank2@946、act:convoy@948、act:summons@950、act:dadian@952、act:donate@956、act:recruit:*@958

`bot_policy`、`bot`、`bot_runner` 其他函式裡寫到前綴字串的：26 個函式（`bot_policy.other_prefix_refs`）。

## 七、路由

| 方法 | 路徑 | handler | 行 | 行數 | 直接叫的 Game 方法 | 經動作表 | 經殼函式 |
|---|---|---|---|---:|---:|---:|---:|
| GET | `/` | `index` | 2452～2454 | 3 | 0 | 0 | 0 |
| GET | `/journal.css` | `journal_css` | 2457～2459 | 3 | 0 | 0 | 0 |
| GET | `/api/patch_notes` | `api_patch_notes` | 2462～2465 | 4 | 0 | 0 | 0 |
| GET | `/api/me` | `me` | 2468～2471 | 4 | 0 | 0 | 19 |
| POST | `/api/login` | `api_login` | 2474～2478 | 5 | 0 | 0 | 19 |
| POST | `/api/register` | `api_register` | 2481～2485 | 5 | 0 | 0 | 19 |
| POST | `/api/character` | `api_character` | 2488～2492 | 5 | 0 | 0 | 19 |
| POST | `/api/logout` | `api_logout` | 2495～2499 | 5 | 0 | 0 | 0 |
| GET | `/api/main` | `api_main` | 2502～2506 | 5 | 0 | 0 | 18 |
| POST | `/api/choose` | `api_choose` | 2614～2635 | 22 | 0 | 0 | 6 |
| POST | `/api/answer` | `api_answer` | 2638～2644 | 7 | 0 | 0 | 4 |
| POST | `/api/say` | `api_say` | 2647～2653 | 7 | 0 | 0 | 4 |
| POST | `/api/do/{op}` | `api_do` | 2656～2705 | 50 | 2 | 66 | 22 |
| GET | `/api/peer` | `api_peer` | 2773～2777 | 5 | 1 | 0 | 0 |
| GET | `/api/figure` | `api_figure` | 2780～2785 | 6 | 1 | 0 | 0 |
| POST | `/api/peer/act` | `api_peer_act` | 2788～2814 | 27 | 2 | 0 | 1 |
| POST | `/api/party/leave` | `api_party_leave` | 2817～2823 | 7 | 1 | 0 | 0 |
| GET | `/api/menxia` | `api_menxia` | 2826～2829 | 4 | 0 | 0 | 18 |
| POST | `/api/menxia/{op}` | `api_menxia_do` | 2832～2863 | 32 | 1 | 26 | 19 |
| GET | `/api/prologue` | `api_prologue` | 2866～2870 | 5 | 1 | 0 | 0 |
| GET | `/api/howto` | `api_howto` | 2873～2878 | 6 | 1 | 0 | 0 |
| POST | `/api/sense` | `api_sense` | 2881～2887 | 7 | 0 | 0 | 2 |
| POST | `/api/sense_read` | `api_sense_read` | 2890～2899 | 10 | 0 | 0 | 0 |
| POST | `/api/sense_warm` | `api_sense_warm` | 2902～2906 | 5 | 0 | 0 | 0 |
| POST | `/api/forge_line` | `api_forge_line` | 2909～2918 | 10 | 3 | 0 | 0 |
| POST | `/api/smith_line` | `api_smith_line` | 2921～2926 | 6 | 1 | 0 | 4 |
| GET | `/api/reports` | `api_reports` | 2929～2932 | 4 | 0 | 0 | 5 |
| GET | `/api/tale/{battle_id}` | `api_tale` | 2970～2973 | 4 | 0 | 0 | 0 |
| GET | `/api/boards` | `api_boards` | 3091～3097 | 7 | 1 | 0 | 0 |
| GET | `/api/board_card` | `api_board_card` | 3100～3109 | 10 | 0 | 0 | 0 |
| GET | `/api/mingtie` | `api_mingtie` | 3113～3118 | 6 | 1 | 0 | 0 |
| POST | `/api/mingtie/{op}` | `api_mingtie_do` | 3121～3138 | 18 | 4 | 0 | 0 |
| GET | `/api/annals` | `api_annals` | 3141～3145 | 5 | 1 | 0 | 0 |
| GET | `/api/xingshi` | `api_xingshi` | 3148～3152 | 5 | 1 | 0 | 0 |
| GET | `/api/zhuan` | `api_zhuan` | 3255～3259 | 5 | 0 | 0 | 1 |
| POST | `/api/zhuan/write` | `api_zhuan_write` | 3262～3270 | 9 | 1 | 0 | 2 |
| POST | `/api/zhuan/share` | `api_zhuan_share` | 3273～3281 | 9 | 1 | 0 | 1 |
| GET | `/zhuan/{code}` | `zhuan_page` | 3284～3294 | 11 | 0 | 0 | 0 |
| GET | `/api/map` | `api_map` | 3318～3322 | 5 | 0 | 0 | 6 |
| GET | `/api/map/base` | `api_map_base` | 3325～3329 | 5 | 0 | 0 | 2 |
| GET | `/api/map/state` | `api_map_state` | 3332～3336 | 5 | 1 | 0 | 0 |
| POST | `/api/travel` | `api_travel` | 3339～3362 | 24 | 2 | 0 | 7 |
| POST | `/api/password` | `api_password` | 3365～3368 | 4 | 0 | 0 | 0 |
| GET | `/api/queue` | `api_queue` | 3371～3376 | 6 | 0 | 0 | 0 |
| GET | `/api/events` | `api_events` | 3379～3392 | 14 | 0 | 0 | 0 |
| GET | `/api/push` | `api_push` | 3402～3407 | 6 | 0 | 0 | 0 |
| POST | `/api/push/prefs` | `api_push_prefs` | 3410～3418 | 9 | 0 | 0 | 0 |
| POST | `/api/push/test` | `api_push_test` | 3421～3431 | 11 | 0 | 0 | 0 |
| POST | `/api/push/subscribe` | `api_push_subscribe` | 3434～3453 | 20 | 0 | 0 | 0 |
| POST | `/api/push/unsubscribe` | `api_push_unsubscribe` | 3456～3461 | 6 | 0 | 0 | 0 |
| GET | `/sw.js` | `service_worker` | 3464～3467 | 4 | 0 | 0 | 0 |
| GET | `/manifest.webmanifest` | `manifest` | 3470～3473 | 4 | 0 | 0 | 0 |
| GET | `/api/admin` | `api_admin` | 3476～3481 | 6 | 1 | 0 | 8 |
| POST | `/api/admin/player` | `api_admin_player` | 3484～3492 | 9 | 2 | 0 | 0 |
| POST | `/api/admin/reset_password` | `api_reset_password` | 3495～3497 | 3 | 0 | 0 | 1 |
| GET | `/api/mall` | `api_mall`（tianxia/features/mall/routes.py） | 54～58 | 5 | 0 | 0 | 0 |
| GET | `/api/mall/records` | `api_mall_records`（tianxia/features/mall/routes.py） | 60～64 | 5 | 0 | 0 | 0 |
| POST | `/api/mall/buy` | `api_mall_buy`（tianxia/features/mall/routes.py） | 66～84 | 19 | 0 | 0 | 0 |
| POST | `/api/mall/claim` | `api_mall_claim`（tianxia/features/mall/routes.py） | 86～93 | 8 | 0 | 0 | 0 |
| POST | `/api/mall/rename` | `api_mall_rename`（tianxia/features/mall/routes.py） | 95～114 | 20 | 0 | 0 | 0 |
| POST | `/api/admin/mall` | `api_admin_mall`（tianxia/features/mall/routes.py） | 116～124 | 9 | 1 | 0 | 0 |

動作表：`MAIN_ACTIONS` 27 個 op（第 2511～2551 行）；`ADMIN_ACTIONS` 38 個 op（第 2555～2604 行）；`MENXIA_ACTIONS` 27 個 op（第 2732～2770 行）。

殼的共用管線（被 5 個以上殼函式／路由直接叫，遞移時略過）：`_account`（9）、`_game`（38）、`_locked`（13）、`_open_request`（18）、`_tell_tabs`（10）、`_web_push`（5）、`account_store`（10）、`act`（23）、`joined`（7）、`look`（29）、`main_view`（10）、`md`（11）、`model_call`（20）、`within_budget`（23）。

## 八、web 與 content

| web 檔 | 行數 | bytes | 頂層 function 宣告 | const 物件 | 頂層宣告合計 |
|---|---:|---:|---:|---:|---:|
| `web/app.js` | 6,846 | 554,748 | 336 | 26 | 537 |
| `web/icon.svg` | 1 | 219 |  |  |  |
| `web/index.html` | 40 | 2,680 |  |  |  |
| `web/main.js` | 1,867 | 176,360 | 124 | 10 | 263 |
| `web/mall.css` | 139 | 13,342 |  |  |  |
| `web/mall.js` | 398 | 27,926 | 33 | 1 | 43 |
| `web/manifest.webmanifest` | 15 | 611 |  |  |  |
| `web/map.js` | 1,649 | 122,654 | 124 | 16 | 224 |
| `web/outing.js` | 718 | 42,736 | 45 | 3 | 80 |
| `web/style.css` | 3,568 | 326,684 |  |  |  |
| `web/sw.js` | 33 | 1,389 | 0 | 0 | 0 |
| `web/zhuan.css` | 131 | 10,479 |  |  |  |
| 圖、影片等二進位檔 130 個 | | 9,428,814 | | | |

content：頂層 53 檔（738,632 bytes）、`events/` 37 檔（1,074,973 bytes）、`profiles/` 3 檔（season21.json、week7.json、weekend.json）。

## 九、測試（ast 數 `def test_`，參數化算一條）

| 資料夾 | 檔 | test_*.py | test 函式 | 其中 slow |
|---|---:|---:|---:|---:|
| `tests/acts` | 30 | 30 | 600 | 203 |
| `tests/arts` | 38 | 38 | 905 | 34 |
| `tests/battle` | 52 | 52 | 956 | 112 |
| `tests/bots` | 23 | 23 | 541 | 26 |
| `tests/（根）` | 1 | 0 | 0 | 0 |
| `tests/core` | 101 | 101 | 2,310 | 145 |
| `tests/figures` | 44 | 44 | 1,394 | 80 |
| `tests/fixtures` | 30 | 0 | 0 | 0 |
| `tests/gear` | 25 | 25 | 676 | 0 |
| `tests/kit` | 8 | 0 | 0 | 0 |
| `tests/map` | 14 | 14 | 206 | 58 |
| `tests/ranger` | 14 | 14 | 206 | 59 |
| `tests/seal` | 13 | 13 | 286 | 90 |
| `tests/season` | 11 | 11 | 246 | 63 |
| `tests/server` | 14 | 14 | 561 | 20 |
| `tests/web` | 44 | 44 | 724 | 84 |
| `tianxia/features/feast/tests/（根）` | 2 | 1 | 10 | 0 |
| `tianxia/features/mall/tests/（根）` | 10 | 10 | 175 | 100 |
| `tianxia/features/sortie/tests/（根）` | 4 | 4 | 31 | 8 |
| **合計** | | 438 | 9,827 | 1,082 |

## 十、現有功能包與整套拿掉的

- `tianxia/features/feast`：prefix `feast`，bot_always ['feast:']，非測試 482 行，7 個檔
- `tianxia/features/mall`：prefix `None`，bot_always []，非測試 1,178 行，16 個檔
- `tianxia/features/sortie`：prefix `None`，bot_always []，非測試 646 行，8 個檔
- `sys.modules` 舊名別名：`tianxia.feasts` → `tianxia.features.feast.rules`、`tianxia.mall` → `tianxia.features.mall.rules`、`tianxia.sortie` → `tianxia.features.sortie.rules`

**整套拿掉**（企劃者 10/31：只剩 week7、season21；排在搬完六包之後，不規劃搬包）：

- `tianxia/explore_modes.py`（229 行；被 12 個非測試模組、9 個測試檔 import）
- `tianxia/gather_llm.py`（50 行；被 3 個非測試模組、1 個測試檔 import）
- `content/gather_branches.json`（701 bytes）：探索三選一用的（整套拿掉時一起看）
- `content/profiles/weekend.json`（145 bytes）：整套拿掉（週末設定／探索三選一）
- Game 方法裡用到 explore_modes／gather_llm 的：21 個、893 行（`game_methods[].touches_removal`）：`_explore_mode_options`、`_gather_branch_options`、`_seek_option`、`_practice_option`、`_boss_away`、`_practice_line`、`action_notes`、`choose`、`gather_text_request`、`gather_say`、`_action_title`、`_act`、`_explore_mode`、`_gather`、`_home_gather`、`_gather_say`、`_practice`、`_gather_fight`、`_seek`、`_explore_one`、`_arrive`
- 不帶設定的 14 天季、週末設定：散在 `Config`／`content.py` 的 profile 判斷，這份盤點不逐條列（另派）

