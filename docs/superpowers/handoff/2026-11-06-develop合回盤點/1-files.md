# develop 合回主幹盤點 1：逐檔分類

> 11/06 唯讀盤點（工作流程 `wf_4c64148d-820`），量的時候主幹 `0176753d`（檢查者另對 `3e2271a4`）、develop `99f6a79b`。第 27、50 批之後主幹是 `f7b17ed7`，行號開工前重量。

**develop 合回主幹：逐檔分類地圖（11/06）**

**〇、基準先講清楚（跟派工單的數字不一樣）**
- 我照派工單的指令 fetch 時，develop 從 `40c30129` 前進到 `99f6a79b`：多了 PR #171～#175，是 11/06 的介面重整收尾。所以現在的數字是：錨點之後 109 筆提交（不含合併的有 74 筆）、458 個檔、撞 31 個檔。
- 拿 `40c30129` 重跑 merge-tree，撞檔正好是 29 個，和派工單對得上。多出來的 2 個都來自 `51787b33`：`docs/guide/地圖與介面.md` 和 `tests/web/test_gather_branches_web.py`。
- 主幹是 `0176753d`，錨點 `17c5199d`。這次 merge-tree 的結果樹是 `882cd7d6`，下面寫的「合併樹第幾行」都指這一份（行號含衝突標記）。

**一、統計表**

| 類 | 檔數 | 其中撞檔 | 程式／測試／文件與其他 |
|---|---|---|---|
| (A) 主幹沒動 | 123 | 0 | 程式 36、測試 32、內容 44、網頁 9、文件 2 |
| (B) 兩邊都改，位置沒變 | 48 | 21（文件 7、測試 2、程式 12） | 程式 29、測試 8、文件 10、內容 1 |
| (C) 主幹搬走或拆了 | 19 | 10（8 個別名模組，2 個 modify/delete） | 9 個搬家的測試，git 自動跟過去了 |
| (D) develop 新加 | 268 | 0 | 非圖檔 44，圖與資料 224 |
| 合計 | 458 | 31 | |

- 另外還有「檔案算 B、裡面有幾段要照新位置搬」的情形：`engine.py` 9 個方法加常數、`server.py` 1 段路由、`rules.py` 1 段（搬進 `_fx_stats`）。下面放在 (C) 一起列。

**二、31 個撞檔逐一歸類**

文件 7 個，都是 (B)：
- `.claude/skills/tianxia-flow/SKILL.md`
- `CLAUDE.md`
- `docs/guide/地圖與介面.md`
- `docs/guide/大勢人物與賽季.md`
- `docs/guide/核心與存檔.md`
- `docs/superpowers/feedback/試玩回饋.md`
- `docs/superpowers/handoff/2026-10-30-主機側交接.md`

測試 4 個：
- `tests/core/test_feature_boundaries.py`：(B)
- `tests/core/test_test_for.py`：(B)
- `tests/acts/test_explore_modes.py`：(C)，主幹刪、develop 改
- `tests/web/test_gather_branches_web.py`：(C)，主幹刪、develop 改

程式 20 個：
- (B)，一共 10 個：`tianxia/bot.py`、`bot_policy.py`、`content.py`、`core/__init__.py`、`core/registry.py`、`core/services.py`、`features/guide/actions.py`、`plans.py`、`rules.py`、`rumor_view.py`
- (B) 加 (C) 混著，2 個：`tianxia/engine.py`（12 塊）、`server.py`（2 塊）
- (C) 別名模組，8 個：`zhuan_html.py`、`tianxia/companion_agent.py`、`cultivation.py`、`epiphany.py`、`foreshadow.py`、`sensing.py`、`smithing.py`、`storyline.py`

撞檔裡沒有 (A)，也沒有 (D)。

**三、(A) 主幹沒動，123 檔**
- 目錄分布：
  - 內容：`content/events` 32 個；`content/` 其他 12 個（hints、itineraries、looks、mall、opportunities、orders、patch_notes、profiles/season21、profiles/week7、skills、timetable、traits）
  - tianxia 頂層舊模組 17 個：battle_instance、battlelog、deeds、encounter、insight_fx、journal、library、renown、rise、roster、seal_duel、skillview、tale、team、territory、timetable、world_state
  - tianxia/features 19 個：looks 12、battle 3（muster、rules、tests/test_battle_tales）、guide 2（checks、tests/test_guide_smoke）、mall/tests 2
  - tests 32 個：web 12、battle 6、core 5、arts 3、figures、fixtures、kit、ranger、seal、season 各 1
  - web 9 個：admin.js、app.js、index.html、main.js、mall.css、mall.js、outing.js、style.css、zhuan.css
  - docs 2 個
