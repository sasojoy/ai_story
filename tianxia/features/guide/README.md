# 新手引導（`tianxia/features/guide/`）

草廬之後的引導框（說書人、初入江湖的老周）、碰到才說的提示、新手目標、開局第一分鐘（城門口三選一與第一封託付）、入伍段（引薦人帶兩步）、序章的畫面與重看。全部拆包第 22 批（引導一）搬進來（計畫 `docs/superpowers/plans/2026-11-01-新手引導包-第1批.md`）；玩法說明（`howto`）是第 59 批（引導二）。網頁那一半（`onb`、`guideGlow`、`watchOrders` 那幾個）第 66 批切進 `web/guide.js`。

- 導覽：`docs/guide/核心與存檔.md` 的「新手引導（功能包 `tianxia/features/guide/`）」那一節。
- 設計稿：沒有版本號——新手引導重做設計（Joy 2026-10-22，https://claude.ai/artifact/Eb25MwPveJMYSf5Ge4mDyx：第四節入伍段、第五節碰到才說、第六節新手目標、第七節略過與換季、8.1 對話框）；新手引導計畫一～三（`docs/superpowers/plans/2026-10-06-新手引導-1-序章.md`、`-2-入伍段.md`、`-3-碰到才說.md`）；開局第一分鐘：減法季整合設計 6.7。

## 裡面有什麼

- `rules.py`（原 `tianxia/guide.py`：說書人的步驟、任務卡、下一步）、`hints.py`、`newbie.py`、`opening.py`、`enlist.py`（原名）：五個舊名都留成 `sys.modules` 別名（同一個模組物件），`from tianxia import guide`、`from tianxia.guide import note_action`（engine）與測試照舊拿得到（本週卡 `weekcard` 第 36 批起收進核心，三選一還沒選改問 `Game._opening_pending` 委派，不再 import `opening`）。
- `actions.py`：原本 `Game` 上的 31 個方法（名字去掉前導底線），加上核心原位叫的 11 個服務的本體（`opening_on`……`enlist_expire`；`Game._note_action` 叫 engine 模組層的 `note_action`，見下）。
- `checks.py`：內容檢查（`check_content`）——碰到才說（`hints.json`）那一塊原本在 `content.validate`，核心不准 import 包，搬進這裡、句子照抄。
- `HutReward`（序章步驟的獎勵那一行的記號）搬進核心 `tianxia/core/services.py`：核心的 `Game._guide`、`_menxia_entry` 認它；`rules.HutReward` 是同一個類別。
- 掛鉤：`enabled` 一直是 True（引導、提示、新手目標、開局各有自己的開關）、`check_content`、`player_fields`／`carried`、叛投那一刻的格 `defection()`（`clear` 位置的 `hints`：`hints.defect_clear`，舊陣營的引薦人排著還沒說的提示作廢；全部拆包第 32 批，原本 `defection.clear_progress` 直接寫 `hint_queue`；釘住這一格的測試在包外、改這一包時 `test_for` 挑不到：`tests/arts/test_hints.py::test_defecting_drops_the_old_sides_queued_hints_and_keeps_the_mentors`，下面「另外要跑的」那一串已經列了這個檔；`tianxia/features/faction/tests/test_defection.py::test_defecting_drops_the_old_sides_queued_hints` 測的是同一件事）。**沒有選項前綴**：動作走 `server.MAIN_ACTIONS`（`hints_off`、`skip_tutorial`、`view_map`、`view_orders`、`view_tab`、`guide_ack`、`newbie_drifter`）與 `/api/prologue`（`server.py` 一行沒動，照舊叫 Game 的委派）；選單上的那幾顆是別人的（`act:rest` 是核心 `act:` 的子動詞、開局三選一是事件的 `choice:`、投靠是 `faction:`），所以沒有 `bots.py`、`bot_policy` 不動。
- 「你這一步」的格 `steps()`（全部拆包第 36 批；順序在核心的 `STEP_ORDER`：伏筆之後、去投靠之前）：`newbie`（`actions.newbie_step_items`／`newbie_step_place`：讀殼算好傳進來的 `status["newbie"]`〔`newbie_view` 那一份，不重算〕，每一條一件、多一個 `i`；目標是「去做」帶去的地點；原本 `weekcard._steps` 的新手目標那一段與 `step._target` 的新手目標那一支）。不問 `enabled`。`_nearest_to`（委派）第 36 批起也是查詢服務：軍情包的軍令、陣營包的去投靠那兩格補目標時經 `ctx._nearest_to` 問（原本舊模組 `step.py` 直接叫 `game._nearest_to`）。

