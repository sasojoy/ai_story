# 探索 `tianxia/features/explore/`

- **做什麼**：減法季的「探索」那一格——**探索一顆**（出門一趟只碰上一件事：遭遇、事件、素材、感悟，照地點的表抽；三道閘的前兩道；頭目擋路；自家營寨跟同袍比劃；城裡的地痞）與**走一趟**（按一次探索走一、三、五段，每一段就是一次探索一顆；停在要選的事上、選完接著走；打輸、氣血見底、體力不夠回頭；走完留一句〔預設三句免費、自己寫的用一張題壁墨〕、遊記；路上看到別人的留言與揮手；撿到稀世的東西、以弱勝強記一則行狀）。開關：減法季的 `explore_one`、`outing` 兩個子開關（`rules.jianfa`；season21、week7 開，不帶設定、weekend、測試內容關）。主動搬六包第 3＋4 批（企劃者 10/31「趕快拆」，兩批合成一批）搬進來；**探索三選一**（`explore_modes.py`、`gather_llm.py` 與 Game 上它的方法）企劃者 10/31 定不搬、留在 engine。
- **導覽**：`docs/guide/行動與地盤.md` 的「減法季探索一顆」那幾段（模組那一節的 `explore_one`／走一趟兩條、行動那一節的「減法季探索一顆」）、`docs/guide/戰鬥.md` 的「減法季三道閘」；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：沒有版本號，兩份：探索一顆是 `docs/superpowers/specs/2026-10-24-減法季-整合設計.md` 4.1（4.2 三道閘）；走一趟是企劃者 2026-10-29～30 的設計稿（artifact，網址在 `outing_rules.py` 開頭；不在 specs/），之後 Joy 10/30～31 的幾輪改字、改結算卡照江湖紀錄與程式裡的註記。

## 名字陷阱

名字帶 outing 的有兩樣東西：`explore_actions.py` 裡的 `outing_on`、`outing_foe`、`outing_weights`、`outing_plan_at`（原 `Game._outing_plan`）、`outing_plan`、`outing_option`、`outing_fight`、`outing_event`、`outing_ledger` 是**探索一顆**的（減法季批 2 起叫「出門一趟」）；**走一趟**是疊在上面的一層，在 `outing_actions.py`／`outing_rules.py`。這一批兩樣都進這一包，**不改名**（PM 10/31）。`PlayerState.outing_last` 也是探索一顆的（上一趟要選的那件事），`PlayerState.outing` 才是走一趟的。走一趟與探索一顆之間的互相讀（`Game._beat`、`rare_boost`、`FEAT_*`、`foe_look`）現在是包內。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`ExploreFeature`）：`enabled`＝`rules.jianfa(..., "explore_one")`（不擲骰）、`web = ("outing.js",)`（本來就是獨立的檔，位置不動）、`content = ("outing_lines.json",)`、`player_fields`、`check_content`；`prefix` 是 None（那一格是核心的 `act:explore`） |
| `checks.py` | 內容驗證：探索表（每個地點歸得到一張、城裡的地痞、旅人事件）與段落句子（`content/outing_lines.json`）。原本是核心 `content.py` 的 `check_explore_one`、`check_outing_lines`（核心不 import 包）；「旅人」與至少幾則（`TRAVELER_TAG`、`TRAVELER_MIN`）照舊寫在核心，這裡讀那兩個模組屬性 |
| `explore_rules.py` | 探索一顆的純規則（原 `tianxia/explore_one.py`；那個名字留成別名）：表、比重、抽、自己的亂數、鈕上的小字、段落句子、帳 |
| `explore_actions.py` | 原本 `Game` 上探索一顆的 15 個方法與模組層的 `OutingPlan` |
| `outing_rules.py` | 走一趟的純規則（原 `tianxia/outing.py`；那個名字留成別名）：開關、倍數、這一趟在不在路上、留言與路碑、畫面那一份、遊記 |
| `outing_actions.py` | 原本 `Game` 上走一趟的 12 個方法 |
| `tests/` | `test_explore_package.py`（2 條，含煙霧一條：包的內容驗證擋得下壞的內容、核心與包的「旅人」同一個字）與原本在 `tests/` 底下、整檔屬於這一包的 9 個檔（226 條）：`test_explore_one.py`、`_2e`、`_fix`、`_polish`、`_single`（原 `tests/battle/`）、`test_explore_one_2f.py`、`test_explore_one_rules.py`（原 `tests/core/`）、`test_outing.py`（原 `tests/acts/`）、`test_outing_web.py`（原 `tests/web/`） |

**認領的欄位**（3.5，留在原地）：`PlayerState.outing`（`Outing`、`OutingBeat`）、`outing_last`、`explore_seq`（第幾次探索：跟留在 engine 的探索三選一共用，`seal.find`、`epiphany` 讀）、`fight_day`、`fights_today`（遭遇的疲勞，三道閘的第一道）——換季都跟著新角色重來（`carried` 是空的）；`WorldState.inscriptions`、`inscription_seq`（走一趟的留言）；`Config.jianfa` 的 `explore_one`、`outing` 兩個子開關與 `explore_stamina`、`explore_tables`、`town_foes`、`town_loot_scale`、`camp_spar_share`、`outing_*` 那幾個數字（`jianfa_numbers.py`）；`content/outing_lines.json`。題壁墨這件商品（`inscribe_ink`）在商城的 `mall.json`，經核心的錢包服務（`ctx.wallet`）用。