- 合了就進來，git 不用處理。但有幾件語意上的事要留意：
  - `content/profiles/week7.json`、`season21.json` 把 `attributes.v2` 和 `legacy` 打開了（`6cb80d62`）。主幹新加或搬家的 124 個測試檔裡，有 55 個用 week7 或 season21。它們從沒在五項屬性的規則下跑過。develop 自己打開時修了 24 條紅（`e9907a84`），推測主幹這邊也會出一批。
  - 第 27、50 批還沒合進主幹。合了之後，有 4 個 A 會變 B 或 C：
    - `tests/seal/test_seal_revamp_hidden.py` 會被 `dev/seal-1` 搬到 `features/seal/tests`（R100）
    - `tests/battle/test_terrain_arts.py`、`tests/figures/test_rumor_layers.py`、`tianxia/features/battle/muster.py` 會被 `dev/map-2` 改到
  - 第 27 批會把 `tianxia/seal.py` 變成別名（`origin/dev/seal-1`）。
  - `seal_duel.py`（第 28 批）和 `tale.py` 加 server 戰記那一段（第 52 批）現在算 A。輪到那幾批時，develop 的改動要一起帶過去。

**四、(B) 主幹改過、位置沒變，48 檔**

文件：
- `SKILL.md`：撞，合併樹 150 行。「週末、14 天季、三選一」這一行兩邊都改：主幹寫第 13、14 批（`a5b8acf6`），develop 仍是舊文；develop 另加雲端 PR 規矩（`f7dfe8cb`、`b0538bde`）。
- `CLAUDE.md`：撞，59 行。兩邊都改「賽季由管理者開」和「第一季濃縮版」這兩行：主幹把 weekend 換成 season21、week7，develop 加傳承換季一句。其餘自動合：主幹改分支段和模組表（拿掉 explore_modes、gather_llm）；develop 改 PR 範本、Joy 直推例外、「不用避開搬包中的包」。
- `docs/guide/地圖與介面.md`：撞，22 行。主幹改「江湖頁」那一條；develop 在同一處加「介面重整」10 行（`51787b33`）。
- `docs/guide/大勢人物與賽季.md`：撞，160 行。主幹加「一條線（features/story）」一節，develop 在同一處加「傳承」一節。兩節都留。
- `docs/guide/核心與存檔.md`：撞，36 行。「新手引導重做」那一條兩邊都改；develop 另加「補新手教學十一條」。
- `docs/guide/量表與教訓.md`：自動合。主幹拿掉週末和三選一；develop 加 1 行平衡檢查清單（`d2ce9e05`）。
- `docs/superpowers/feedback/beta-主機端操作.md`：自動合。主幹是週末設定關門；develop 加 2 行，寫拿掉 TIANXIA_UI_CLASSIC。
- `試玩回饋.md`：撞，529 行。表尾各加一列（主幹 FB-9310、develop FB-9430），兩列都留。
- `主機側交接.md`：撞，7 行。主幹整份改寫（+125／−495）；develop 只在頂上加「停在錨點」的註記。取主幹。
- `2026-10-30-開發模式-design.md`：自動合。主幹 +365（PM 認定那幾節）；develop +19／−5（雲端 PR 規矩、開季準備卡 `ef6d4faa`）。

內容與頂層、腳本：
- `content/tutorial.json`：自動合。主幹把兩步的 action 從 drill／field_win 改成 explore（`8eb13295`）；develop 加 text_v2、line_v2，改兩段師父的話。
- `run_studio.py`：自動合。主幹 env_profile 換 serving_profile；develop 加 fresh_retries。
- `scripts/measure_gear.py`：自動合。主幹改註解；develop 讓 toll 多收 `**kw`（squad）。
- `scripts/same_behavior.py`：自動合。主幹 +14116，PROFILES 只剩 season21、week7、test；develop 加 1 行，挑同伴時跳過 hire_type。

