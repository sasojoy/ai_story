"""核心給功能包的服務（開發規範手冊 3.3、3.10）。第一階 ctx 就是 Game 本身；功能包只准叫下面這張清單上的東西。
清單之外要用 Game 的別的方法，先加進這張清單（在派工單或回報裡寫明，PM 看過），不要直接叫。

清單分四段（主動搬六包批次表第二節，PM 2026-10-31）：一、共用服務（每一包都可以用的）；二、查詢服務（別包問「我在哪一場」這一類，
由那一包經 Game 的委派回答）；三、過渡（別的功能還沒搬的方法，標主人：主人搬成包時改成那一包的查詢服務、或拿掉）；四、寄放
（包放在 Game 上的暫時旗標）。每一包只用自己用得到的那幾個；`tests/core/test_feature_boundaries.py` 照這一份放行。

## 一、共用服務

狀態與時刻
- `ctx.state`（GameState：`state.player`、`state.world`）、`ctx.content`、`ctx.world`（WorldStateStore）、`ctx.now`、`ctx.rng`、`ctx.client`
- `ctx.pill_now()`、`ctx._pill_day()`：回體丹那一套的現實時間與「第幾天」（台灣 00:00 換日）
- `ctx.stamp(t)`：寫給玩家看的時刻（calendar.stamp_text）
- `ctx.touched`：這一下動到的別人的名號（伺服器叫他們的分頁重抓）

記錄與存回
- `ctx._log(msgs)`：這一下的回話；`ctx._write(title, lines, tag=...)`：寫一則江湖紀錄；`ctx._guide(...)`：引導那一框
- `ctx._outcome(tag, line)`：這一下那一則江湖紀錄的結果那一格；`ctx._draft`：這一下的那一則（choose 建的 Draft，例：出陣回報掛在 front）
- `ctx._save_season()`：把這一次動到的季寫回共用賽季；`ctx._reconcile_season()`：重讀共用賽季
- `ctx._cost_option(id, label, stamina)`：花體力的選項（鈕上寫體力）

戰報（出陣第 1 批加的；打一場的包都要）
# battle（主動搬六包第 5 批：單打服務留核心、列進這一段，PM 10/31 定）
- `ctx.battle_card()`、`ctx.battle_list()`、`ctx.battle_detail(record_id)`、`ctx.shows_battle_card()`：戰報（「剛剛」那張卡片、戰報頁的列表與
  那一筆；決戰的戰局條要問「剛剛」那張卡片是不是一場決戰）
- `ctx._record_exp(record, exp, source)`：本人的經驗寫進戰報（滿級換心得）；`ctx._file_battle(record, ...)`：存戰報、回那一行
- `ctx._play_rounds(record, squad, tier, ...)`：排回合的演出；`ctx._deed_fame(kind)`：立功給名望
- `ctx._load_kin(name)`、`ctx._save_kin(game)`：同一把鎖裡讀、寫別人的存檔（混戰、截殺）
# battle（全部拆包第 7 批：集結、投效、挑同伴加入那一刻快照的份量；總表歸核心「戰力快照」）：這裡原本列的戰力快照 7 個，第 8 批去重——
# 以下面 `# shared` 那一段的「戰力快照」為準（第 16 批合併時 PM 定：第 8 批做；`_battle_scores`、`_battle_power` 測試換掉，包裡經 ctx 叫）
# battle（全部拆包第 8 批：推進與結算；時刻表決戰收場那一下，總表歸核心）
- `ctx._deliver_big_events()`：這一季的時刻表大事人人有份，沒看過的補進自己的江湖紀錄（FB-038；決戰包的時刻表決戰收場之後叫）

店面與戰報的補充（tavern：主動搬六包第 10 批酒肆加的）
- `ctx._shop_say(key, problem=None)`、`ctx._shop_after(problem, done, keyer=None)`：掌櫃那一句（七間店共用，shop_lines.json 的情況）
- `ctx._idle()`：閒著（不在路上、沒在閉關）才進得了店
- `ctx._last_wear`：`_file_battle` 留下的這一場兵器、防具損耗那幾句（接在戰報那一則的後面）

身分
- `ctx._side()`：站哪一軍；`ctx.is_admin()`；`ctx._admin_target(name)`、`ctx._save_target(game)`：管理者動到別人的存檔
- `ctx._quick_client()`：鎖內的模型呼叫（一步最多 in_lock_model_timeout 秒）
# battle（全部拆包第 6 批：管理者的決戰工具）
- `ctx._admin_refusal(action)`：管理者觸發的共同檢查（不是管理者、賽季沒在進行、暫停中回那一句；做得了回 None）——管理者外殼（手冊 3.1，核心）

錢包（3.10：跨包的票經過這裡，不叫商城）
- `ctx.wallet`：WalletService（下面）——`tokens(kind)`、`consume(kind)`、`purchases()`、`card_bonus()`、`item_for(effect)`
- `ctx._wallet()`：商城開著時的 Wallet（資料庫那一側）；關著是 None。`ctx._mall_owner()`：錢包的主人（名號的 casefold）
- `ctx.pill_cap()`、`ctx.pills_left_today()`：回體丹一天的上限（含月卡）與今天還能服幾顆

共用的字與小函式（不是 Game 上的，從這個模組 import）：`PAUSED_TEXT`、`NO_SUCH_PLAYER`、`drill_share`
# battle（全部拆包第 6 批：PM 定的「siege.py 不搬，這一批用到的名字列進共用段、標主人」）
- 共用規則層的名字（不是 Game 上的、也不在這個模組；包直接 import 那個模組）：`siege.title`（攻城戰的名字「攻城・地點」）、
  `siege.settle`（收場那一下改季：易手或守住、進度歸 50、時程表記結果）、`siege.verdict`（誰贏、大勝或險勝）——主人：共用規則層
  （地盤與攻城；總表附錄甲，`tianxia/siege.py` 不搬）。第 11 批開了共用規則層的名單（`tianxia/core/registry.SHARED`），`siege` 登記在上面：
  包 import 它不必註「過渡：待搬」（同一行還有別的舊模組的照註）；其餘的共用規則層模組總表第 15 批登記

選單與分派（explore：主動搬六包第 3＋4 批加的這一段）
- `ctx.options(odds=False, tick=False)`：此刻的選單（走一趟問「探索按不按得下去、這一段端出要選的事沒」）；`ctx.choose(id)`：按一顆
  （走一趟每一段叫一次 act:explore，各寫各的江湖紀錄）。閒著的那一顆是 `tianxia.core.option.IDLE_MARK`

# shared（全部拆包第 15 批「共用規則層登記」：五區調查量好的共用服務一次列進來，總表第六節第 4 條；計畫
# docs/superpowers/plans/2026-11-01-共用規則層登記.md 1.5）。主人都是核心：本體留在 Game 上（第一階 ctx 就是 Game），之後的包直接叫，
# 不必再一個一個加。上面已經列了的照列一次名字（同上）；三、過渡裡寫成別的主人的 12 個（`odds`、`_squad_encounter`、`_pill_find`、
# `_scrap_find`、`_push_progress`、`_conquest_side`、`_spar_power`、`_spar_mirror`、`_raid_key`、`_drill_gains`、`_drills_with`、
# `place_minutes`）照五區調查與總表附錄甲是核心的共用服務，以這一段為準；那幾行第 16 批合進 develop 時去重了（三、過渡留一句記它們原本寫的用法）。
共用規則層的函式怎麼寫（第 6 批的 `siege.title`、`siege.settle`、`siege.verdict` 那一條一起定）：**不列在這張清單**。這張清單只管 Game 上的
`ctx.<名字>`（邊界測試只認這個寫法）；共用規則層有哪些模組看 `tianxia/core/registry.SHARED`，包直接 import 那個模組、不註過渡。
單打服務（戰鬥區；打一場的每一包都用）
- 大場面判讀：`ctx.is_big(squad)`、`ctx._fight_squad(option_id)`、`ctx.fight_request(option_id)`（A 段）、`ctx._checked_fight(option_id, fight)`、
  `ctx._fight_gone(fight)`（C 段的重驗與「選項不在了」）、`ctx._judged(squad)`、`ctx._fight_with(squad, judged, **kw)`、
  `ctx._narrate(record, result, judged)`、`ctx._style_note(squad, result)`、`ctx._terrain_note()`
- 勝算：`ctx.odds(squad_id, at=None)`（鈕上寫的那一個）
- 單次判定與收場：`ctx._squad_encounter(squad_id, wild=False, as_sortie=False)`、`ctx._take_toll(tier, wild=, clash=)`、
  `ctx._player_hp_and_cap()`、`ctx._player_hp()`、`ctx._hp_facts(healed=())`、`ctx._play_rounds(...)`（同上）、`ctx._trait_say(...)`、
  `ctx._trait_lines(...)`、`ctx._record_exp(...)`（同上）、`ctx._battle_rewards(squad, record, max_tier=None)`、`ctx._thin_drops(drops, record)`、
  `ctx._tier3(squad, record, chance, tag, source)`、`ctx._seize(record, draw=False)`（附錄甲裁核心）、`ctx._lose_silver(record)`、`ctx._file_battle(...)`（同上）
- 劇情戰：`ctx._story_squad(squad)`（江湖水漲）
- 戰報：`ctx.battle_card()`、`ctx.battle_list()`、`ctx.battle_detail(record_id)`、`ctx.shows_battle_card()`（同上）、`ctx.battle_card_id()`、
  `ctx.latest_battle_id()`、`ctx.big_battle_ids()`、`ctx.battle_extra_html(for_card=False)`
- 戰力快照（加入決戰那一刻存進 BattleParticipant 的）：`ctx._battle_power(seal=True)`、`ctx._battle_scores(mounted=True, seal=True)`、
  `ctx._battle_role()`、`ctx._battle_mount()`、`ctx._battle_troops()`、`ctx._battle_gear()`、`ctx._battle_marks()`、`ctx._battle_road()`、
  `ctx._battle_neili_cap()`（`_seal_bare` 附錄甲裁給玉璽，不在這裡）
店面殼、修練頁紀錄、線索（武學與成長＋裝備區）
- 店面殼（七間店共用）：`ctx._shop_say(...)`、`ctx._shop_after(...)`（同上）、`ctx._shop_open()`（哪一間店開著）、
  `ctx._shop_live(option_ids=None, shop="smith")`（那一串是不是眼前的選單）、`ctx.shop_view(option_ids=None)`（店面的畫面資料）
- 修練頁紀錄：`ctx._xinde()`、`ctx._menxia_entry(tag, xinde_before, ...)`（修練頁、煉製頁的動作寫進江湖紀錄，同一種連續的併成一則）
- 線索（口訣、殘譜、鑄譜、秘方）：`ctx._tale_clue(event)`、`ctx._scrap_find()`、`ctx._forge_clue(source, seed)`、`ctx._overhear(companion_id, msgs)`、
  `ctx._solved_secrets()`、`ctx._note_solved(before)`；素材與經濟的一天 `ctx.econ_day()`；探索那一行悟意境被拿掉的原因 `ctx._insight_blocked(loc)`
地點（大勢人物＋地圖區；總表附錄甲裁核心）
- `ctx.place_minutes(loc_id)`（走到那裡要現實幾分鐘）、`ctx._figures_here()`（這個地點的大勢人物：核心的選單也叫）
回體丹、醫館、地盤、本人對本人、操練的得、閒著（行動與地盤＋散人區）
- 回體丹與體力：`ctx.pill_now()`、`ctx._pill_day()`、`ctx.pill_cap()`、`ctx.pills_left_today()`、`ctx._cost_option(...)`（同上）、`ctx._day_of(t)`、
  `ctx._pill_card_bonus()`、`ctx.take_stamina_pill(pill_only=False)`、`ctx._refill_stamina()`、`ctx._top_up_pills()`、`ctx._action_costs()`（各行動花的體力）、
  `ctx._pill_find(rng)`、`ctx._stamina_play_options()`（設伏、屯糧那一串；附錄甲裁核心，留作接縫）
- 醫館：`ctx._heal_option()`、`ctx._heal_msgs()`、`ctx.heal()`、`ctx.heal_button()`、`ctx._at_clinic_town()`（附錄甲裁核心：店面與打點都問）
- 地盤：`ctx._push_progress(loc_id, nominal, source, how=None)`、`ctx._event_progress()`、`ctx._conquest_side()`、`ctx._at_own_base()`
- 本人對本人：`ctx._spar_power(who, against, seal=True)`、`ctx._spar_mirror(result, power)`、`ctx._raid_key(attacker, target)`
- 操練的得：`ctx._drill_gains(squad, share=None, source="hold", echo=True)`、`ctx._exp_changes(exp, keep, gained)`、`ctx._drills_with(squad)`
- 閒著：`ctx._idle()`（同上）、`ctx.is_idle()`（切磋、論武問的那一個）
名聲（總表附錄甲：名聲服務是核心，`_log` 每一下都叫）
- `ctx._deed_fame(kind)`（同上）、`ctx._renown_after(synced=False, fresh=None)`、`ctx._deliver_echoes()`（首創名望回饋）、`ctx._famed_news(place, foe, tier)`
# core-events（全部拆包第 16 批：事件檢定搬進核心本體 tianxia/core/event_check.py，Game 留一行委派）
事件檢定（核心本體）
- `ctx._present(event, action)`：把一則事件端到眼前（action 是抽中它的行動：記進防重複的輪替、人物心意；記看過、寫那一則的結果標記與
  場景那一句、片段事件的伏筆）。探索包抽到事件時叫。三、過渡 explore 那一段原本也列了它（主人寫「事件」）：主人現在是核心本體，
  第 16 批合進 develop 時去重、只留這一行
# guide（全部拆包第 22 批「引導一」；計畫 docs/superpowers/plans/2026-11-01-新手引導包-第1批.md 1.3、1.4）
新手引導（主人：新手引導包，Game 上一行的委派；很多包在叫，派工單定列在共用段）
- `ctx._check_hints()`：做完一件事看一遍碰到才說（新手目標發獎勵、該說的排一條、輪到的上框；記在這一則紀錄的引導那幾行）
- `ctx._hint(hint_id)`：碰到某個玩法、排一條提示（事件型的：被名將打發、玉璽碎片的秘密揭開、第一次交友或談話、操練練完）
- `ctx._note_action(action)`：做完一個行動，引導（說書人的步驟、入伍段）看這一步完成了沒，回那幾行（交給 `ctx._guide`）——出陣包的
  「出一次力」叫它（原本 import `tianxia.guide.note_action`：包 import 包）；本體叫 engine 模組層的 `note_action`（測試換的是那個名字）
- 核心的：`ctx._preparing()`（籌備中）、`ctx._journal_guide(notes)`（引導的話記進這一則江湖紀錄的引導那幾行）、`ctx._free_text_of(event)`
  （這一則事件有沒有隨口應對：事件檢定的委派）
- 共用的字：`HutReward`（序章步驟的獎勵那一行的記號，核心的 `_guide` 認它；原本在 `tianxia/guide.py`，搬到這個模組，引導包 re-export）

# sortie（全部拆包第 17 批「出陣三」：舊遊歷、操練、守勢、遊歷推大勢搬進出陣包要叫的；主人都是核心，總表附錄乙 final_owner.json）
推大勢（玩家自己造成的大勢推動一律走這裡）
- `ctx.push_trend(trend_id, delta, source=)`（人數緩衝、每人每日上限、貢獻、季長縮放與盡頭阻力）、`ctx._goals()`（自己那一邊各線的目標方向）、
  `ctx.season_scale()`（季長倍數）、`ctx._carry(trend_id, amount)`（不足一點的零頭記進全服的 trend_accum，回滿了的整數）、
  `ctx._push_room(trend_id)`（今天在這條線上還推得動多少；第一季規則關著是無限）
- 共用的字：`BIG_FIGHT_WAIT`（大場面按下去、等模型判讀時按鈕上的字；事件的戰鬥選項、挑戰本人、遊歷與出陣都用，從這個模組 import）

## 二、查詢服務

# battle（主動搬六包第 5 批；主人：決戰包。本體還在 Game——「打」那一半，第 6～8 批搬——決戰包「看」那一半經 ctx 叫；搬完由決戰包經
# Game 的委派回答別的包）
- `ctx._battle_for_me(tick)`：場景上畫著的那一場（戰鬥, 定義），序章裡、沒有是 None；tick 照原位（畫面是 False、放手一搏送出是 True：
  一次請求只推進一次）。`ctx._battle_now()`：此刻自己參戰（或看）的那一場（酒肆也在用：殺手不找決戰裡的人；酒肆第 10 批在三、過渡
  也記了一行，第 11 批去重，留這一行）。第 8 批兩個本體搬進 `features/battle/progress.py`、決戰包裡直接叫；酒肆包、形象包、核心的
  事件檢定照舊經 Game 的委派問
- `ctx._definition_of(battle)`（那一場的定義：攻城戰是「攻城・地點」）
- `ctx._watching_battle(battle, definition)`（此刻只能在一旁看）、`ctx._free_agent(definition)`（散人、豪強：只能臨時投效；本體第 7 批搬進
  `features/battle/muster.py`，決戰包裡直接叫，別的包問它叫 Game 的委派）。（第 7 批：決戰的大區叫什麼、還沒到戰場的原因、臨時投效的人
  打完照樣是誰三個本體搬進 `muster.py`、只有決戰包裡叫，Game 上不留，從這裡拿掉）
# battle（全部拆包第 6 批）
- `ctx._definition_of` 的本體搬進了包（`features/battle/sieges.py`），包裡照樣經 ctx 叫（測試直接叫 `Game._definition_of`）；
  `ctx._sieges()`（還沒收場的攻城戰，照開集結的先後；這一季沒開領地爭奪是空的、不讀資料庫）——本體也在 `sieges.py`，核心原位叫委派，
  別的包問「此刻有沒有攻城」叫它
# battle（全部拆包第 7 批）
- `ctx.battle_now()`（這個人看的那一場，同 `_battle_now`；假人的分數讀它，決戰包的 `bots.py`）
# battle（全部拆包第 8 批）
- `ctx._round_mvp(battle, resolve)`（主人：形象包；決戰包推一回合時包著回合結算叫：結算完挑回合首功、回合紀錄多一行。決戰包不 import 形象包）
- 上面那一行的 `ctx._watching_battle` 第 8 批本體搬進 `features/battle/progress.py`、決戰包裡改直接叫，清單上照舊留著：Game 上的委派
  回答別的包（Game 原位的 options、引導的 `_hint_triggers`；第 22 批把 `_hint_triggers` 搬進引導包之後，引導包經 ctx 問它。審查：拿掉的話
  兩條線合起來 git 不報衝突、邊界測試卻紅）

explore（主動搬六包第 3＋4 批加的這一段）
- `ctx._outing_on()`（主人 explore：減法季探索一顆開著、不在序章裡；出陣包問——散人那一行、出陣的字；出陣第 1 批原本列在
  三、過渡，審查修正拿掉了，只在這一段）
- `ctx._sortie_host(loc)`（主人 sortie：這一處自家的那一路；探索一顆在自家營寨跟同袍比劃問）

# looks（主人：形象包）
- `ctx._battle_ult()`：放手一搏送出那一刻身上的絕招（move、name、look、weapon；沒穿、沒有導演稿是 None）。決戰包送出放手一搏時記進
  `BattleRound.ults`，回合首功從這裡挑（Joy 2026-11-03；純展示，不動數字）

# guide（全部拆包第 22 批：新手引導包問別的包）
- `ctx._at_battle(definition)`（主人決戰：人到了決戰的大區沒；碰到才說的 h_spectator）
- `ctx._tavern_on()`、`ctx._tavern_here()`、`ctx._tavern_at(loc_id)`（主人酒肆：酒肆開著沒、人此刻在酒肆、這個地點有沒有酒肆；碰到才說的
  h_tavern、新手目標「去酒肆」指哪幾處。Game 上一行的委派叫 `tavern_rules.on`／`here`／`tavern_at`——原本 `_hint_triggers`、`_newbie_go`
  直接讀酒肆的那兩筆 `GAME_DIRECT` 換成它們）

# bout（全部拆包第 12 批；主人：單挑包。本體在 tianxia/features/bout/，Game 留一行委派回答別的包）
- `ctx._boss_ready()`（此刻在這裡遇得上的頭目：不在序章、沒在打、不在冷卻、這一隻的次數還沒用完；沒有是 None）、`ctx._boss_face(boss)`
  （這一隻對你露的那一面的名字，照陣營）、`ctx._duel_start(boss)`（撞上頭目、開打）：探索包的出門一趟撞上頭目時問。原本列在三、過渡
  explore 那一段（主人寫頭目戰，`_boss_ready` 那時是探索包直接 import `tianxia.duel` 叫 `available`），單挑成包時照總表第六節第 4 條改成查詢服務
- `ctx.arena_look()`、`ctx.arena_move()`（主人：形象包）：擂台報名、開打那一刻記這個人穿哪一套、出招疊哪一張光效（擂台搬進單挑包之後由包經 ctx
  問；`tianxia/features/bout/tests/test_arena.py` 換掉 `Game.arena_look`）

## 三、過渡（別的功能還沒搬的方法；括號是主人）

explore（主動搬六包第 3＋4 批加的這一段）
- `ctx._home_gather(loc, mids)`、`ctx._sense_here(loc, rng)`、`ctx._wild_foes(loc)`、`ctx._practice_tier(loc)`
  （探索三選一：企劃者 10/31 定不搬、留在 engine——批次表第 9 批不做，三選一整套拿掉之前一直掛在 Game 上；`_boss_face` 第 12 批改成二、查詢服務）
- `ctx._story_begin(strand)`（一條線；`_duel_start` 第 12 批改成二、查詢服務）
- 收尾的掉落：`ctx._legend_find(rng)`（破境丹）、`ctx._seal_find(loc_id)`（玉璽碎片）——照原本的順序在原位叫，不收成事件（同一串的
  回體丹 `_pill_find`、殘譜 `_scrap_find` 在一、共用服務）
- `ctx._outing_plan(loc)`、`ctx.outing_plan()`（探索包自己的委派：測試換掉 game._outing_plan 之後按探索，包裡經 ctx 叫，換掉的才打得到；
  呼叫端改完就拿掉）
（第 16 批合進 develop 時去重：這一段原本還列了 `_present`（主人是核心本體，見一、共用服務 `# core-events`）與 `odds`（勝算：鈕上寫的
同一個；測試換掉 game.odds）、`_drills_with`（那一路是不是自己這一邊）、`_pill_find`、`_scrap_find`、`_squad_encounter`（wild=True：探索一顆的
遭遇那一場，扣氣血減半、不問模型、不推大勢）——以一、共用服務 `# shared` 那一段為準。）

（原本這裡還有 `_train_option`、`_train_pick`、`_big_trip`：舊遊歷的鈕與大場面挑哪一路，第 17 批搬進同一包，包裡直接叫 train_actions，拿掉了。）
# battle（主動搬六包第 5 批；擺在這兩行之間：別條拆包線與 develop 改的是段頭、_order_credit、_outing_on 以下與段尾，不跟它們貼在一起）
- （`_mutate_battle_of`：改共用狀態裡的那一場——第 8 批本體搬進 `features/battle/progress.py`、包裡直接叫，從這裡拿掉。第 7 批：
  放手一搏送出、隨你出陣的同伴回江湖兩個本體搬進 `muster.py`、包裡直接叫，從這裡拿掉）
- `ctx._four_wins()`（三陣營四勝利：這一季開著沒；決戰的軍餉記不記豪強的貢獻）
# battle（全部拆包第 6 批：管理者的決戰工具、攻城）
- `ctx._apply_battle_outcome(battle)`（收場套結果：第 8 批本體搬進 `features/battle/progress.py`，包裡照舊經 ctx 叫——測試換掉
  `Game._apply_battle_outcome`〔test_server〕。同一行原本的 `_shelve_unfinished_battle`、`_advance_battle_round`、`_highlight_line`、`_merit_line`
  第 8 批搬進 `progress.py`、包裡直接叫，從這裡拿掉）
- `ctx._timetable_event(event_id)`、`ctx._timetable_refusal(action)`（時刻表：這一季的那一件、時刻表類管理者動作的共同檢查；主人大勢人物與賽季）
- `ctx.admin_battles()`、`ctx.admin_start_battle(battle_id, now)`、`ctx.cancelled_showdowns()`、`ctx._deliver_battle_results()`（決戰包自己的
  委派：測試直接叫〔前三個〕或換掉〔`Game._deliver_battle_results`，test_renown_cross〕，包裡經 ctx 叫才打得到；呼叫端改完就拿掉）
# battle（全部拆包第 7 批：集結、投效、挑同伴）
- `ctx._battle_status(tick)`（測試換掉、數它被叫幾次〔test_engine、test_hints〕：第 8 批本體搬進 `features/battle/progress.py`，包裡照舊經 ctx 叫。
  同一行原本的 `_mutate_battle_now`、`battles_now` 第 8 批搬進 `progress.py`、包裡直接叫，從這裡拿掉）
- `ctx._mandate_weight(definition, scores)`（天命之爭手上有碎片的人份量加權；主人：玉璽，總表裁定這一批留原位）。（同一行原本的
  `_backfill_battle_scores` 第 8 批搬進 `progress.py`〔PM 11/03 從第 12 批挪來〕、包裡直接叫，從這裡拿掉）
# battle（全部拆包第 8 批：推進與結算；主人：玉璽，總表附錄甲）
- `ctx._seal_bare()`（補份量快照時不含碎片的那一份）、`ctx._seal_settle(battle, definition, result)`（時刻表決戰收場：先挑挑戰者、再挑現世的得主）、
  `ctx._deliver_seal_results()`（玉璽碎片的事補送到自己手上）
- `ctx._order_credit(...)`（軍令；出陣約戰結算時也叫在攻方、應戰的人那兩份 Game 上——包裡的變數名 attacker、defender，邊界測試照樣掃）
（第 16 批合進 develop 時去重：這一段原本還列了出陣包用的 `_squad_encounter`（as_sortie=True：打一場隊伍，出陣攻打）、`_push_progress`
（地盤：領地爭奪推、拉進度）、`_drill_gains`（操練）、`_spar_power`、`_spar_mirror`（切磋：本人對本人的威力、從另一邊看同一場）、
`_raid_key`（截殺與混戰共用的冷卻帳 WorldState.raids 的鍵）、`_conquest_side`（領地爭奪算哪一邊；出陣約戰用）、`place_minutes`（出陣約戰卡上
別區的「前往 N 分」）；後面三個出陣第 1 批審查從共用段搬到這裡，第 15 批照五區調查與總表附錄甲裁回核心的共用服務——以一、共用服務
`# shared` 那一段為準。）
- `ctx.sorties_left()`、`ctx._sortie_hold(loc, how)`（出陣包自己的委派：測試換掉 Game.sorties_left〔test_bot_policy_conquest〕、
  腳本換掉 Game._sortie_hold〔sim_trend_sources〕，包裡經 ctx 叫，換掉的才打得到；呼叫端改完就拿掉）
（原本這裡還有 `duel_on`、`_duel_option`：第 1 批替出陣約戰留的；第 2 批約戰搬進同一包，包裡直接叫 duel_actions，拿掉了。）

（酒肆第 10 批在這裡記的 `_battle_now` 第 11 批去重：只留二、查詢服務那一行。）

core-seams（全部拆包第 11 批「核心收接縫」：新的接縫掛鉤裡包要叫回 Game 的）
（原本這裡還有 `_train_squad_ids`：出陣包行動列那一格的序章雪恥，第 17 批舊遊歷與出陣共用的對手池搬進同一包，包裡直接叫，拿掉了。）
- （`_fighting`：決戰包蓋在畫面上的戰場要不要整個取代自己眼前的事——第 8 批本體搬進 `features/battle/progress.py`、`scene_over` 掛鉤直接叫，
  從這裡拿掉；Game 上的委派留給 options）

# sortie（全部拆包第 17 批「出陣三」）
- `ctx._parley_backing_here()`（並肩出陣：今天答應陪你、你在他那一帶的那位人物；act:train 打的那一場包在外面；主人人物情誼〔總表第 19～20 批〕）
- `ctx._train()`、`ctx._sortie()`、`ctx.train_trend_push(loc_id=None)`、`ctx._train_push(trend_id, delta)`（出陣包自己的委派：
  tests/figures/test_parley_two.py 換掉實例上的 `_train`、`_sortie`，tests/core/test_explain.py 換掉 `Game.train_trend_push`，
  scripts/sim_trend_sources.py 換掉 `Game._train_push`——包裡經 ctx 叫，換掉的才打得到；呼叫端改完就拿掉）

# guide（全部拆包第 22 批：新手引導包叫的、主人還沒搬的）
- `ctx._recruit_target()`、`ctx._recruitable_here()`（主人同伴 features/companions：碰到才說的 h_recruit）
- 假人走序章（`_graduate`）照每一步的完成條件做的那幾下：`ctx.slot_insight(art, insight)`、`ctx.switch_art(art)`、`ctx.practice(kind)`、
  `ctx.allocate_stat(stat)`、`ctx.melt_art(art)`（主人武學 features/arts）、`ctx.forge(main, aux)`（主人煉製 features/craft）
- `ctx._hint_triggers(only)`（這一包自己的委派：tests/arts/test_hints.py 換掉 game._hint_triggers，包裡經 ctx 叫，換掉的才打得到；
  呼叫端改完就拿掉）

# bout（全部拆包第 12 批：單挑包自己的委派，被測試或腳本換掉的，包裡經 ctx 叫才打得到；呼叫端改完就拿掉）
- `ctx._arena_bare()`（擂台挑人的身手不含玉璽碎片的那一份；`tests/seal/test_seal_revamp_hidden.py` 換掉 `Game._arena_bare`）、
  `ctx._duel_finish(tier, line)`（頭目戰收場；`scripts/sim_season_one.py` 換掉 `Game._duel_finish` 數頭目戰打成怎樣）

## 四、寄放（包放在 Game 上的屬性；包外的呼叫端與測試還在 Game 上讀寫；那一包的線再碰到時搬走）

explore（主動搬六包第 3＋4 批加的這一段；都是 Game.__init__ 起的）
- `ctx._beat`（走一趟：剛剛那一次探索抽到什麼——探索一顆寫、走一趟讀）、`ctx._outing_close`、`ctx._outing_upset`（探索一顆：這一趟打了折的閘、
  這一場開打前勝算凶險以下）、`ctx._outing_busy`（走一趟正在走、正在記一件事選完的得失：engine 模組層的 `_outing_watch` 套在 choose、
  answer_event、epiphany_names、sense_draw 上，看它不再套一層）
- `ctx._loot_scale`、`ctx._drop_scale`、`ctx._gate_scale`（遭遇那一場的戰利、掉落、經驗倍數：探索一顆的遭遇設、核心 `_battle_rewards` 讀；
  三選一的 `_practice` 也寫 `_loot_scale`）

- `ctx.mall_bought`、`ctx.mall_already`（商城）：上一次 actions.buy 的結果（買成的商品 id；同一個編號早就買好的那一件），伺服器在鎖裡讀
- `ctx._clash_won`、`ctx._sortie_marked`、`ctx._sortie_moved`、`ctx._sortie_flipped`（出陣）：Game.__init__ 起的、出陣那一下設、
  `_push_progress`（地盤，留在核心）寫與讀——混戰得勝的加成、記過一筆出陣沒、這一下推（拉）動了多少、推滿易手了沒（出陣回報讀）

# battle（全部拆包第 7 批：Game.__init__ 起的，核心的 _battle_now〔第 8 批〕也讀 _battle_ref）
- `ctx._battle_ref`（這一下按的鈕指定的那一場：加入鈕帶 @流水號）、`ctx._escort_picked`、`ctx._escort_now`（挑好了同伴、正要加入的那一下：
  戰力快照照它帶那一位）

tavern（主動搬六包第 10 批酒肆加的這一段；擺在段尾，理由同上）
- `ctx._tavern_seek_exact`、`ctx._tavern_reply`：查人那一下問得多清楚（託酒家留意看它；None 沒查成、True 確切地點、False 沒問清楚）、
  問酒家 B 段寫好的那一句（tavern_ask 放、問完清掉）

不在清單上的：`Game` 其餘一千多個方法都是還沒搬的功能自己的，功能包碰了就是跨包（手冊 3.4 第 1 條）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import Content
from ..wallet import Purchase, Wallet

if TYPE_CHECKING:
    from ..engine import Game

# 共用的字（原本寫在 engine.py；功能包要用、又不能 import engine，搬到這裡，engine 照舊叫得到）
PAUSED_TEXT = "賽季暫停中（停機維護）：這段時間不能行動，畫面照常可看"
NO_SUCH_PLAYER = "（江湖上沒有「{name}」這個人。）"  # 管理者查不到名號（玩家個人劇情、商城查帳；只有管理者看得到）
# sortie（全部拆包第 17 批：原本寫在 engine.py；出陣包的遊歷鈕要用、又不能 import engine，搬到這裡，engine 照舊叫得到）
BIG_FIGHT_WAIT = "兩人對峙……"  # 大場面按下去、等模型判讀時按鈕上的字（武學與成長設計 8.3）


# guide（全部拆包第 22 批）：原本寫在 tianxia/guide.py；核心的 Game._guide、_menxia_entry 照它把序章步驟的獎勵（這一下的結果）跟對話框
# 那幾行分開，新手引導包產生它——核心不能 import 包，型別搬到這裡，引導包（tianxia.guide.HutReward 照舊是同一個類別）re-export
class HutReward(str):
    """序章步驟的獎勵那一行（出師的盤纏）：不進對話框，當這次行動的結果寫進「剛剛」（Game._guide 認這個型別，T7 審查 M4）。"""


def drill_share(amount: int, share: float) -> int:
    """跟自己人操練拿對手那一項獎勵的幾成（Config.drill_reward_share），四捨五入（round 是銀行家進位）。
    操練真的給的（出陣包 train_actions.drill）與行動列底下說會給什麼（train_actions.train_line）都算這一個；出陣的守與打贏（出陣包）、探索也用。
    （原本寫在 engine.py；出陣包要用、又不能 import engine，搬到這裡，`from tianxia.engine import drill_share` 照舊拿得到。）"""
    return int(amount * share + 0.5)


CARD_KEY = "pill_cap"  # 月卡記在 mall_entitlements 的哪一格（回體丹每天的上限）


def wallet_on(content: Content) -> bool:
    """錢包開著沒（＝商城開著，Config.mall.enabled）：關著時不讀不寫三張表、月卡不加上限、沒有票。"""
    return content.config.mall.enabled


def tokens(wallet: Wallet, owner: str, effect: str, season: int | None = None) -> list[int]:
    """帶著 effect（zhuan_rewrite、rename、列傳的四件、題壁墨）還沒用掉的那幾筆購買（id，舊的在前）：沒退、data 裡沒有 used。每一筆是一次。
    season 給了只算那一季買的（列傳的票綁買的那一季，減法季批 7b、FB-845）。"""
    return [b.id for b in reversed(wallet.purchases(owner)) if b.refunded is None and b.data.get(effect) and not b.data.get("used")
            and (season is None or b.season == season)]


def look_ids(wallet: Wallet, owner: str) -> list[str]:
    """這個人買到的擂台形象（購買那一列 data 的 look_id；沒退的，舊的在前、不重複）：帳號的，換季也帶著走（Joy 2026-10-31
    「花錢買的東西不能不見」）。商城包（買過了不再賣）與形象包（穿哪一套）都照它。"""
    seen: list[str] = []
    for b in reversed(wallet.purchases(owner)):
        look = b.data.get("look_id")
        if b.refunded is None and look and look not in seen:
            seen.append(look)
    return seen


def card_bonus(content: Content, wallet: Wallet, owner: str, day: int) -> int:
    """月卡（商城架構設計 4.5）：day 這一天在卡的期間裡（開始日～到期日，不含到期日）就回 Config.mall.card_pill_bonus，其餘 0。"""
    if not wallet_on(content):
        return 0
    span = wallet.card(owner, CARD_KEY)
    return content.config.mall.card_pill_bonus if span is not None and span[0] <= day < span[1] else 0


def item_for(content: Content, effect: str) -> str | None:
    """賣這一種效果的第一件商品（照 content/mall.json 的順序；「去萬寶閣」那一顆停在這一件）；商城關著或沒賣是 None。"""
    if not wallet_on(content):
        return None
    return next((item.id for item in content.mall.values() if item.effects.get(effect)), None)


class WalletService:
    """ctx.wallet：這個人的錢包，只做票的庫存與消耗、月卡加的上限、哪一件商品賣這種效果（3.10）。
    商城關著（ctx._wallet() 是 None）時庫存是空的、消耗什麼都不做、上限不加、沒有商品。賣與記帳是商城包的事。"""

    def __init__(self, game: Game) -> None:
        self._game = game

    def tokens(self, kind: str, bought_in: int | None = None) -> list[int]:
        """手上還沒用掉的 kind 票（購買 id，舊的在前）；bought_in 給了只算那一季買的。"""
        wallet = self._game._wallet()
        return [] if wallet is None else tokens(wallet, self._game._mall_owner(), kind, bought_in)

    def consume(self, kind: str, *, bought_in: int | None = None, at: float | None = None, **marks) -> int | None:
        """用掉最舊的一張 kind 票：那一列的 data 記 used（＝at，不給是回體丹那一套的現實時間 pill_now）與 marks；回那一張的購買 id，
        沒有票回 None、什麼都不寫。"""
        left = self.tokens(kind, bought_in)
        if not left:
            return None
        self._game._wallet().mark_used(left[0], self._game.pill_now() if at is None else at, **marks)
        return left[0]

    def purchases(self) -> list[Purchase]:
        """這個人全部的購買（新的在前；列傳那幾張票照已經讀好的這一份數，zhuan_end.season_tickets）；商城關著是空的。"""
        wallet = self._game._wallet()
        return [] if wallet is None else wallet.purchases(self._game._mall_owner())

    def card_bonus(self) -> int:
        """今天月卡讓回體丹上限多幾顆（Game.pill_cap 與體力條的說明都讀這一份）；沒有卡、商城關著是 0。"""
        wallet = self._game._wallet()
        return 0 if wallet is None else card_bonus(self._game.content, wallet, self._game._mall_owner(), self._game._pill_day())

    def item_for(self, effect: str) -> str | None:
        return item_for(self._game.content, effect)
