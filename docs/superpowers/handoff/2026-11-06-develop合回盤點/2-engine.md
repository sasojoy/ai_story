# develop 合回主幹盤點 2：develop 改到主幹已搬走的程式

> 11/06 唯讀盤點（工作流程 `wf_4c64148d-820`），量的時候主幹 `0176753d`（檢查者另對 `3e2271a4`）、develop `99f6a79b`。第 27、50 批之後主幹是 `f7b17ed7`，行號開工前重量。

# develop 改到「主幹已經搬走的東西」地圖（只讀，沒改任何檔）

**基準**
- `origin/split/trunk` 是 0176753d，`origin/develop` 是 99f6a79b，錨點 `split-anchor-20261104` 是 17c5199d。
- 下面的行號：主幹寫「主幹 N」，develop 寫「develop N」。

**怎麼量的**
- 兩邊都改過的 .py 有 47 個。我把它們抽到 scratchpad，用 `git merge-file --diff3` 做三方合併（主幹當 ours，develop 當 theirs）。repo 沒碰。
- 合併結果在 `C:\Users\ray61\AppData\Local\Temp\claude\4d5f79bfb143ac0b\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\mf\*.merged`。

**衝突數**
- engine.py 14、core/registry.py 3、server.py 2、content.py 2、core/__init__.py 2。
- 以下各 1：bot.py、bot_policy.py、companion_agent.py、core/services.py、cultivation.py、epiphany.py、features/guide/actions.py、foreshadow.py、plans.py、rules.py、rumor_view.py、sensing.py、smithing.py、storyline.py、zhuan_html.py。
- 測試：test_feature_boundaries、test_test_for 各 1；test_explore_modes、test_gather_branches_web 是主幹刪掉、develop 改過。

**先後的提醒**
- 第 27 批（origin/dev/seal-1，44d4fbc1）還沒進主幹。它在 engine 的 `_seal_challenge`、`_seal_spectators`、`_seal_side_of`、`seal_gamble`、`admin_seal_duel` 這幾行把 `seal.` 改成 `seal_rules.`；也改了 rules.py、core 三檔、battle/view.py。
- 第 50 批：origin/dev/map-2（251df23a）還是主幹的祖先，origin 上查不到它的程式。
- 下面的主幹行號在 27、50 合進來之後都要重量。

---

## 一、engine.py 的每一個 hunk

### (A) 方法還在主幹 engine，照原位套

**頂端 import 與常數**
- **import**（主幹 16–25）
  - 加 `from . import attrset`。
  - 括號那一串用主幹的版本，只補 `place_state`（location_text、scene_art 留在核心，也要讀它）。
  - develop 那一行帶的 annals、checkin、chuangong、cultivation、explore_modes、gather_llm 等，主幹已經拿掉，不要帶回來。
- **常數** `GROWTH_PREFIX`、`GROWTH_LOCKED`、`GROWTH_CUSTOM_ASK`（develop 314–316，原本夾在 `PREPARING_TEXT` 中間）
  - 主幹那裡只剩註解（主幹 293–295），`PREPARING_*` 已搬到 core/services。
  - 三句照樣放 engine 模組層：bot.py:20 是 `from .engine import GROWTH_PREFIX`。

**照原位插的 hunk**
- **`Game.new`**（主幹 463–505）：插在主幹 490–491 之後。
- **`_reset_player_for_new_season`**（主幹 545–649）
  - 插在主幹 640 之後：`fresh.player.legacy = old.player.legacy`（2f4ae10d）。
  - 跟主幹寫法一致：出陣包照帶的兩格也在這裡（主幹 611 的註解）；legacy 包已宣告 `carried=("legacy",)`。
- **`_deliver_away`**（主幹 948–951）：上線邸報，改成 gazette（b96fd295）。
- **`_everyday_options`**
  - 在主幹 1100（休季那一顆）之後、1101 之前插開季準備（ef6d4faa）。
  - 主幹 1112：`renown.meets` 改成 `renown.open_to(s, c, "choices", …)`（169fa2b5）。
- **`choose`**：growth 前綴插在主幹 1727（`option is None or not option.enabled`）之後、1728（`faction_before`）之前。
  - **不要改成包的 choose 掛鉤**。主幹的 `features_core.choose` 排在 `battle_card = None`、`guide_done = []` 之後；develop 的 growth 在清這兩格之前就 return。搬成掛鉤就會多清這兩格，行為不同。
  - 這裡叫的 `self.pick_growth` 如果成了一行委派，`GAME_DELEGATE_CALLERS` 要加 `("choose", "pick_growth")`。
