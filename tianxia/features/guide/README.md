# 新手引導（`tianxia/features/guide/`）

草廬之後的引導框（說書人、初入江湖的老周）、碰到才說的提示、新手目標、開局第一分鐘（城門口三選一與第一封託付）、入伍段（引薦人帶兩步）、序章的畫面與重看。全部拆包第 22 批（引導一）搬進來（計畫 `docs/superpowers/plans/2026-11-01-新手引導包-第1批.md`）；玩法說明（`howto`）是第 59 批（引導二）。網頁那一半（`web/app.js` 的 `onb`、`guideGlow`、`watchOrders` 那幾個）第 3 階再切。

- 導覽：`docs/guide/核心與存檔.md` 的「新手引導（功能包 `tianxia/features/guide/`）」那一節。
- 設計稿：沒有版本號——新手引導重做設計（Joy 2026-10-22，https://claude.ai/artifact/Eb25MwPveJMYSf5Ge4mDyx：第四節入伍段、第五節碰到才說、第六節新手目標、第七節略過與換季、8.1 對話框）；新手引導計畫一～三（`docs/superpowers/plans/2026-10-06-新手引導-1-序章.md`、`-2-入伍段.md`、`-3-碰到才說.md`）；開局第一分鐘：減法季整合設計 6.7。

## 裡面有什麼

- `rules.py`（原 `tianxia/guide.py`：說書人的步驟、任務卡、下一步）、`hints.py`、`newbie.py`、`opening.py`、`enlist.py`（原名）：五個舊名都留成 `sys.modules` 別名（同一個模組物件），`from tianxia import guide`、`from tianxia.guide import note_action`（engine）、舊模組 `weekcard`（`opening`）與測試照舊拿得到。
- `actions.py`：原本 `Game` 上的 31 個方法（名字去掉前導底線），加上核心原位叫的 11 個服務的本體（`opening_on`……`enlist_expire`；`Game._note_action` 叫 engine 模組層的 `note_action`，見下）。
- `checks.py`：內容檢查（`check_content`）——碰到才說（`hints.json`）那一塊原本在 `content.validate`，核心不准 import 包，搬進這裡、句子照抄。
- `HutReward`（序章步驟的獎勵那一行的記號）搬進核心 `tianxia/core/services.py`：核心的 `Game._guide`、`_menxia_entry` 認它；`rules.HutReward` 是同一個類別。
- 掛鉤：`enabled` 一直是 True（引導、提示、新手目標、開局各有自己的開關）、`check_content`、`player_fields`／`carried`。**沒有選項前綴**：動作走 `server.MAIN_ACTIONS`（`hints_off`、`skip_tutorial`、`view_map`、`view_orders`、`view_tab`、`guide_ack`、`newbie_drifter`）與 `/api/prologue`（`server.py` 一行沒動，照舊叫 Game 的委派）；選單上的那幾顆是別人的（`act:rest` 是核心 `act:` 的子動詞、開局三選一是事件的 `choice:`、投靠是 `faction:`），所以沒有 `bots.py`、`bot_policy` 不動。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`guide_done`、`guide_outro`、`enlist_end`、`enlist_since`、`hint_queue`（換季跟著新角色重來）；`hints_seen`、`hints_off`、`newbie_marks`、`newbie_done`（`carried`：換季照帶，照舊在 `Game._reset_player_for_new_season` 原位帶）。
- 另外是這一包的、可是「做到才帶」的：`tutorial_step`（做到不分季的那幾步才帶）、`guide_skipped`（同上）、`enlist_step`（走完才帶）——契約測試的換季那一條擺不出這種條件，不列進 `player_fields`。`onboarding`（引導照哪一版記的）是核心的版本章。
- 內容：`content/tutorial.json`、`hints.json`、`opening.json`（`content` 宣告；`content.py` 照舊讀）。

## 委派與留在原位的接縫

