# 有所感與頓悟（`tianxia/features/sense/`）

探索撞上有所感（卡上三四個做法、選對擲中進感悟狀態、一筆畫下心中的形或順其自然）、自己畫字悟出的私有意境（看圖取名的三段式、首悟紀錄）、特殊頓悟（擲中感悟時再擲：心靈拷問 → 心境小試 → 心魔 → 取名，收進一份神品意境）。全部拆包第 24 批搬進來（計畫 `docs/superpowers/plans/2026-11-01-有所感包-第1批.md`）。網頁那一半（`web/app.js` 的 `SENSE_DRAW`、`SENSE_SIZE`、畫布、`godName`……）第 3 階再切。

- 導覽：`docs/guide/武學與成長.md` 的「有所感與頓悟（功能包 `tianxia/features/sense/`）」那一節；規則細節照舊在那一份的 `tianxia/epiphany.py` 那一條與〈行動與地盤〉的靜心感悟。
- 設計稿：沒有版本號——悟意境設計（企劃者 2026-10-06「甲案加乙案」：第零節有所感、0.2 看圖取名、0.2a 退路與暖機、0.2b 私有意境與首悟）；意境提示設計（第一、二節：每個地點最濃的意境）；特殊頓悟設計稿（企劃者 2026-10-26，https://claude.ai/artifact/EBUqqzK3dPMpjwYTdRzLs3）。

## 裡面有什麼

- `sensing.py`（原 `tianxia/sensing.py`：有所感的規則）、`epiphany.py`（原 `tianxia/epiphany.py`：特殊頓悟；import 的時候登記一條線的鉤子 `storyline.TASKS`／`TASK_LEFT`／`REFRESH_HOOKS`／`FIGHT_HOOKS`／`END_HOOKS`）、`glyph.py`（原 `tianxia/glyph.py`：讀筆畫）、`insight_llm.py`（原 `tianxia/insight_llm.py`：看圖取名的 B 段）——四個舊名都留成 `sys.modules` 別名（同一個模組物件，`mock.patch.object(epiphany, "_trial")`、`server.insight_llm.warm` 這一類照樣換得到）。
- `actions.py`：原本 `Game` 上的 10 個方法（名字去掉前導底線、第一個參數 `ctx`；`sense_draw`、`epiphany_names` 掛核心的 `outing_watch`），`scene` 掛鉤的本體，核心原位、探索包、引導包叫的 7 個服務的本體（`sense_missed`、`sense_drop_stale`、`sense_menu`、`sense_start`、`sense_canvas`、`epiphany_title`、`prologue_choice`）。
- `routes.py`：`/api/sense`、`/api/sense_read`、`/api/sense_warm`（原本寫在 `server.py`；殼照 `FEATURES` 掛，函式名照舊）。畫完那一筆的鎖外三段式照舊是殼的 `server.sense_draw`、靜心思名照舊是 `server.epiphany_think`（鎖外工作的掛鉤是總表第 69 批）。
- 掛鉤：`enabled` 一直是 True（有沒有場景看內容、特殊頓悟看 `Config.epiphany`）；`prefix = ("sense", "dunwu")`；`choose` 只吃 `sense:`（標題「有所感・場景」）；`scene`（接縫掛鉤：有所感的卡、取名那一張，排在宴客之後）；`routes`；`content`（`insight_scenes.json`）；`player_fields`。**沒有 `bots.py`**：`bot_policy.score` 本來就沒有 `sense:`、`dunwu:` 那一段（落到最後的 None），拿了前綴之後 `bot_pick` 預設回 None，一樣不按（手冊第十五節第 2 批）；假人的有所感、取名照舊在 `bot_policy.take_turn` 的 `_sense`、`_god_name` 與 `bot.py` 的 `sense_pick`／`sense_stroke`，叫 Game 的委派。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`sensing`、`sense_serial`、`sense_misses`（有所感那一份、流水號、選錯的帳）、`epiphanies`、`epiphany_dry`、`god_naming`（特殊頓悟這一季的次數與保底、等著取名的那一個；後三個在 `state.QUIET_DEFAULTS`）。換季全部跟著新角色重來，`carried` 空的。
- 不列的：私有意境 `own_insights`／`own_serial`（共用規則層 `insights` 的，合成 `fusion` 也寫）；季上的 `WorldState.god_names`、`god_firsts`（核心的季）；`WorldStateStore.claim_insight_first`（核心）。
- 內容：`content/insight_scenes.json`（`content` 宣告；`content.py` 照舊讀、`content.check_insight_scenes` 照舊驗——核心沒有 import 這一包，不動）；神品意境的四十個模板在 `content/traits.json` 的 `god`（共用的功效表，`content.validate` 驗）。