測試：
- `tests/conftest.py`：自動合。主幹加 `old_explore`，develop 加 `old_attrs`。
- `tests/core/test_contract_features.py`：自動合。主幹改 CORE_IDS、MENU_BY_CORE；develop 加 1 處關 legacy。
- `tests/core/test_feature_boundaries.py`：撞，469 行。主幹拿掉 `(allocate_stat, _note_action)`（第 23 批搬走了）；develop 在同一處加 `(_allocate_v2, _note_action)`、`(pick_growth, _note_action)`。要等 growth 的歸屬定了才知道怎麼合。
- `tests/core/test_test_for.py`：撞，1021 行。STAGE_PACKAGES 兩邊各加一批（主幹加 checkin、companions、sense……；develop 加 legacy、hire），取聯集。develop 改 mall.js 那條斷言是自動合的。
- `tests/gear/test_shop.py`：自動合。主幹 weekend 換成 None；develop 在兩條測試補 `/api/do/growth`。
- `tests/seal/test_seal_acts.py`：自動合。主幹改 callers 路徑；develop 加一行 `attr_alloc`。
- `tests/server/test_server.py`：自動合。主幹改用 `old_explore`；develop 加戰記分享頁的測試。
- `tests/web/test_jianghu_page_web.py`：自動合。主幹 −58（拿掉三選一那幾條、with_reveal）；develop +110／−60（託付信、介面重整）。合併樹裡查過，沒有留下引用已刪名字的地方。

tianxia 頂層：
- `bot.py`：撞，15 行，是 import 那一行。主幹拿掉 explore_modes 等，develop 加 attrset。growth_key、allocate_points 的 v2 分支、pick 的 GROWTH_PREFIX 自動合。`from .engine import GROWTH_PREFIX` 要看常數最後放哪。
- `bot_policy.py`：撞，701 行。主幹把 `kind == "opp"` 那一支搬去 `features/military/bots.py`；develop 在它前面加 growth 那一支。留 growth、丟 opp。
- `conquest.py`：自動合。主幹加 void、_rumor（第 46 批）；develop 加 `place_state.flipped`。
- `content.py`：撞 2 塊。
  - 27 行的 import：主幹拿掉 GatherBranch；develop 加 PLACE_KINDS、Check、StatDef。
  - 2685 行：主幹拿掉 `check_xingshi_lines`（搬進 `features/territory_acts/__init__.py` 的 check_content）；develop 在同一處加 `check_attributes`。
  - 其餘自動合：_load_attributes、resolve_grades、hirelings 併進人物表。
- `core/__init__.py`：撞，39 行。主幹改寫了 MODULES 和註解；develop 在 MODULES 加 `"attrset"`。
- `core/features.py`：自動合。主幹加 world、effects、defection、bus、steps 掛鉤；develop 加 `prep` 掛鉤。
- `core/registry.py`：撞 3 塊。
  - 49 行：import。
  - 115 行：FEATURES 清單。主幹在 bout 後面接了 stamina_plays、seclusion、peers、travel 等；develop 接 legacy、hire。
  - 192 行：SHARED。develop 加 place_state；同一處的 seats、factions 說明主幹改過。
- `core/services.py`：撞，456 行，是服務清單那一行。主幹寫 allocate_stat 歸修練包；develop 加 `ctx.pick_growth`。
- `events.py`：自動合。主幹 foreshadow 換 omen_base；develop 加 qiyu_multiplier、check_stat_name。
- `figure_life.py`：自動合。主幹收進共用規則層；develop 在函式裡 import place_state，warmed 多帶 state。
- `models.py`：自動合。主幹拿掉 ExploreModes 和 drill_* 欄位；develop +363（AttrV2Rules、StatDef、LegacyRules、HireRules 等）。
- `mounts.py`：自動合。develop 讓馬市開不開讀 place_state。
- `plans.py`：撞，17 行，只撞在模組說明；develop 的 import 和 `_settle` 自動合。
- `rules.py`：撞，1169 行。主幹把 apply_effect 拆成一格一段，屬性那一段在 `rules.py:1101 _fx_stats`；develop 改的是原本的屬性迴圈（歷練 grant_event），要寫進 `_fx_stats`。`_fx_affinity` 那一處 warmed(state) 自動落在 `:1162`。
- `rumor_view.py`：撞，10 行 import。主幹 foreshadow、opportunities 換 core.omen_base；develop 加 deeds。gazette_* 自動合。
- `state.py`：自動合。develop 加 ShihaiSeal、LegacyBook 和新的存檔欄位（稽核第 6 節說要原名帶過去）。

