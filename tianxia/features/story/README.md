# 一條線（`tianxia/features/story/`）

特殊事件與特殊頓悟的底座：一條線是一串段（事件、答題、打一場、等一件事做成），每一段走完照這條線自己記下的記號往下一段或某一個結局，段可以有期限，結局一定寫進傳（失敗的也寫；季末還沒收的寫「此事未了」）。長篇奇事（照記號換段落、多日段、餘波、紀念物與跨季旗標）也在這裡。全部拆包第 30 批搬進來（計畫 `docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md`，和簽到小包併批）。

- 導覽：`docs/guide/大勢人物與賽季.md` 的「一條線（功能包 `tianxia/features/story/`）」那一節；規則另見 `docs/guide/行動與地盤.md` 的特殊事件那一節。
- 設計稿：沒有版本號——特殊事件設計稿「一條線」（企劃者 2026-10-26）、長篇奇事（2026-10-27，`StoryStage.wait_days`、餘波、紀念物）。

## 裡面有什麼

- `tianxia/story_base.py`（**共用規則層**，不在包裡）：`storyline.py` 前半原樣搬出來的底座——常數（`WORLD`、`HISTORY`、`OPTION`、`JOURNAL`）、登記鉤子的字典（`TASKS`、`TASK_LEFT`、`REFRESH_HOOKS`、`FIGHT_HOOKS`、`END_HOOKS`）、`on`、`definition`、`active`、`room`、`here`、換字（`vary`）、開頭（`roll_start`、`start`、`_enter`）、`current`、`stage_art`、`question_text`、`open_quiz`、`heard`。放在共用層是因為別人也讀：核心的 `rules.fill_marks`（換字）、事件檢定（`heard`）、`Game` 的幾個讀取，與兩個已成包的包——探索包（`roll_start`）、有所感包（頓悟那一條線登記鉤子、開線、開第一題）；這些是模組層登記，不能改走 `ctx`。比總表寫的「換字那一小段」大，原因在計畫 Review Focus 1。
- `storyline.py`（原 `tianxia/storyline.py` 的後半：`task_note`、`retry_note`、`waiting`、`doable`、`ready_event`、`label`、`options`、`pending_lines`、`quiz_menu`、`answer`、`wait_text`、`fought`、`route`、`tick`、`finish`、`aftermath`、`close`、`close_season`、`seen`……，與 `PENDING_HEAD`、`LATER_LABEL` 這些玩家看得到的字）：開頭 re-export `story_base` 的每一個名字，所以 `from tianxia import storyline`（舊名 `tianxia/storyline.py` 留成 `sys.modules` 別名，同一個模組物件）照舊拿得到全部，往 `storyline.TASKS[...]`、`FIGHT_HOOKS[...]` 裡登記的就是 `story_base` 同一個字典。
- `actions.py`：原本 `Game` 上的 10 個方法（名字去掉前導底線、第一個參數 `ctx`；`story_act`、`story_fight`、`story_bout` 只有包裡叫，`Game` 不留），加上核心原位叫的 4 個本體（`story_menu`、`story_options`、`close_season`、`story_title`）。模組層 import `chapters`（章回主線；載入時往 `storyline.TASKS` 登記「章回的一拍」，原本是 `engine` 在模組層 import，載入時機不能晚）。
- 掛鉤：`enabled` 一直是 True（線自己看 `Config.jianfa.storylines`；灰掉的包不接 choose，落到 else 當成事件選項炸掉）；`prefix = "story"`；`choose` 吃 `story:`（按「未了之事」那一顆、答題的答案 `story:<線>:a<序號>`、先擱著 `story:<線>:later`；標題＝線的名字，動作之前先拿）；`content`（四個長篇奇事的段落事件檔）；`player_fields`；核心的效果格 `effects()`（`story` 那一格：`storyline.effect_step`，一條線的一步——記號、往哪裡、紀念物收與交；全部拆包第 32 批，原本 `rules.apply_effect` 最後一段直接寫 `storylines`、`keepsakes`）。
- **沒有 `bots.py`、沒有路由、不碰 `web/`**：`bot_policy.score` 本來就沒有 `story:` 那一段（落到最後的 `None`），拿了前綴之後 `bot_pick` 預設回 `None`，一樣不按；`bot.py` 的「先擱著（`story:*:later`）不按」是排除整季機器人的一顆（`bot_always` 是整個前綴，接不了），留在原位。`/api/do/story_seen`、`/api/main` 的 `story_cards` 在殼的 `MAIN_ACTIONS`／`main_view`，照舊叫 `Game` 的委派。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`storylines`（這一季開過的線與進度，收了的也留著）、`story_open`（答題停在哪一條）、`story_cards`（等著跳出來的卡）、`keepsakes`（紀念物）、`lasting`（跨季旗標）。
- `carried`：`keepsakes`、`lasting`（`Game._reset_player_for_new_season` 帶到下一季，並把 `lasting` 併進旗標）；其餘換季跟著新角色重來。
- 內容：`content/events/story_fuzhi.json`、`story_maier.json`、`story_wangyue.json`、`story_wolong.json`（`content` 宣告）。`content/storylines.json` 混著章回主線的線（`ch_*`），不宣告（章回批再看）。

## 委派與留在原位的接縫