- `howto.py`（全部拆包第 59 批「引導二」；原 `tianxia/howto.py` 的底，字一個不動）：體力條點開的說明（`stamina_lines`）、建角色送回體丹那一行（`gift_line`）、戰況圖卡點開的說明（`war_help`）、名望與名聲怎麼來、設定抽屜那一頁（`page`：只照核心的 `howto_table()` 接起來）
- `routes.py`：`/api/howto`（第 59 批從 `server.py` 搬來；`/api/prologue` 還在殼）

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`guide_done`、`guide_outro`、`enlist_end`、`enlist_since`、`hint_queue`（換季跟著新角色重來）；`hints_seen`、`hints_off`、`newbie_marks`、`newbie_done`（`carried`：換季照帶，照舊在 `Game._reset_player_for_new_season` 原位帶）。
- 另外是這一包的、可是「做到才帶」的：`tutorial_step`（做到不分季的那幾步才帶）、`guide_skipped`（同上）、`enlist_step`（走完才帶）——契約測試的換季那一條擺不出這種條件，不列進 `player_fields`。`onboarding`（引導照哪一版記的）是核心的版本章。
- 內容：這一包的 `content/tutorial.json`、`hints.json`、`opening.json`，開局與序章的事件池 `content/events/opening.json`、`prologue.json`（全部拆包第 63 批；跟 `opening.json` 是不同的檔）（`content` 宣告；`content.py` 照它到這一包的 `content/` 載）。測試內容的 `tutorial.json` 在 `tests/content/`（第 63 批）。

## 委派與留在原位的接縫

`Game` 留 24 個一行委派（公開 14：`enlist_glow`、`guide_box`、`newbie_view`、`newbie_drifter`、`set_hints_off`、`guide_ack`、`skip_tutorial`、`view_orders`、`view_map`、`view_tab`、`prologue_view`、`onboard_view`、`prologue_recap`、`quest_text`；私有 10：`_note_gift`、`_graduate`、`_begin_enlistment`、`_greet_rejoin`、`_hint`、`_hint_triggers`、`_check_hints`、`_nearest_to`、`_newbie_go`、`_rest`），加上核心原位與出陣包叫的服務 12 個（`_note_action`、`_opening_on`、`_opening_begin`、`_opening_pending`、`_opening_deliver`、`_opening_gate`、`_tutorial_intro`、`_guide_speakers`）與酒肆的查詢服務 3 個（`_tavern_on`、`_tavern_here`、`_tavern_at`：引導包問酒肆，包不能 import 包）。

核心原位碰引導的那幾處都沒有第 11 批的掛鉤，改叫上面的服務、記進邊界測試的 `GAME_DELEGATE_CALLERS`（35 對；全部拆包第 24 批有所感的 `_sense_apply`、`sense_draw` 搬進有所感包、包裡經 ctx 叫，剩 33 對）與 `CORE_DELEGATE_CALLERS`（事件檢定 6 對），**沒有新增 `GAME_DIRECT`**（原本兩筆 `_hint_triggers`、`_newbie_go` 讀酒肆的拿掉）：