## 委派與留在原位的接縫

`Game` 留 8 個一行委派（公開 5：`epiphany_request`、`epiphany_names`、`sense_request`、`sense_draw`、`method_help`——server 與假人在叫；私有 3：`_epiphany_begin`〔測試直接叫〕、`_epiphany_name`〔`choose` 原位〕、`_sense_here`〔探索包、`_explore_mode`、`_explore_outcome`〕），加上核心原位與探索、引導兩包叫的服務 7 個，與探索包回答這一包的查詢服務 `_rare_boost`（走一趟的稀有倍數：擲特殊頓悟乘它）。`_sense`、`_sense_apply` 只有包裡叫，不留。

核心原位碰有所感的那幾處（計畫 1.4）：能接第 11 批掛鉤的接上——`choose` 掛鉤接 `sense:`、`scene` 掛鉤接場景卡（就在原本那一行）；接不了的改叫上面的服務、記進邊界測試 `GAME_DELEGATE_CALLERS` 的 `# sense` 那一段（11 對，各寫理由），**沒有新增 `GAME_DIRECT`**（原本那一筆 `_sense` 讀探索包的 `rare_boost` 換成查詢服務、拿掉）：

- 清失效參照中段的 `_sense_drop_stale`（後面的收店讀 `player.sensing`，`on_drop_stale` 在最後）；選單的 `_sense_menu`（擂台之後；`menu` 掛鉤在擂台前面）。
- `choose`：`sense:draw` 只叫出畫布（`_sense_canvas`，建紀錄之前那一格，同 `battle:`）；`dunwu:` 要帶自己寫的名字（`text`），`choose` 掛鉤不帶，留在原位的 elif 叫 `_epiphany_name`，標題 `_action_title` 叫 `_epiphany_title`。
- 探索三選一與舊探索（總表第 13 批）：`_explore_mode_options`、`_insight_blocked`、`_explore_can` 的 `_sense_missed`；`_explore_outcome` 的 `_sense_start`（序章四景）、`_sense_here`（落在悟意境那一支：就是靜心感悟那四行）；`_explore_mode` 的 `_sense_here`。
- 裝飾器 `_outing_watch` 搬進核心（`tianxia/core/services.py` 的 `outing_watch`；`Game.choose`、`answer_event` 照舊掛），經 `ctx._outing_watched` 叫探索包的委派，記在 `CORE_DELEGATE_CALLERS`。籌備中那兩句 `PREPARING_TEXT`、`PREPARING_REFUSAL` 也搬進核心（`sense_request` 籌備中回它；第 23 批同時搬同樣兩句）。
- 包 import 包的地雷先拆：探索包 `explore_actions.outing_weights` 改問 `ctx._sense_missed(loc)`、引導包 `actions.graduate_pass` 改問 `ctx._sense_prologue_choice()`。
- 一行沒動的：`server.py` 的 `sense_draw`（鎖外三段式）、`epiphany_think`、`main_view` 的 `sense_help`、`api_choose` 自己寫名字被擋回給表單那一句；`bot.py`、`bot_policy.py`、`bot_runner.py`；`fusion`（`own_name`、`add_own`：舊模組 → 包，過渡；它還在共用規則層的 `SHARED_LATER`，同時還讀 `annals`）、`mapdata`（`terrain_tags`）；網頁。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組：`actions.py` 1 行（`storyline`）、`epiphany.py` 1 行（`annals`、`storyline`）、`sensing.py` 1 行（`seal_acts`：頒詔）。
- 舊模組 → 包：engine 3 行（`features.sense.actions`、別名 `sensing`、`epiphany`）、四個別名檔；還沒搬的 `fusion`、`mapdata`、`bot`、`bot_policy`、`bot_runner`、server（`insight_llm`、`epiphany`）、腳本。
- 服務清單（`tianxia/core/services.py`）這一包加的：一、共用 `outing_watch`、`PREPARING_TEXT`、`PREPARING_REFUSAL`；二、查詢 `_sense_here`（從三、過渡 explore 那一行搬來）、`_sense_missed`、`_sense_prologue_choice`（這一包回答別的包），`_rare_boost`（主人 explore）。包裡叫回 Game 的另有 `_outcome`、`_preparing`、`_log`、`_draft`、`_check_hints`、`_save_season`、`_quick_client`、`_guide`、`_note_action`（都已在清單）。

