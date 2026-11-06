# 懸賞榜（`tianxia/features/bounties/`）

城鎮的懸賞榜：官軍、黃巾自動掛的討伐、打探、護送，求兵（不用揭、當場交一把兵器），玩家卡上花銀兩掛的通緝，系統通緝（陣營、官府），人物掛的復仇與追剿、對自己陣營發的求援，書信與人物對話附的委託。交差走事件（打贏一場、出門一趟、舊探索、抵達、截殺打贏、人物託付）。每季都有（`Config.bounties.enabled`＋劇本有陣營＋這一季還沒收，不看第一季開關）。

**同字不同物**：包名 `bounties` 跟設定 `Config.bounties`（`models.py`）、季上的 `WorldState.bounties`（`state.py`）同字，不是同一件事：這裡是功能包，另兩個是舊的名字（同 `gear`）。

- 導覽：`docs/guide/散人與玩家互動.md`（懸賞榜、求兵、通緝）、`docs/guide/裝備與店面.md`（店面）、`docs/guide/大勢人物與賽季.md`（委託、求援、人物懸賞）。
- 設計稿：`docs/superpowers/specs/2026-10-06-陣營武學懸賞-design.md`（懸賞榜）、`2026-10-10-懸賞榜每季都有-design.md`、名聲設計 `2026-10-15-名聲-design.md`（4.6 系統通緝、5.4 官府海捕文書）、大勢人物擴充第二、三批（人物懸賞、委託、求援）、店面獨立介面 `2026-10-13-店面獨立介面-design.md`。
- 計畫：`docs/superpowers/plans/2026-11-07-懸賞榜包-第1批.md`。

## 裡面有什麼