- **`_battle_role`**（主幹 2895–2898）、**`_battle_marks`**（主幹 2934–2936，`seal_bare` 之後加 `card`）：90360171。
- **玉璽那五個方法**（主幹 3247–3335）
  - `_seal_challenge`：主幹 3276 `open_duel` 之前加 `seal_duel.faced`。
  - `_seal_spectators`：主幹 3315–3317 加 `card=`。
  - `_seal_side_of`：主幹 3331–3334 加 `card=`。
  - `seal_gamble`：主幹 5154 換成 charm 那一行（69093561）。
  - `admin_seal_duel`：主幹 6022 前後。
  - 第 27 批不搬這五個（屬第 28 批），但第 27 批改的就是同幾行，合了 27 再套會有小衝突。第 28 批搬它們時，develop 這幾行要一起帶走。
- **其餘照原位套的**
  - `_squad_encounter`：主幹 3686，加 `squad=`（0a09c32f）。
  - `_take_toll`：主幹 4034–4047。
  - `_play_rounds`：主幹 4078（`v1_stat`）。
  - `_story_squad`：主幹 4148，`rise.on(c, s.world)`。
  - `_spar_power`：主幹 4949 用 `facing_player` 包住。
  - `location_text`：主幹 6334–6338；`scene_art`：主幹 6374。
  - `status_data`：主幹 6506–6508，attrs、stat_cap，再加 growth、lilian 兩個鍵。
- **說明字**：core/services.py:73 寫的 `ctx._take_toll(tier, wild=, clash=)` 補上 `squad=`。

### (B) 主幹已搬走（Game 只剩一行委派），改動要改寫進包

- **`_recruit_targets`** → `tianxia/features/companions/actions.py:40 recruit_targets`
  - 第 43 行：`roster.on(ctx.content)` 改成 `roster.on(ctx.content, ctx.state.world)`（704cc885）。
- **`_explore_weights`** → `features/explore/explore_base.py:90`
  - 第 96 行改成 `team.v1_stat(s, c, "wis")`（4be00ea3）。
- **`challenge_odds`、`_figure_squad`、`_challenge`** → `features/figure_acts/challenge.py`
  - 77：`rise.draw_floor(ctx.content, ctx.state.world)`。
  - 84 之後插：`if attrset.on(c, s.world): return attrset.figure_squad(c, s.world, squad, s.world.time)`（c83b0fbc）。
  - 85：`rise.on(c, s.world)`。
  - 107：`rise.draw_floor(c, s.world)`。
  - 138：`ctx._take_toll(…, squad=squad)`。
  - 第 13 行的 import 補 `attrset`（核心）。
- **`_finish_seclusion`** → `features/seclusion/actions.py:41 finish`
  - 第 46 行改成 `team.v1_stat(ctx.state, ctx.content, "wis", 0)`。
  - 這個檔沒 import team（第 8 行只有 journal、prologue、treasures），要補。
- **`allocate_stat`** → `features/cultivation/actions.py:284–312`（`@not_while_preparing` 掛在包的函式上）
  - 在 `p, cfg = …` 之後插：`if attrset.on(ctx.content, ctx.state.world): return allocate_v2(ctx, stat)`。
  - import 補 attrset。
- **`_raid_spoils`** → `features/peers/raid_actions.py:168`；**`_ambush_spoils`** → `features/stamina_plays/ambush_actions.py:138`
  - 兩處的 `agi=lp.stats.get("agi", …)`（180、166）都改成 `agi=team.v1_stat(loser.state, c, "agi")`。

### (C) develop 新加的 9 個方法，建議放哪

**修練包**
- **`_allocate_v2`**（develop 8820）→ `cultivation/actions.py` 新函式 `allocate_v2(ctx, stat)`。
  - self 換成 ctx 即可：`_log`、`_guide`、`_note_action` 都在服務清單上。
  - develop 邊界測試加的 `("_allocate_v2", "_note_action")`（develop tests/core/test_feature_boundaries.py:470）拿掉。