**Game 上留的一行委派**（18 個，6 個私有；server、假人、腳本、測試與核心原位還在叫）：走一趟 9 個 `outing_go`、`outing_view`、`outing_can_go`、`_outing_watched`（engine 模組層的 `_outing_watch` 套在 `choose`、`answer_event`、`epiphany_names`、`sense_draw` 上叫它；那個裝飾不是 Game 的方法，邊界測試的掃描看不到）、`outing_say`、`outing_tale_request`、`outing_set_tale`、`outing_ink_left`、`admin_erase_inscription`；探索一顆 9 個 `_outing_on`、`_outing_plan`、`mostly_here`、`outing_plan`、`map_mostly`、`_outing_option`、`_explore_one`、`_outing_fight`、`fatigue_next`。包裡只有 `_outing_plan`、`outing_plan`、`_outing_on`、`odds` 經 `ctx` 叫（這一包的 `tests/test_explore_one.py` 換掉 `game._outing_plan`、`test_explore_one_2e`／`_single` 換掉 `game.odds`）；`explore_one.draw`（測試 12 處換掉它）、`team.fight`、`sensing.missed_today` 一律寫模組屬性。

**還留在原位的接縫（過渡；批次表第二節，第 11 批一次收）**：`Game._everyday_options` 最前面探索那一段（`_outing_on`、`_outing_option`）、`_act` 的 `act:explore` 分派（探索一顆開著走 `_explore_one`；扣體力、晉升奇遇、序章的舊探索、探索三選一都在那裡）、`choose` 後半段的探索常數（`PICK`、`GATHER_PICK`、`note_action("explore")`、`field_win`：三選一的）、`action_notes` 底下那一行（`_outing_plan`）、`_action_title`（「出門一趟・某地」）、輿圖（`map_base`、`map_state` 叫 `map_mostly`）、有所感（`_sense` 讀 `outing_rules.rare_boost`）、模組層的 `_outing_watch`；收尾的掉落（回體丹 `_pill_find`、殘譜 `_scrap_find`、破境丹 `_legend_find`、打探懸賞、玉璽碎片 `_seal_find`）照原本的順序在包裡經 `ctx` 叫；`server` 的 `/api/do/outing`、`outing_say`（鎖外審字）、`outing_tale`（鎖外三段式）、`outing_erase`、`/api/main` 的 `outing` 與 `mostly`、輿圖的 mostly；`bot.py` 的 `outing_segments`、`outing_say`；`bot_policy.take_turn` 那兩段（停著的那一趟先接著走、挑到探索就挑段數出發）與 `score` 的 `outing_plan`／`fatigue_next`；`howto`、`mapdata`（`explore_one` 別名）；網頁一行沒動。`tests/core/test_feature_boundaries.py` 的 `GAME_DIRECT`（`_sense`）、`GAME_DELEGATE_CALLERS`（`(_action_title, _outing_on)`、`(map_base, map_mostly)`；另外 7 對的呼叫端在 `GAME_DIRECT` 裡，寫在那一段的註解）逐條寫理由。

**改這一包時 `test_for` 挑不到、要另外跑的**（混在別人檔裡的測試，這一輪不拆，批次表第二節）：改包的檔只挑這一包的 `tests/` 與核心契約，下面這幾個蓋著搬過來的程式卻不在包裡——
- 三道閘的接線（`fight_gate`、45 級以後的經驗）：`tests/battle/test_drill_gates_engine.py`（也驗核心 `_record_exp`，算混合檔）。
- 屬性五段與探索一顆的互動：`tests/battle/test_stat_milestones_engine.py`（整檔 slow）；走一趟、探索一顆的開關與表：`tests/core/test_jianfa_switch.py`（整檔 slow）；一條線的開頭、特殊頓悟的倍數：`tests/core/test_storyline.py`、`tests/core/test_story_wangyue.py`（整檔 slow）；週解鎖的四格小字：`tests/figures/test_week_unlock.py`；真實內容：`tests/season/test_real_content.py`。
- 一起跑：`scripts/test_for.py --base <分支> <改的包檔> tests/battle/test_drill_gates_engine.py tests/battle/test_stat_milestones_engine.py tests/core/test_jianfa_switch.py tests/core/test_storyline.py tests/core/test_story_wangyue.py tests/figures/test_week_unlock.py`（直接給的測試檔連 slow 一起跑）；要不要讓 `test_for` 把混合檔算進包，交 PM 定（出陣包第 1 批同一題）。
- `test_outing.py` 只有幾條超過一秒的標 slow：改走一趟的引擎時帶 `--slow` 才跑得到那幾條。

**過渡 import**：`explore_actions.py` 16 行（events 兩行）、`outing_actions.py` 7 行、`checks.py` 2 行（events 在函式裡）、`outing_rules.py` 1 行（zh 在函式裡），一共 26 行import 還沒搬的舊模組（`bounties`、`duel`、`events`、`explore_modes`、`growth`、`mapdata`、`mapview`、`tavern`……，註「過渡：待搬」）；`tavern.BANNED_WORDS`（留言的禁字）照派工單不搬進 naming（酒肆那條線同時在搬 tavern.py）。`bot`、`bot_policy`、`server`、engine 照舊 `from tianxia import outing`，`howto`、`mapdata` 照舊 `from tianxia import explore_one`（別名）。