- `rules.py`（原 `tianxia/bounties.py`，舊名留成指到這裡的 `sys.modules` 別名）：交差（`_complete`、`_done`、`on_*`、`_complete_rally`、`_complete_commission`、`_figure_thanks`）、揭下與放棄（`take`、`drop`、`take_problem`）、賞（`reward_*`、`_silver`、`_exp`、`_attached`）、求兵（`give`、`fit_problem`、`fitting`、`hand_in_options`、`give_choice`）、通緝（`post`、`post_problem`、`post_auto`、`deliver_refunds`、`deliver_lapses`）、掛單（`issue`、`issue_day`、`tick`、`step_tick`）、求援（`rallies`、`rally_reward`）、狀態（`status`、`targets`）、FB-162 那一句（`stale_line`）。
- `core/bounty_base.py`（**不在這一包，是核心本體**）：別人讀的純函式與字句（`active`、`board_here`、`close_board`、`mine`、`visible`、`open_bounties`、`title`、`how`、`issuer`、`stranded`、`join_note`、`drop_stranded`、`hunting`、`official_hit`、`open_commissions`、`is_browse_line`、`BOARD`、`ENEMY`……）與會寫季但只靠核心與共用層的 `post_rally`、`post_figure`；`rules.py` re-export 同一批物件。
- `wanted.py`（原 `tianxia/wanted.py`，舊名是別名）：通緝掛上玩家卡；載入這一包就登記進核心的 `core/cards.py`（`ACTIONS`；卡上照 `(order, id)` 排，通緝 65）。頂端只碰 `core/cards.py`，`rules`、`actions` 在函式裡才拿（registry 載入時不能連帶載入 `team`）。
- `actions.py`：原本 `Game` 上的 `_bounty_options`（`options`）、`_bounty`（`bounty`）、`post_wanted`、`_raid_bounty`（`raid_bounty`，事件 `raid_win` 的發布點跟著搬、位置不動；標題 `BOARD` 那一則紀錄**PM 認定不挪**），加 `_act` 的打開榜（`enter`）、`sync` 的退押金與作廢（`deliver`）、`own_turn_checks` 的系統通緝（`post_auto`）、`choose` 的 FB-162（`stale`）、`status_data` 的懸賞卡（`status`）。規則照模組屬性叫（`rules.take`、`rules.give`：`scripts/measure_sanren.py`、`sim_server_bots.py`、測試換掉模組上的，這裡照樣打得到）。
- `step_actions.py`：「你這一步」的 `commission`、`bounty` 兩格（原本 `step._STEP_CORE`）；`REF`、`place` 是核心本體 `step` 的。
- `bots.py`：假人看到 `bounty:` 的選項怎麼按（原本 `bot_policy.score` 那一段）。`act:bounties` 的分數、`_takeable`、`_bounty_here`、`_bounty_hop`、`BOUNTY_MOVE_SCORE` 留 `bot_policy`（前綴 `act` 是核心的），`bot_policy.BOUNTY_SCORE` 同值一份；整季機器人用的 `bot.take_bounties` 與 `pick()` 排除的 `act:bounties` 是共用底層，不搬（`give_choice` 跟著模組進包、經別名照舊拿得到）。
- 掛鉤：`prefix = "bounty"`；`choose` 接 `bounty:*`（標題 `BOARD`）；`verbs()` 一個 `Verb("bounties")`；`bus()` 六格（`win`、`outing`、`explore`、`arrive`、`raid_win`、`aid`；`aid` 第 45 批開，`figure_acts/aid_actions.py` 發布，PM 點頭，`BUS_ORDER` 只加這一列）；`world()` 四格（`step`、`week`、`day`、`start`；`WORLD_ORDER` 不動）；`steps()` 兩格（`commission` 的 `ref` 是 `"errand"`，格名與 ref 分開記）；`defection()` 的 `stranded`。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`picking_bounty`（榜開著）、`bounty_pick`（第三層指著哪一張求兵）、`bounties_done`（交差的總數，寫在 `rules._complete`）。
- `carried = ()`：換季全部跟著新角色重來。
- 不認領：`shop_line`、`shop_clue`、`shop_hold`（七間店共用，核心）；`Bounty` 類別與 `WorldState.bounties`、`rallies`、`bounty_seq`、`bounty_week`、`bounty_day` 的定義留 `state.py`；`Config.bounties` 留 `models.py`、`content.py` 的 `check_bounties` 留原處（第 34 批認定第 2 條）。
- 包外直接讀寫的（第 34 批認定第 9 條，照實記、寫哪一批收）：`atlas.travel_block` 讀 `picking_bounty`（第 50 批記的另外 13 個欄位排第 56 批，這是第 14 個）、酒肆包 `tavern:board` 直接寫 `picking_bounty`、核心 `Game._idle` 讀 `picking_bounty`（都是第 56 批選單收接縫）；`bot.py` 讀 `picking_bounty`、`shopview` 讀 `bounty_pick`（舊模組，假人底層與 `SHARED_LATER`）；引導包 `newbie.py`、列傳包 `standing.py`、傳承包 `legacy/rules.py` 讀 `bounties_done`（總表第 56 批）。反過來：這一包的 `open_commissions`（在核心 `bounty_base`）讀人物情誼包認領的 `PlayerState.letters`，`_complete_commission` 寫 `parley_owed`。

## 委派與留在原位的接縫

**`Game` 留的一行委派**：`_bounty_options`（`_everyday_options`）、`_bounty`（`tests/gear/test_shop2.py` 直接叫，同 `_smith`）、`_raid_bounty`（查詢服務，截殺與設伏）、`_bounty_deliver`（`sync`）、`_bounty_post_auto`（`own_turn_checks`）、`_bounty_stale`（`choose`）、`_bounty_status`（`status_data`）。人物情誼包回答這一包（服務清單二 `# bounties`，PM 認定乙案）：`_letter_thank`、`_parley_settle_task`、`_parley_keep`、`_parley_owed_line`、`_parley_ask_label`。`post_wanted` 沒人叫，不留。