- **`pick_growth`**（develop 8858）→ 本體進 `cultivation/actions.py`，Game 留委派。
  - 叫它的：server 的 MAIN_ACTIONS "growth"（develop server.py:2875）、bot.py:127、guide 包的 `ctx.pick_growth`。
  - **`Refused` 只在主幹 engine.py:287，包拿不到**。照 bout/arena_actions.py:494「Game 原位照它回 Refused」的前例：Game.pick_growth 自己保留三步——`@_not_while_preparing`、「這一季沒有成長配比」、「已經定了 → `Refused(self._log([GROWTH_LOCKED]))`」，先後照 develop。
  - `services.py:459`（`# guide` 段）加 `ctx.pick_growth(preset)`。
  - `GAME_DELEGATES` 加 `pick_growth`；`("pick_growth", "_note_action")` 拿掉。

**留在核心（engine）**
- **`_season_prep`、`season_prep_view`**（develop 8835、8847）：建議留 engine。
  - 它跟 `_everyday_options` 一樣，是照 FEATURES 問 `prep` 掛鉤的核心選單；`prep` 掛鉤在 core/features.py 已經乾淨合進去。
  - 稽核第 6 節把「prep 掛鉤留不留」列為待 PM 定。
- **`_attr_rows`**（develop 12065）：留 engine，是 status_data 的一部分。
- **`place_state_view`**（develop 3385）：建議留 engine。
  - 它只讀共用規則層的 place_state，location_text 和 scene_art 也在核心讀同一個。
  - 另一案（11/05 稽核）：跟 place_deeds_view 一起進 `figure_acts/plan_actions.py:46`，Game 留委派。

**交友求見包、人物情誼包**
- **`figures_here_view`**（develop 2780）→ 建議進 `features/socialize/view.py`，Game 留委派。它用到的 social_plan、audience_options、talkable、why_not_talk 都屬這一包。改法：
  - `self._figures_here()` → `ctx._figures_here()`（服務清單上有）。
  - `self._social_plan()` → `social_plan(ctx)`。
  - `self._audience_options()` → `menus.audience_options(ctx)`。
  - `self._talkable` / `self._why_not_talk` → `talkable(ctx, cid)` / `why_not_talk(ctx, cid)`（view.py:25、30）。
  - 它讀的 `p.pending_companion` 是人物情誼包認領的欄位（companions/__init__.py:21–27），記進交友包 README「包外直接讀寫的」。
- **`talk_view`**（develop 2816）→ 建議進 `features/companions/talk_actions.py`（`pending_companion` 是這一包的），Game 留委派。
- **`_figure_side_name`**（develop 2810）→ 它只讀 content.figures 和 scenario。建議放進共用規則層 `tianxia/figures.py`（例如 `side_name(content, fid)`），兩包各自叫，避免包叫包。

**登記**
- 新的委派都加進 `GAME_DELEGATES`。
- engine 會用到的包模組（`socialize_view`、`companions_talk`、`cultivation_actions`、`figure_plan_actions`）主幹已經 import，`GAME_IMPORTS` 不用動。

---

## 二、其他檔

### (A) 主幹已成別名的舊模組（develop 改到 8 個）

- **`tianxia/cultivation.py`** → `features/cultivation/cultivation.py`：125、138 改成 `team.v1_stat(state, content, "wis")`。
- **`tianxia/epiphany.py`** → `features/sense/epiphany.py`
  - 第 35 行加 `from tianxia import attrset`。
  - 157：`attrset.legacy(state, content, "wis", 5)`。
  - `roll`：在 174 那行（`rng.random() < odds * boost` 就回真）之後插重擲那兩行，另加新函式 `_luck_reroll`（9167c73f、169fa2b5）。
- **`tianxia/sensing.py`** → `features/sense/sensing.py`：第 22 行 import 加 attrset；141 改成 `attrset.legacy(…)`。
- **`tianxia/smithing.py`** → `features/smithy/smithing.py:140`，改成 `team.v1_stat(...)`。
- **`tianxia/storyline.py` 的 `roll_start`** → **不在包裡，在共用規則層 `tianxia/story_base.py:160`**
  - 171 之後插 `_luck_again` 那兩行；`_luck_again` 本體也放 story_base。這裡寫 `from .renown import legacy_door` 是同一層，合法。
  - `features/story/storyline.py:34–37` 的 re-export 清單加 `_luck_again`。