`Game` 留 24 個一行委派（公開 14：`enlist_glow`、`guide_box`、`newbie_view`、`newbie_drifter`、`set_hints_off`、`guide_ack`、`skip_tutorial`、`view_orders`、`view_map`、`view_tab`、`prologue_view`、`onboard_view`、`prologue_recap`、`quest_text`；私有 10：`_note_gift`、`_graduate`、`_begin_enlistment`、`_greet_rejoin`、`_hint`、`_hint_triggers`、`_check_hints`、`_nearest_to`、`_newbie_go`、`_rest`），加上核心原位與出陣包叫的服務 12 個（`_note_action`、`_opening_on`、`_opening_begin`、`_opening_pending`、`_opening_deliver`、`_opening_gate`、`_tutorial_intro`、`_base_step_count`、`_guide_speakers`、`_enlist_done`、`_mark_veteran`、`_enlist_expire`）與酒肆的查詢服務 3 個（`_tavern_on`、`_tavern_here`、`_tavern_at`：引導包問酒肆，包不能 import 包）。

核心原位碰引導的那幾處都沒有第 11 批的掛鉤，改叫上面的服務、記進邊界測試的 `GAME_DELEGATE_CALLERS`（35 對；全部拆包第 24 批有所感的 `_sense_apply`、`sense_draw` 搬進有所感包、包裡經 ctx 叫，剩 33 對）與 `CORE_DELEGATE_CALLERS`（事件檢定 6 對），**沒有新增 `GAME_DIRECT`**（原本兩筆 `_hint_triggers`、`_newbie_go` 讀酒肆的拿掉）：

- 做完一件事引導跟著走（`_note_action`）：`choose` 七處、`_order_credit`、`_faction_step`、`_arrive`、`take_stamina_pill`、`_menxia_entry`——總表第 26 批的事件（配點 `allocate_stat` 第 23 批進修練包，那裡的 `_note_action`、`_check_hints` 都經 `ctx` 叫）。
- 碰到才說（`_check_hints`、`_hint`）：`choose`、`sync`、`travel`、`_menxia_entry`、`_act`、`_brush_off`、`_open_dialogue`、`_town_drill`，與核心 `event_check.answer_event`、`answer_branch`（連 `_begin_enlistment`、`_greet_rejoin`）。
- 開局（`_opening_*`）：`choose`、`check_in`、`_auto_checkin`、`checkin_view`、`now_entry_html`、`Game.new`。
- 換季照帶（`_reset_player_for_new_season`：`_enlist_done`、`_base_step_count`、`_tutorial_intro`）、清失效參照一開頭（`_mark_veteran`）、`sync` 的引薦人結語（`_enlist_expire`）、核心的引導框服務（`_note_guide` 的 `_guide_speakers`）、狀態列的任務卡（`status_data` 的 `newbie_view`）、`act:rest`（`_act` 的 `_rest`）。
- 掃描看不到的：`Game.new`（classmethod，用 `game.` 叫）的 `_opening_on`、`_opening_begin`、`_tutorial_intro`、`_graduate`、`_note_gift`；舊模組 `step.py` 叫 `game._nearest_to`。

**`note_action` 被測試換掉的那一層**：`tests/core/test_engine.py` 換的是 `tianxia.engine.note_action`（看 `args[3]`／`args[-1]`），所以 `Game._note_action` 的本體叫 engine 模組層那個名字（`from .guide import note_action`：別名）；包裡的 `view_orders`、`view_map`、`view_tab` 與出陣包的六處（`actions.py`、`duel_actions.py` 四處；守勢 `train_actions.duty` 兩處：原本的 `Game._duty` 第 17 批進了出陣包，這一批合進 develop 時改）都經 `ctx._note_action`。包裡互相叫直接叫函式，只有被測試換掉的 `_hint_triggers`（`test_hints` 換掉 `game._hint_triggers`）經 `ctx`。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組：`rules.py` 2 行（`explore_modes`、`ranks`；`world`）、`opening.py` 1（`bounties`）、`enlist.py` 1（`orders`）、`actions.py` 1（`atlas`、`create`、`figures`、`howto`、`training`；`sensing` 全部拆包第 24 批有所感成包時拿掉：假人走序章那一下改問有所感包的查詢服務 `ctx._sense_prologue_choice()`）。
- 服務清單（`tianxia/core/services.py`）這一包加的：一、共用 `_check_hints`、`_hint`、`_note_action`、`_preparing`、`_journal_guide`、`_free_text_of`、`HutReward`；二、查詢 `_at_battle`（決戰）、`_tavern_on`、`_tavern_here`、`_tavern_at`（酒肆）、`_recruit_target`、`_recruitable_here`（人物情誼；第 19 批成包，從過渡改成查詢服務）；三、過渡 `slot_insight`、`switch_art`、`practice`、`allocate_stat`、`melt_art`（武學）、`forge`（煉製）、`_hint_triggers`（自己的委派）。