features：
- `battle/view.py`：自動合。主幹 annals 換 annal_base、cultivation.seize 換 `ctx._seize_chance`；develop 加 fallen。
- `bout/arena_actions.py`：自動合。develop 加 attrset、pvp_card、faced。
- `bout/arena_rules.py`：自動合。主幹加 world_close；develop 加閃避。
- `bout/duel_actions.py`：自動合。主幹拿掉 boss_here 等；develop 改 rise.duel 傳 world、加魅力。
- `guide/actions.py`：撞，9 行 import。主幹拿掉 create、sensing；develop 加 checkin、chuangong、seal、equipment、mounts、place_state、treasures、name_key、attrset、roster。hire_here、graduate_pass 的 v2 那段、`_more_triggers` 自動合。
- `guide/hints.py`：自動合。主幹加 defect_clear；develop 加提示 id 和 attrs_v2 的說法。
- `guide/rules.py`：自動合。主幹 `explore_modes.is_town` 換 `precise.is_town`；develop 加 step_words。
- `sortie/duel_actions.py`：自動合。develop 把 agi 改成 v1_stat。

**五、(C) 主幹搬走或拆了，要照新位置搬**

八個變成別名的模組（主幹上那個檔只剩 `sys.modules` 別名，develop 的改動都撞）：
- `zhuan_html.py` 搬到 `tianxia/features/zhuan/zhuan_html.py`。develop 的 `e9f351a7` 加了 import re、zh-skip 那一行、新函式 `text()`、page() 的 body 和 ping、zh-play class。新位置的 page() 從 `:89` 起，body 那行在 `:104`。
- `tianxia/companion_agent.py`：`renown.warmed(..., state)` 搬到 `features/companions/companion_agent.py:434`。
- `tianxia/cultivation.py`：兩行 wis 改 `team.v1_stat`，搬到 `features/cultivation/cultivation.py:125`、`:138`。
- `tianxia/epiphany.py` 搬到 `features/sense/epiphany.py`：
  - import 在 `:35`
  - chance() 的 wis 在 `:157`
  - roll() 的 `p.epiphany_dry += 1`（`:176`）前面加 `_luck_reroll`，再加 `_luck_reroll` 這個新函式
- `tianxia/foreshadow.py`：warmed(state) 搬到 `features/military/fs_rules.py:522`。
- `tianxia/sensing.py` 搬到 `features/sense/sensing.py`：import 在 `:22`，rate() 的 wis 在 `:141`。
- `tianxia/smithing.py`：wis 搬到 `features/smithy/smithing.py:140`。
- `tianxia/storyline.py`：roll_start 在主幹是 `tianxia/story_base.py:160`（共用規則層）。`_luck_again` 加在那裡；`from .renown` 在 story_base 照樣能用。

主幹刪了、develop 改了的 2 個測試：
- `tests/acts/test_explore_modes.py`：develop 改的那條測試，主幹搬成 `tianxia/features/sense/tests/test_sensing.py:40 test_a_treasure_raises_the_sensing_odds`（`17a92b78`）。要補 develop 那兩行 `attr_alloc["int"]`，因為 week7 開了 v2。
- `tests/web/test_gather_branches_web.py`：主幹整檔刪了（三選一拿掉）。develop 的 `51787b33` 改的是 practice 那條斷言，而主幹 tianxia 裡 `explore:practice` 只剩 prologue 一處，推測整條丟掉。

搬家的 9 個測試，git 自動跟過去了，合併樹裡查過 develop 的改動都在新路徑：
- `tests/arts/test_epiphany.py` 到 `features/sense/tests/`
- `tests/bots/test_silver_gates.py` 到 `features/outlets/tests/`
- `tests/core/test_biography.py` 到 `features/zhuan/tests/`
- `test_explore_variety.py` 到 `features/explore/tests/`
- `test_socialize_variety.py` 到 `features/socialize/tests/`
- `test_story_wangyue.py`、`test_story_wolong.py` 到 `features/story/tests/`
- `tests/figures/test_checkin.py` 到 `features/checkin/tests/`
- `tests/season/test_real_map.py` 到 `features/map/tests/`