- 做完一件事引導跟著走（`_note_action`）：`choose` 五行、`take_stamina_pill`、`_menxia_entry` 留在核心原位。**第 57 批量過，不開事件**（第 26 批認定第 6 條交那一批量；計畫第四節）：`BUS_ORDER` 沒有「做完一個動作」這種事件，開新事件要過 PM；最接近的 `arrive` 也接不了（`departure.arrive` 的 `left` 要在 `note_action` 之後算，訂閱者的回話會排到它前面）；`choose` 那幾行之間夾著 `_opening_deliver`，`_menxia_entry` 還把 `HutReward` 拆進 changes，都是位置就是行為。進了包的（`faction/join_actions.py`、`travel/departure.py`）已經經 `ctx`（配點 `allocate_stat` 第 23 批進修練包，那裡的 `_note_action`、`_check_hints` 都經 `ctx` 叫）。
- 碰到才說（`_check_hints`、`_hint`）：`choose`、`sync`、`travel`、`_menxia_entry`、`_act`、`_brush_off`、`_open_dialogue`，與核心 `event_check.answer_event`、`answer_branch`（連 `_begin_enlistment`、`_greet_rejoin`）。
- 開局（`_opening_*`）：`choose`、`check_in`、`_auto_checkin`、`checkin_view`、`now_entry_html`、`Game.new`。
- 換季開場那一則的引導（`_reset_player_for_new_season` 的 `_tutorial_intro`：是 `_write` 的引數）、核心的引導框服務（`_note_guide` 的 `_guide_speakers`）、`act:rest`（`_act` 的 `_rest`）。
- 掃描看不到的：`Game.new`（classmethod，用 `game.` 叫）的 `_opening_on`、`_opening_begin`、`_tutorial_intro`、`_graduate`、`_note_gift`；舊模組 `step.py` 叫 `game._nearest_to`（第 36 批起 `step.py` 收進核心本體、不再叫它：改由軍情包、陣營包那兩格經 `ctx._nearest_to` 問）。

**`note_action` 被測試換掉的那一層**：`tests/core/test_engine.py` 換的是 `tianxia.engine.note_action`（看 `args[3]`／`args[-1]`），所以 `Game._note_action` 的本體叫 engine 模組層那個名字（`from .guide import note_action`：別名）；包裡的 `view_orders`、`view_map`、`view_tab` 與出陣包的六處（`actions.py`、`duel_actions.py` 四處；守勢 `train_actions.duty` 兩處：原本的 `Game._duty` 第 17 批進了出陣包，這一批合進 develop 時改）都經 `ctx._note_action`。包裡互相叫直接叫函式，只有被測試換掉的 `_hint_triggers`（`test_hints` 換掉 `game._hint_triggers`）經 `ctx`。

**玩法說明的掛鉤**（第 59 批；計畫 `docs/superpowers/plans/2026-11-06-玩法說明-第59批.md`）：`Feature.howto()`（`HowtoHook`、`HowtoPage`，`core/features.py` 檔尾）。那一頁的 22 格照核心寫死的 `HOWTO_ORDER` 接（順序就是行為，`test_contract_core` 逐字鎖；改表先過 PM），這一包交 `season`、`act_head`、`growth`、`stamina`、`fame`、`bag` 六格，其餘 16 包各交自己那一節；別節中間判斷在別包的句子走 `HOWTO_INSERTS`（`fame_seal`、`fame_tavern`、`land_seal`，主人玉璽、酒肆）。整包不看 `enabled`（判斷都在各節自己裡面，跟搬之前一樣）。兩包以上要用的 `section`、`tenth`、`order_pushers`、`SOME_PLACES` 在核心 `core/howto_base.py`。
**Game 上這一批留的一行委派**：`howto_text`（路由與二十幾個測試）、`_top_up_line`（`_top_up_pills`：讀檔那一刻寫一行）、`_stamina_help`、`_war_help`（`status_data`：status 掛鉤只問開著的包、鍵的順序算行為，第 66 批才收）。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組（全部拆包第 40 批合完重印 3 處，原本 6 處）：`opening.py` 1（`bounties`）、`actions.py` 1（`atlas`、`howto`；同一行的 `figures` 第 40 批收進共用規則層，不算過渡，註照留「過渡：待搬」；`rules.py` 的 `ranks`、`enlist.py` 的 `orders` 第 40 批收進共用規則層，註改寫成「共用規則層」；`world` 那一行全部拆包第 25 批收進核心本體，註拿掉；`create` 第 44 批煉製自創成包時拿掉：`h_create` 改問包的三個查詢服務 `ctx._create_on()`、`_create_allowed()`、`_create_price()`；`training` 第 18 批登記進共用規則層，不算過渡；`sensing` 全部拆包第 24 批有所感成包時拿掉：假人走序章那一下改問有所感包的查詢服務 `ctx._sense_prologue_choice()`）。
- 第 45 批合完重印 **1 處**：`actions.py` → `howto`；`opening.py` 的 `issuer` 改讀核心 `core/bounty_base`。
- 第 50 批合完重印 **2 處**：`opening.py` → `bounties`、`actions.py` → `howto`（原本 `atlas`、`figures`、`howto` 同一行，拆成兩行，`atlas`、`figures` 那一行註「共用規則層」）。`actions.py` 讀軍情包認領的 `fragments` 那一處照舊不收（第 34 批認定第 9 條；總表第 59 列）。
- 第 59 批合完重印 **1 處**：`howto.py` 函式裡 → `events`（`fame_ranges` 的 `is_rare`）；`actions.py` 的 `howto` 改讀包裡那一份。舊名 `tianxia/howto.py` 留成重新匯出的殼（內容在 17 包，`sys.modules` 別名只能指一包），舊的頂層名字 110 個一個不少；沒有產品程式 import 它，二十幾個測試檔改完就拿掉（第 61 批之後）。
- 服務清單（`tianxia/core/services.py`）這一包加的：一、共用 `_check_hints`、`_hint`、`_note_action`、`_preparing`、`_journal_guide`、`_free_text_of`、`HutReward`；二、查詢 `_at_battle`（決戰）、`_tavern_on`、`_tavern_here`、`_tavern_at`（酒肆）、`_recruit_target`、`_recruitable_here`（人物情誼；第 19 批成包，從過渡改成查詢服務）、`_create_on`、`_create_allowed`、`_create_price`、`forge`（煉製自創，第 44 批成包，從過渡改成查詢服務）；三、過渡 `slot_insight`、`switch_art`、`practice`、`allocate_stat`、`melt_art`（武學）、`_hint_triggers`（自己的委派）。