- **`tianxia/foreshadow.py`** → `features/military/fs_rules.py:522`：`renown.warmed(content, delta, state)`。
- **`tianxia/companion_agent.py`** → `features/companions/companion_agent.py:434`：`renown.warmed(content, cooled, state)`。
- **`zhuan_html.py`** → `tianxia/features/zhuan/zhuan_html.py`
  - 加 `import re` 和 SCRIPT 那一行。
  - 新函式 `text()` 放在 `seal()`（42）後面。
  - `page()`（78）裡的 body/ping，還有 `<body class>`、`<main>` 兩行。

### (B) 沒成別名，但主幹改了結構

**規則層與內容**
- **`rules.py`**：develop 改的是舊 `apply_effect` 的屬性迴圈（develop 1113–1120）。主幹第 32 批把它拆成 `_fx_stats(r)`（主幹 1101）。
  - 迴圈頭換成 `v2 = attrset.on(…)` 加上 `for key, delta in _season_stats(effect, state, content):`，再接 v2 那三行。
  - 情誼那一行（`_fx_affinity`，主幹 1168）三方合併已經自己套上。
- **`rumor_view.py`**（共用規則層）
  - 用主幹第 10–11 行（calendar、orders，加 `core.omen_base`），只補 `deeds`。
  - develop 那一行帶的 foreshadow、opportunities 現在是軍情包的別名，帶回來邊界會紅。新的 gazette 函式沒用到那兩個。
- **`content.py`**
  - import 區用主幹的版本（沒有 GatherBranch，有 DIALOGUE_TAGS），加 Check、StatDef、PLACE_KINDS。
  - `check_xingshi_lines` 主幹已搬進地盤包（content.py:691）。`check_attributes(c, need)` 放在 `check_art` 之後、`check_traits` 之前。
- **`plans.py`**：只有模組說明字衝突，兩邊的字合寫。

**假人**
- **`bot.py`**
  - 第 15 行用主幹的版本，加 attrset；第 20 行加 `GROWTH_PREFIX`。
  - 其餘合得乾淨（主幹的 bot.py 已經 import hashlib）。
- **`bot_policy.py`**
  - growth 的分數那兩行（develop 822–823）放在主幹 700 那行註解附近，`features_core.bot_pick` 之後。growth 不是任何包的前綴，位置不影響結果。
  - `GROWTH_SCORE`（develop 542）照帶。

**殼（server.py）**
- `import tale_html` 照加：戰記還沒成包，排第 52 批。
- `api_talk_log`（develop 3136）原本夾在 api_figure 和 api_peer_act 之間，那三條在主幹已經各自搬進包。
  - 建議進 `features/companions/routes.py`，跟 `/api/figure` 放一起；照主幹的寫法，當下讀 `shell._game`、`shell.talk_store()`、`shell.figure_face`。
  - `talk_log.py` 讀的 `used_dialogue_options`、`dialogue_history` 是人物情誼包的欄位（companions/__init__.py:24、29），建議整個一起進包。server.act 的快照和記帳留在殼，改成 import 包裡那一份。
- server.py 其餘的改動合得乾淨，留在殼。

**核心三檔**
- `core/__init__.py`：MODULES 用主幹的版本（多了 world、log_archive、step、weekcard），再加 `"attrset"`。
- `core/registry.py`
  - legacy、hire 的 import 和 FEATURES 都接在 gear 後面。
  - SHARED 加 develop 的 `place_state` 那一條。
  - **這兩項（attrset 進 MODULES、place_state 進 SHARED）一定要帶過去**。develop 讓 rise、roster、insight_fx、renown（函式裡）import attrset，讓 plans、conquest、territory、timetable、mounts、figure_life import place_state。沒登記的話，`test_the_shared_rules_layer_only_imports_the_core_and_itself` 會紅。
- `core/services.py:459`：加 `ctx.pick_growth(preset)`。

**新手引導包**
- `guide/actions.py`：見三第 4 條。

### (C) 合得乾淨、方法還在原檔，不用搬

- bout 的 arena_actions、arena_rules、duel_actions；battle 的 muster、view；guide 的 hints、rules；sortie/duel_actions。
- figure_life、conquest、events、models、state、mounts。
- core/features（`prep` 掛鉤）、run_studio、scripts 的 measure_gear、same_behavior。
- 這些合併結果我用粗略的「未定義名稱」掃了一遍，是 0。

### (D) 測試檔