`engine.py` 的 12 個衝突塊（行號是合併樹的）：
- 17、25 行：import。取主幹的清單，只補 attrset、place_state。develop 那一邊還留著 ascend、gather_llm 等主幹已經拿掉的名字。
- 306 行：develop 在 PREPARING_TEXT 旁邊加 GROWTH_* 三個常數。主幹已把 PREPARING_TEXT 搬進 `core/services.py`，這三個常數放哪要 PM 定。
- 1371 行：`_recruit_targets` 的 `roster.on(..., world)`，搬到 `features/companions/actions.py:40 recruit_targets`（`:43`）。
- 1940 行：develop 在 figure_view 後面新加 `figures_here_view`、`_figure_side_name`、`talk_view`；主幹那裡已經是委派 `companions_actions.figure_view`。
- 2512 行：`_explore_weights` 的 wis，搬到 `features/explore/explore_base.py:90`（`:96`）。
- 4253 行：`challenge_odds` 的 draw_floor 傳 world，搬到 `features/figure_acts/challenge.py:73 odds`（`:77`）；`_figure_squad` 加 `attrset.figure_squad` 分支，搬到 `challenge.py:80`（`:85`）。
- 4301 行：`_challenge` 的 draw_floor 和 `_take_toll(squad=)`，搬到 `challenge.py:93`（`:107`、`:138`）。
- 4772 行：`_finish_seclusion` 的 wis，搬到 `features/seclusion/actions.py:41 finish`（`:46`）。
- 5179 行：allocate_stat 開頭多一支 v2 分支，搬到 `features/cultivation/actions.py:285`；develop 在同一塊新加 `_allocate_v2`、`_season_prep`、`season_prep_view`、`pick_growth`。
- 5421 行：`_raid_spoils` 的 agi，搬到 `features/peers/raid_actions.py:168 take_spoils`（`:180`）。
- 5482 行：`_ambush_spoils` 的 agi，搬到 `features/stamina_plays/ambush_actions.py:138 spoils`（`:166`）。

develop 新加的 9 個 Game 方法：
- 撞的有 7 個（在 1940 和 5179 那兩塊裡）。
- 沒撞、自動合進 engine 的有 2 個：`place_state_view`（落在主幹 plan_view 委派 `:2202` 後面；稽核第 6 節說歸 figure_acts）、`_attr_rows`（落在 feature_status `:6441` 後面）。

`engine.py` 裡其餘 develop 的改動都自動合在原位，主幹也還留著那些方法：new、_reset_player_for_new_season、_deliver_away、_everyday_options、choose、_battle_role、_battle_marks、_seal_challenge、_seal_spectators、_seal_side_of、_squad_encounter、_take_toll、_play_rounds、_story_squad、_spar_power、seal_gamble、admin_seal_duel、location_text、scene_art、status_data。

`server.py` 的 2 個衝突塊：
- 66 行：主幹拿掉 `import zhuan_html`，develop 加 `import tale_html`。
- 3067 行：develop 在 api_figure 旁邊新加 `/api/talk_log`。主幹已把這一區（api_figure、peer、party）搬進各包的 routes.py，api_figure 在 `features/companions/routes.py:13`。推測 talk_log 也進 companions/routes.py。
- 其餘自動合在殼裡：figure_face、talk_store／_log_talk、`/zhanji`、tale_cover、main_view 的 prep、figures_here、talk、place_state、`_online_count`、MAIN_ACTIONS 的 growth。

**六、(D) develop 新加的 268 檔**

新模組 4 個：
- `tianxia/attrset.py`（250 行）：五項屬性，只 import models 和 state；develop 把它列進核心（`4be00ea3`）。
- `tianxia/place_state.py`（186 行）：地點會變樣，import calendar、deeds、world_state；develop 列進 SHARED（`b96fd295`）。
- `tianxia/talk_log.py`（119 行）：往來紀錄，存在旁邊的 `<db>-talk.sqlite`（`4de6fb28`）。
- `tale_html.py`（156 行）：戰記分享頁（`e9f351a7`）。推測要照 zhuan_html 的做法進包，或交給第 52 批。

新功能包：
- `features/hire/` 5 個檔：README、`__init__`、actions、tests/hire_stage、tests/test_hire_smoke。招募同伴（`8a16893d`）。
- `features/legacy/` 10 個檔：README、`__init__`、actions、bots、rules、tests 底下 5 個。傳承（`2f4ae10d`、`9167c73f`、`303d3196`、`169fa2b5`、`38b928e3`）。