**三間店不排進 `Shop`（PM 認定，排給第 56 批選單收接縫）**：`features_core._shops` 照 `FEATURES` 走，酒肆排在 `smithy`、`gear` 前面，要維持「懸賞榜 → 鐵匠鋪 → 馬市 → 其他店」就得挪包或開寫死的店面順序表；`sync` 只收鐵匠鋪、馬市，懸賞榜登記了 `drop_shops` 會在 `sync` 多收一次；鐵匠鋪 `here` 兩個意思。所以這些留原位：`_everyday_options` 的入口與 `picking_bounty` 選單、`_shop_open`、`shop_view` 的 `board` 那一支、`_drop_stale_references`、`_idle`、移動包 `departure.py` 收店那四行（先後不動）。`SHOP_ACTS`、`LEAVE_SHOP_IDS` 不動。

**原位讀 `core/bounty_base` 的（engine 不再 import 舊名 `bounties`，所以 `GAME_DIRECT` 不加）**：`choose` 的 `BROWSE_VERBS`、`is_browse_line`（翻頁不寫紀錄，照鐵匠鋪 `page:`）、投靠那一下的 `drop_stranded`、`week_unlock_names` 的 `active`、`_drop_stale_references`、`_shop_open`、`_everyday_options` 的 `board_here`、`visible`、`BOARD`、`close_board`。掛鉤逐項查過：`on_sync`、`on_drop_stale` 只問開著的包（`active`）而原位不看開關，`on_own_turn` 在暫停那一道之前（系統通緝要在之後），`choose_unlisted` 回 list（FB-162 回 `Refused`），`Feature.status` 是頂層另一個鍵（理由在邊界測試 `# bounties` 那一段）。

**人物情誼**：`letters.view` 沒有 ctx（殼與測試只給 `state`、`content`），書信卡的賞直接叫 `bounty_base.commission_line`，字問同包的 `parley.ask_label`；這一包的 `commission_reward` 經 `ctx._parley_ask_label` 問，同一句字。

**事件**：`raid_win` 的發布點在 `actions.raid_bounty`；`aid_actions.py` 發 `aid`；其餘四種發布點在各包。`bus_bypasses` 擋 `bounties.on_*` 這種名字，所以包的 `bus()` 寫 `rules.on_*`。

**過渡 import（這一包到舊模組）1 處**：`actions.py` → `shopview`（`board_key`；`SHARED_LATER`）。`rules.py` 讀的 `allied`、`equipment`、`materials`、`ranger`、`renown`、`roster`、`territory`、`treasures`、`weapons` 都在共用規則層。舊模組經別名碰這一包：`bot.py`、`bot_policy.py`、`shopview.py`、`scripts/`（`measure_sanren.py`、`sim_server_bots.py`）。懸賞榜的畫法（`boardHtml`、`paperHtml`、`boardUnpick`、`boardZoom`、`boardClose`、`boardLeave`、`boardHanded`、`STAMP_MS`）在 `web/bounties.js`（全部拆包第 65 批從 `app.js` 逐行切出來，90 行；`web = ("bounties.js",)`；計畫 `2026-11-06-網頁殼化-第65批.md`），點擊分派的 `case`、店面的框留在 `app.js`（殼）；`main.js` 的 `bountiesHtml`、`rewardChips` 第 67 批才切。

## 測試

**這一包的 `tests/`**（`test_for` 改這一包跑）：`test_bounties_smoke.py`（新寫的煙霧）、`test_renown_prize.py`、`test_renown_wanted.py`（第 41 批認定第 6 條：只整檔搬沒人用裸名 import、不是網頁類的）。

**留原處**：`tests/ranger/test_bounties.py`、`tests/bots/test_bounty_hand_in.py`（被裸名 import，第 61 批）、`test_bounty_tags.py`、`tests/web/test_sanren_web.py`（網頁類）、`test_season21_daily.py`（混合檔）。改 `web/bounties.js` 時 `test_for` 照檔名挑得到 `test_shop2_web`、`test_bounty_tags`、`test_shop_polish`、`test_shop_width`、`test_shell_web`。