## 測試

- 這一包的（整檔屬於這一包、第 24 批搬進來的）：`tests/test_sensing.py`（36 條：讀筆畫、看圖取名、有所感的流程、私有意境在合成與修練裡、首悟、機器人；原 `tests/arts/`）、`test_epiphany.py`（26：擲中、保底、拷問、小試、心魔、取名、神品的限制；原 `tests/arts/`）、`test_insight_strong.py`（20：每個地點最濃的意境；原 `tests/arts/`）、`test_sense_smoke.py`（1，smoke：week7 散人在潁水河畔有所感、選對擲中、順其自然）、`sense_stage.py`（契約測試擺局面：平常）。`pytest tianxia/features/sense/tests -n 4 -m "slow or not slow"`：83 條約 7 秒。改這一包任一檔 `test_for` 挑到 208／209 條（包＋核心契約與邊界）。
- **`test_for` 挑不到的、另外要跑的**（這一輪不搬、不拆）：
  - 網頁（第 3 階跟網頁檔一起搬）：`tests/web/test_epiphany_name_web.py`（神品自己取名的輸入框；整檔 slow）、`test_explain2_web.py`（做法底下的小字）、`test_prologue_web.py`、`test_jianghu_page_web.py`。
  - 路由與殼的三段式：`tests/server/test_server.py`（`/api/sense` 三條、看圖取名的 B 段、靜心思名、`_tell_tabs`）。
  - 混在別人檔裡的：`tests/arts/test_explain2.py`（做法底下的小字、`SHOW_KINDS`）、`test_hints.py`（畫完悟到意境的提示）、`test_pr21_merge.py`、`test_secret_recipes.py`；`tests/core/test_prologue.py`（草廬的有所感）、`test_storyline.py`（頓悟那一條線的鉤子）、`test_engine.py`、`test_explain.py`、`test_biography.py`、`test_choose_refusal.py`、`test_old_saves.py`、`test_precise_actions.py`；`tests/acts/test_explore_modes.py`（三選一的靜心感悟）、`test_conquest_rules.py`；`tests/battle/test_stat_milestones_engine.py`；`tests/figures/test_day_scale.py`（選錯了到換日的那一刻）、`test_admin_timetable.py`；`tests/gear/test_mounts.py`；`tests/map/test_mapdata.py`、`test_mapdata_layers.py`；`tests/seal/test_seal_acts.py`（頒詔）；`tests/season/test_real_content.py`、`test_measure_tactics_gear.py`；探索包的 `test_explore_one.py`、`test_explore_one_2e.py`、`test_explore_one_2f.py`（換 `tianxia.engine.sensing.missed_today`）、`test_explore_one_fix.py`、`test_explore_one_polish.py`、`test_explore_one_single.py`、`test_explore_package.py`（換 `sensing.missed_today`）。
  - 改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/sense/actions.py tests/web/test_epiphany_name_web.py tests/web/test_explain2_web.py tests/web/test_prologue_web.py tests/web/test_jianghu_page_web.py tests/server/test_server.py tests/arts/test_explain2.py tests/arts/test_hints.py tests/arts/test_pr21_merge.py tests/arts/test_secret_recipes.py tests/core/test_prologue.py tests/core/test_storyline.py tests/core/test_engine.py tests/core/test_explain.py tests/core/test_biography.py tests/core/test_choose_refusal.py tests/core/test_old_saves.py tests/core/test_precise_actions.py tests/acts/test_explore_modes.py tests/acts/test_conquest_rules.py tests/battle/test_stat_milestones_engine.py tests/figures/test_day_scale.py tests/figures/test_admin_timetable.py tests/gear/test_mounts.py tests/map/test_mapdata.py tests/map/test_mapdata_layers.py tests/seal/test_seal_acts.py tests/season/test_real_content.py tests/season/test_measure_tactics_gear.py tianxia/features/explore/tests`（寫在指令裡的測試檔 `test_for` 連 slow 一起跑）。
- 前後一字不變：`scripts/same_behavior.py` 的 `sense` 一軌（`--tracks sense`）。