內容 4 個：
- `content/attributes.json`：屬性定義與效果表，第 ① 骨架（`b7573f6d`）
- `content/attributes_v2.json`：五項屬性
- `content/events/places.json`：地點會變樣的事件
- `content/hirelings.json`：招募的人。稽核 3.8 說要改名成 hire.json，由招募包自己驗。

腳本 8 個：balance_matrix、convert_grades、make_hirelings、make_pose_refs、measure_attrs_v2、measure_legacy、measure_pvp_attrs、studio_bench。

包外的測試 8 個：
- `tests/core/test_attributes.py`、`test_attrset.py`
- `tests/figures/test_place_state.py`
- `tests/kit/grade_kit.py`
- `tests/server/test_tale_page.py`、`test_talk_log.py`
- `tests/web/test_revamp_web.py`、`test_season_prep_web.py`

文件 3 個：`.github/pull_request_template.md`、`2026-11-05-上線退版風險-給joy.md`、`2026-11-04-屬性與跨季-架構方向v2.md`。

網頁樣式 2 個：`web/legacy.css`、`web/tale.css`。

圖與資料 224 個：
- web/img 底下的 webp：looks 160、figures/full 18、here 9、tale 7、zhuan 7、legacy 5、acts 4
- looks 的 hands.json 10 個
- `features/looks/pose/*.png` 4 個

**七、搬的時候會踩的坑（都查得到）**
- **會直接壞：**`figures_here_view` 呼叫 `self._talkable`、`self._why_not_talk`，但主幹已經沒有這兩個 Game 方法，搬成了 `features/socialize/view.py:25 talkable`、`:30 why_not_talk`。照貼的話執行時會丟 AttributeError。我掃過 develop 新加的所有 `self.`／`ctx.` 呼叫，只有這兩個。
- **相對 import 進包會壞：**develop 在 sensing、epiphany 寫的是 `from . import attrset`，在 epiphany 寫的是 `from .renown import legacy_door`。進了包，相對 import 會指錯地方，要改成 `from tianxia import ...`。
- **會讓邊界測試紅：**
  - develop 在 `guide/actions.py` 新加的 checkin、chuangong，在主幹已經是別名；seal 到第 27 批也會變別名。它們標了「過渡：待搬」，會違反 `test_feature_boundaries.py:1513`（過渡 import 只能指向舊模組）。
  - 主幹的做法是改走 ctx 的查詢服務，例子是主幹 `guide/actions.py:282` 的 `ctx._create_on()`。
- **兩個前提要先合：**attrset 要在核心 MODULES、place_state 要在 SHARED，這兩件事都卡在衝突塊裡（`core/__init__.py`、`registry.py`）。hire、bout、guide 包裡的 import，和 figure_life、mounts、conquest、plans、territory、timetable 這幾個共用層模組的 import，都靠它們。
- **選單順序：**develop 把 legacy、hire 接在 bout 後面；主幹 bout 後面已經多了好幾包。手冊認定選單順序算行為，要定排在哪裡。

**八、稽核沒涵蓋的部分，以及推測**
- 稽核第 6 節算到 #163，估了 (a)～(d) 四批。之後又進了 #165、#166／#169、#167、#171～#175。範圍是：
  - 歷練：`rules._fx_stats` 那一塊衝突
  - 介面重整：figures_here_view、talk_view、talk_log、`/api/talk_log`、test_revamp_web
  - 絕招例句
  - 魅力說明文字

  推測 (d) 要擴大，或另開第五批。
- 推測：`core/services.py` 那一行服務清單，就是 `test_feature_packages_only_touch_the_service_list_on_the_game` 讀的名單。我沒有讀那條測試的實作。
- 推測：合併之後 `same_behavior` 的基準要重抓。develop 的 week7、season21 行為本來就變了，主幹原本的「一個字不變」證明不適用於合併後的版本。
- 沒有查的：web 的 JS 裡哪些段落歸哪一包（稽核 3.10）；`content/events` 那 32 個檔逐檔的內容。

暫存的對照檔在 `C:\Users\ray61\AppData\Local\Temp\claude\4d5f79bfb143ac0b\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\m6\`：`dev.txt`、`trunk.txt`、`mt.txt`、`c_mt.txt`。我沒有改任何檔，也沒有 commit。