`Game` 留 10 個一行委派（公開 4：`story_start`〔程式組的線的入口，頓悟用〕、`story_cards`〔測試在叫〕、`story_seen`、`story_card_view`〔server〕；私有 6：`_story_begin`〔探索包經 `ctx`〕、`_story_tick`〔`sync`、`choose`、`_event_progress` 與測試〕、`_mirror_squad`〔有所感測試〕、`_story_menu`、`_story_options`、`_story_close_season`）。核心原位碰一條線的幾處（計畫 1.5）接不了第 11 批掛鉤，改叫這些委派、記進邊界測試 `GAME_DELEGATE_CALLERS` 的 `# story` 那一段（6 對，各寫理由），**沒有新增 `GAME_DIRECT`**：

- 答題的選單（`_everyday_options`）在有所感的 `_sense_menu` 之後，`menu` 掛鉤在它之前；「未了之事」那一顆在應召之後、此地的人之前，`options` 掛鉤在最後面——`/api/main` 的選項順序算行為。
- 換季收線（`_reset_player_for_new_season`）要在 `world.save_annals` 存上一季的行狀之前，`on_season_end` 在它之後。
- `sync`、`choose`、`_event_progress` 叫 `_story_tick`：每個動作結束那一格、同步在召見之後席次之前，不是掛鉤的位置。
- 標題與動作原本在 `_action_title` 與 `choose` 的 elif 鏈，換成 `choose` 掛鉤的 `Outcome(title, run)`。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組：沒有了（全部拆包第 40 批合完重印 0 處）：`actions.py` 那一行 `chapters` 第 40 批收進共用規則層，不算過渡，行尾註改寫成「共用規則層」；`storyline.py` 的 `annals` 第 29 批之二改 import 核心。共用層 `story_base` → `atlas`（`here` 的大區，第 50 批）記在邊界測試的 `SHARED_PENDING`；`story_base` → `chapters`（`vary` 的大事結果，函式裡）第 40 批起是共用層之間，不再記。
- 章回的開回、收回（原本 `chapters.tick`，叫這一包的 `finish`）第 40 批整段搬進這一包：`storyline.chapter_tick`（`story_tick` 叫它，先後不變）；`chapters` 讀一條線的 `active`、`current`、`here`、`doable` 改讀底座 `story_base`（`waiting`、`doable` 與新的 `mark_of` 第 40 批搬進底座，`storyline.py` 照原名 re-export 同一個物件；`rules.check_condition` 的 `story_marks`、`story_marks_max` 經 `story_base.mark_of` 讀）；`chapters` 載入時往底座的 `story_base.TASKS` 登記章回的一拍，不 import 這一包。
- 舊模組 → 包：`engine` 1 行（`story_actions`）、別名檔 `tianxia/storyline.py`；`bot`、腳本、測試（`weekcard` 第 36 批起收進核心，`OPTION` 改讀共用規則層的 `story_base`）。
- 服務清單（`tianxia/core/services.py`）這一包加的：二、查詢 `# story` 一段（`ctx._story_begin`：探索包叫它，原本列在三、過渡 explore 那一行）；包裡叫回 `Game` 的其餘都已在清單（`_present`、`_story_squad`、`_judged`、`_fight_with`、`_style_note`、`_terrain_note`、`_narrate`、`_play_rounds`、`_hp_facts`、`_battle_rewards`、`_file_battle`、`_outcome`、`_save_season`）。

## 測試

`tests/` 底下 6 個檔：`test_storyline.py`（引擎，12 條）、`test_story_fuzhi.py`、`test_story_maier.py`、`test_story_wangyue.py`、`test_story_wolong.py`（四條長篇奇事用正式內容走完，各自整檔 slow），加上煙霧 `test_story_smoke.py` 與契約測試擺局面用的 `story_stage.py`。含 slow 25 條，不含 slow 只有煙霧 1 條。

另外要跑的（混在別人檔裡的，改這一包時連它們一起跑）：

- `tests/core/test_chapters.py`（章回主線：用 `storyline.vary`、`TASKS`、`start`，章回批才搬）、`tests/web/test_week_card_web.py`（本週卡：`game._story_tick()`、`OPTION`）。
- 有所感包的 `tianxia/features/sense/tests/test_epiphany.py`、`test_epiphany_name_web.py`（頓悟那一條線登記的鉤子，依賴 `story_base` 與 `storyline` 別名）。
- 探索包的 `tianxia/features/explore/tests/test_explore_one.py`、`test_explore_one_polish.py`（擲開頭 `roll_start`）。

```
python scripts/test_for.py --base HEAD tianxia/features/story/actions.py tests/core/test_chapters.py tests/web/test_week_card_web.py
```

**行狀記一筆改 import 核心**（全部拆包第 29 批之二）：本包原本「包 → `tianxia.annals`」的過渡 import 改成 `from tianxia.core import annal_base as annals`（核心本體，不算過渡，行尾註拿掉「過渡：待搬」）；上面各處寫到 `annals` 的過渡句（含處數）是這一批之前的舊寫法，現在那幾處不算過渡，數字一律以 `python tests/core/test_feature_boundaries.py` 重印為準（舊名 `tianxia/annals.py` 是指到列傳包 `standing.py` 的別名，那一份 re-export 核心那一半）。