**另外要跑的**（`test_for` 挑不到；改這一包開發與修正另跑，`-n 4`，不含 slow）：

- 網頁：`tests/server/test_server.py -k "page or version or scripts"`（那個檔太大，檔名刻意不寫進去）、`tests/bots/test_server_bots.py`（掃字）。
- 留原處的那幾個：`tests/ranger/test_bounties.py`、`tests/bots/test_bounty_hand_in.py`、`tests/ranger/test_bounty_tags.py`、`tests/web/test_sanren_web.py`、`tests/ranger/test_season21_daily.py`。
- 「你這一步」：`tests/bots/test_step.py`、`tests/map/test_weekcard.py` 與 `tianxia/step.py` 模組說明列的那一串（`tests/core/test_chapters.py`、`tests/figures/test_week_unlock.py`、`tianxia/features/companions/tests/test_errands_weekcard.py`、`tianxia/features/guide/tests/test_opening.py`）。
- 世界層四格（第 25 批認定第 7 條）：`tests/core/test_world.py` 與 `tianxia/world.py` 模組說明「另外要跑的」那一串——`tests/figures/test_timetable.py`、`test_seats.py`、`tests/core/test_season_pause.py`、`tianxia/features/companions/tests/test_stances_tie.py`、`tests/figures/test_week7_season.py`、`test_season21_frame.py`、`test_season21_caps.py`、`test_plans.py`、`test_figure_life.py`、`test_figure_attrition.py`、`tests/battle/test_fronts.py`、`tests/figures/test_front_lines.py`、`test_finale.py`、`test_admin_triggers.py`、`test_calendar.py`、`tests/seal/test_seal.py`、`test_seal_engine.py`、`test_seal_acts.py`、`tests/acts/test_conquest_rules.py`、`tianxia/features/stamina_plays/tests/test_stamina_plays.py`、`tests/core/test_marks_wired.py`、`tianxia/features/looks/tests/test_looks_mvp.py`。
- 核心契約：`tests/core/test_contract_core.py`、`test_contract_features.py`、`test_feature_boundaries.py`、`test_social.py`、`tests/arts/test_discuss.py`。
- 人物：`tests/figures/test_figure_life_batch3.py`、`test_week_unlock.py`、`test_gentry_allied.py`；人物情誼包 `test_parley.py`、`test_parley_two.py`、`test_relations_letters.py`；陣營包 `test_four_wins_wiring.py`；探索包 `test_explore_one.py`、`test_explore_one_fix.py`；玩家互動包 `test_raid.py`；`tests/acts/test_territory.py`。
- 經舊名用到懸賞榜、`test_for` 挑不到的：`tests/gear/test_treasures.py`、`test_shop2.py`、`test_shop_polish.py`、`test_weapons.py`、`test_four_tiers.py`、`tests/battle/test_drill_gates_engine.py`、`test_maxed_xinde.py`、`tests/bots/test_bot_policy_stuck.py`、`tests/core/test_precise_actions.py`、`tests/ranger/test_renown_ranger.py`、`tests/server/test_server.py`。
- 沒有 `Game` 的測試叫交差用 `tests/kit/bounty_ctx.py`（`SimpleNamespace` 接真的 `letters`、`parley`）；不要開 `Game`（建構子會 `open_world()`、`_drop_stale_references`）。

比對軌：`scripts/same_behavior.py` 的 `placard`（親手按 `bounty:*`、卡上通緝、系統通緝、退押金、作廢、`aid`、求援、人物倒下、假人）加 `herald`、`compass`、`world`。

**反方向**（第 36 批認定第 1 條）：見計畫第五節；這一批對 import 的舊模組各量一次 `test_for.pick`，少挑到的寫進計畫。