- 主幹刪掉的 test_explore_modes、test_gather_branches_web（第 13 批）：develop 只各改 2～4 行，跟著刪。
- 主幹改名搬進包的 9 支，git 會依改名追到新路徑套上。

---

## 三、字面不撞、執行才壞

1. **`figures_here_view` 叫 `self._talkable`、`self._why_not_talk`**（develop engine.py:2802、2804）。
   - 主幹 Game 已經沒有這兩個，`/api/main` 一畫就 AttributeError。
   - 改法見一(C)。我對主幹已不在 Game 上的 170 個成員，掃了 develop 所有新增行（`x.名字` 和字串），只命中這兩個。
2. **`_luck_reroll` 裡的 `from .renown import legacy_door`** 搬進 `features/sense/epiphany.py` 之後，會去找 `tianxia.features.sense.renown`。
   - 結果是每次頓悟沒擲中都 ModuleNotFoundError。要寫 `from tianxia.renown import legacy_door`。
   - sensing、epiphany 頂端的 `from . import attrset` 同樣要改成 `from tianxia import attrset`。
3. **簽名多了 `world`／`state` 參數，預設 None 時照舊**：主幹包裡的舊呼叫不會報錯，但五項屬性的季會照舊規則跑。
   - 要手動補的：companions/actions.py:43；challenge.py:77、85、107；fs_rules.py:522；companion_agent.py:434；還有 challenge.py:138 少了 `squad=`。
   - muster.py:60、bout/duel_actions.py:47、figure_life:417、plans:414、rules:1168 三方合併會自己套上。
4. **`guide/actions.py` 的 `_more_triggers`**（develop 346–380）和第 10 行 `from tianxia import checkin, chuangong, seal`。
   - checkin、chuangong 在主幹已是包的別名，第 27 批之後 seal 也是。這等於包 import 包，邊界會紅，寫了「過渡：待搬」也不算。
   - 改法：
     - `checkin.on` → `services.checkin_on`（core/services.py:759）。
     - seal 那兩個 → `core/seal_base` 的 `on` / `key` / `holders`（dev/seal-1 上有）。
     - chuangong 那兩個 → 新開一個 Game 一行委派給修練包，照 `ctx._recruit_target` 的前例。
     - develop 第 9 行帶回的 create、sensing 改用主幹的第 9–10 行。
   - **連帶**：develop 新加的 tests/arts/test_hints.py 換的是 `checkin.on`、`seal.on`、`seal.shard_of`。改讀核心之後這幾個換不到，測試要改換 `services.checkin_on`、`seal_base.on` / `holders`；包裡也要照模組屬性當下讀，換的才打得到。
5. **develop 新的 tests/core/test_attributes.py**，ALLOWED 寫死 `"tianxia/chuangong.py": 3`。
   - 主幹上那 3 處在 `features/cultivation/chuangong.py`（138、145、191）。key 要改成新路徑。
   - 這條掃描也會抓到一(B)、二(A) 漏改的直接讀屬性：主幹現在還有 engine.py:4078、explore_base:96、cultivation.py:125/138、seclusion/actions:46、raid_actions:180、ambush_actions:166、epiphany:157、sensing:141、smithing:140、sortie/duel_actions:685（最後這個合併會自己套）。
   - 全部改完之後，應該只剩 chuangong 3、models 3、skillview 1、team 4。
6. **tests/server/test_talk_log.py:60–65 直接叫 `server.api_talk_log`**：路由搬進包之後這個名字就沒了，測試要改。
7. **`storyline._luck_again`**（test_legacy.py:339、341）：story_base 那一份沒有 re-export 的話是 AttributeError。
8. **`pick_growth` 的 Refused 丟了不會報錯**，但網頁不會跳提示：server.py:2835、2839 是看 `isinstance(…, Refused)` 決定的。
9. **`bot.py:20 from .engine import GROWTH_PREFIX`**：常數如果搬走，engine 要留 re-export。

**另外查過、沒問題的**
- develop 新增行裡的 `from tianxia.<模組> import <名>` 和 `<模組>.<名>`（別名照實解到包），對照主幹已搬走的名字：除了 develop 自己新開的 legacy、hire 包，沒有命中。
- develop 新增行沒用到 atlas。用到 seal 的只有 guide 那一處。
- legacy、hire 兩包碰 Game 的只有 state、content、world、`_write`，都在主幹的服務清單上；import 都是核心或共用層。