## 測試

- 這一包的（整檔屬於這一包、第 22 批搬進來的）：`tests/test_guide.py`（23 條：說書人的步驟、下一步、任務卡；原 `tests/core/`）、`test_guide_box.py`（20：對話框；`parents[2]` 改 `parents[4]`）、`test_enlist.py`（53：入伍段）、`test_opening.py`（9：開局第一分鐘）、`test_guide_smoke.py`（1，smoke：week7 新角色在城門口選了一顆、託付送到、任務卡亮新手目標）；審查之後照總表與調查的歸屬再搬兩個：`test_onboard.py`（17：初入江湖的七步，原 `tests/core/`；調查 `area_core` 歸這一包）、`test_newbie_hours.py`（3：新手期照現實時數，測的是共用規則層 `roster.newbie`；總表附錄甲歸這一包）。`pytest tianxia/features/guide/tests -n 4 -m "slow or not slow"`：126 條約 14 秒。
- 第 59 批搬進來的（玩法說明）：`test_core_loop_howto.py`、`test_econ_howto.py`（原 `tests/core/`）；新加 `test_howto_route.py`（`/api/howto` 掛得到）。
- **改玩法說明的句子，`test_for` 只挑那一包，另外要跑的**：`tests/core/test_explain.py`、`tests/arts/test_explain2.py`、`tests/arts/test_stack_rule.py`、`tests/acts/test_conquest_flip.py`、`test_conquest_rules.py`、`test_conquest_siege.py`、`tests/battle/test_terrain_arts.py`、`tests/core/test_econ_divine.py`、`test_journal.py`、`test_precise_actions.py`、`test_renown_status.py`、`test_social.py`、`tests/figures/test_day_scale.py`、`test_season21_caps.py`、`test_week7_season.py`、`test_gentry_allied.py`、`tests/gear/test_four_tiers.py`、`tests/ranger/test_season21_daily.py`、`tests/server/test_set_password.py`、`tests/web/test_explain_web.py`、`test_explain2_web.py`。
- **`test_for` 挑不到的、另外要跑的**（這一輪不搬、不拆）：
  - 測的是共用規則層 `prologue`（序章）的：`tests/core/test_prologue.py`（106 條，連假人走序章 `_graduate`；搬進來的話改包的檔會挑到 350 條，超過 300；調查 `area_core` 歸這一包，交 PM）。
  - 碰到才說的觸發看遍各包（決戰換掉 `_battle_status`、酒肆的 `h_tavern`、同伴、事件）：`tests/arts/test_hints.py`（122 條；搬進來的話改包的檔會挑到 347 條，超過 300；總表附錄甲歸這一包，交 PM）。
  - 網頁（第 3 階跟網頁檔一起搬）：`tests/web/test_prologue_web.py`（107）、`test_hints_web.py`（8）、`test_enlist_web.py`（21）、`test_opening_web.py`（3）。
  - 換掉 `tianxia.engine.note_action` 的 `tests/core/test_engine.py`；`_newbie_go` 的 `tests/acts/test_training.py`；本週卡「你這一步」的 `tests/bots/test_step.py`、`tests/map/test_weekcard.py`（第 36 批起新手目標是這一包登記的 `newbie` 那一格，先後由核心契約 `tests/core/test_contract_core.py` 的 `# core_step` 鎖住）；開局擋簽到的 `tianxia/features/checkin/tests/test_checkin.py`；入伍段與軍令的 `tests/figures/test_orders.py`、`test_promotions_high.py`、`test_gentry_allied.py`；任務卡的 `tests/core/test_world.py`、`tests/figures/test_calendar.py`、`test_finale.py`、`test_season21_frame.py`、`tests/ranger/test_season21_daily.py`；提示與玩法說明的 `tests/core/test_explain.py`；探索包的 `test_explore_one_polish.py`（`hints`）、`test_explore_one_fix.py`（`newbie_view`）；`tests/season/test_real_content.py`、`tests/server/test_server.py`。
  - 改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/guide/actions.py tests/core/test_prologue.py tests/arts/test_hints.py tests/web/test_prologue_web.py tests/web/test_hints_web.py tests/web/test_enlist_web.py tests/web/test_opening_web.py tests/core/test_engine.py tests/acts/test_training.py tests/bots/test_step.py tianxia/features/checkin/tests/test_checkin.py tests/figures/test_orders.py tests/figures/test_promotions_high.py tests/figures/test_gentry_allied.py tests/core/test_world.py tests/figures/test_calendar.py tests/figures/test_finale.py tests/figures/test_season21_frame.py tests/ranger/test_season21_daily.py tests/core/test_explain.py tianxia/features/explore/tests/test_explore_one_polish.py tianxia/features/explore/tests/test_explore_one_fix.py tests/season/test_real_content.py tests/server/test_server.py`（上面列的 23 個檔一個不漏；寫在指令裡的測試檔 `test_for` 連 slow 一起跑，`test_real_content` 用真實內容跑整季的那幾條最慢。假人走序章的 `test_real_content::test_bots_and_scripts_skip_the_real_prologue_and_look_like_graduates` 不是 slow，`actions.graduate_pass` 改壞了只有它抓得到）。
- 前後一字不變：`scripts/same_behavior.py` 的 `guide` 一軌（`--tracks guide`）。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.deliver` 的 `enlist`（`actions.deliver_enlist`）、`hints`（經 `ctx._check_hints`）；`stale.first` 的 `guide`（`actions.mark_veteran`：要在對齊賽季之前）；`season.carry` 的 `guide`（`actions.carry_season`，排最前面）。`_base_step_count`、`_enlist_done`、`_mark_veteran`、`_enlist_expire` 四個委派第 55 批拿掉。