## 測試

- 這一包的（整檔屬於這一包、第 22 批搬進來的）：`tests/test_guide.py`（23 條：說書人的步驟、下一步、任務卡；原 `tests/core/`）、`test_guide_box.py`（20：對話框；`parents[2]` 改 `parents[4]`）、`test_enlist.py`（53：入伍段）、`test_opening.py`（9：開局第一分鐘）、`test_guide_smoke.py`（1，smoke：week7 新角色在城門口選了一顆、託付送到、任務卡亮新手目標）；審查之後照總表與調查的歸屬再搬兩個：`test_onboard.py`（17：初入江湖的七步，原 `tests/core/`；調查 `area_core` 歸這一包）、`test_newbie_hours.py`（3：新手期照現實時數，測的是共用規則層 `roster.newbie`；總表附錄甲歸這一包）。`pytest tianxia/features/guide/tests -n 4 -m "slow or not slow"`：126 條約 14 秒。
- **`test_for` 挑不到的、另外要跑的**（這一輪不搬、不拆）：
  - 測的是共用規則層 `prologue`（序章）的：`tests/core/test_prologue.py`（106 條，連假人走序章 `_graduate`；搬進來的話改包的檔會挑到 350 條，超過 300；調查 `area_core` 歸這一包，交 PM）。
  - 碰到才說的觸發看遍各包（決戰換掉 `_battle_status`、酒肆的 `h_tavern`、同伴、事件）：`tests/arts/test_hints.py`（122 條；搬進來的話改包的檔會挑到 347 條，超過 300；總表附錄甲歸這一包，交 PM）。
  - 網頁（第 3 階跟網頁檔一起搬）：`tests/web/test_prologue_web.py`（107）、`test_hints_web.py`（8）、`test_enlist_web.py`（21）、`test_opening_web.py`（3）。
  - 換掉 `tianxia.engine.note_action` 的 `tests/core/test_engine.py`；`_newbie_go` 的 `tests/acts/test_training.py`；本週卡「你這一步」的 `tests/bots/test_step.py`；開局擋簽到的 `tests/figures/test_checkin.py`；入伍段與軍令的 `tests/figures/test_orders.py`、`test_promotions_high.py`、`test_gentry_allied.py`；任務卡的 `tests/core/test_world.py`、`tests/figures/test_calendar.py`、`test_finale.py`、`test_season21_frame.py`、`tests/ranger/test_season21_daily.py`；提示與玩法說明的 `tests/core/test_explain.py`；探索包的 `test_explore_one_polish.py`（`hints`）、`test_explore_one_fix.py`（`newbie_view`）；`tests/season/test_real_content.py`、`tests/server/test_server.py`。
  - 改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/guide/actions.py tests/core/test_prologue.py tests/arts/test_hints.py tests/web/test_prologue_web.py tests/web/test_hints_web.py tests/web/test_enlist_web.py tests/web/test_opening_web.py tests/core/test_engine.py tests/acts/test_training.py tests/bots/test_step.py tests/figures/test_checkin.py tests/figures/test_orders.py tests/figures/test_promotions_high.py tests/figures/test_gentry_allied.py tests/core/test_world.py tests/figures/test_calendar.py tests/figures/test_finale.py tests/figures/test_season21_frame.py tests/ranger/test_season21_daily.py tests/core/test_explain.py tianxia/features/explore/tests/test_explore_one_polish.py tianxia/features/explore/tests/test_explore_one_fix.py tests/season/test_real_content.py tests/server/test_server.py`（上面列的 23 個檔一個不漏；寫在指令裡的測試檔 `test_for` 連 slow 一起跑，`test_real_content` 用真實內容跑整季的那幾條最慢。假人走序章的 `test_real_content::test_bots_and_scripts_skip_the_real_prologue_and_look_like_graduates` 不是 slow，`actions.graduate_pass` 改壞了只有它抓得到）。
- 前後一字不變：`scripts/same_behavior.py` 的 `guide` 一軌（`--tracks guide`）。