**第 56 批（選單收接縫，核心批）**：`newbie.py` 讀懸賞的張數改問核心 `bounty_base.done_count`；先後在 `core/features.py` 的 `MENU_ORDER`；上面寫「留委派」「原位」的以這一句為準。

**第 57 批（分派與標題收接縫，核心批）**：`verbs()` 是新開的（`rest`：按下去與紀錄標題）。委派 `_rest` 留著（`scripts/same_behavior.py` 直接叫）。改這一格另外跑 `tests/core/test_prologue.py`、`tests/core/test_engine.py -k rest`；序章以外走不到，`same_behavior` 的 `levy` 一軌在鎖裡換掉 `prologue.instant_rest` 才按得到。

## 畫面與狀態列（全部拆包第 66 批）

- 畫面：`web/guide.js`（引導的發光與閃一閃、入伍段看過軍令、玩法說明與重看序章；路線發光、新手目標、說書人的框、`proGuide` 第 67 批從 `main.js` 切進來）、`web/guide.css`（新手目標；`.onb-dim`、`.glow`、`.lit` 要蓋別人，留 `style.css`）；點擊分派的 `case`、`choose` 留 `app.js`。
- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`status` 表 `newbie`；`main` 表 `guide`（`guide`、`prologue`、`onboard`）、`glow`（`actions.glow_slot` 改已經合進去的 `view["guide"]`，沒有鍵）。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`hints_off`（回 `None`，同委派）、`skip_tutorial`、`view_map`、`view_orders`、`view_tab`、`guide_ack`、`newbie_drifter`。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。
