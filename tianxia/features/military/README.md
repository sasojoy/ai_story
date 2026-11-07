# 軍情（`tianxia/features/military/`）

- 做什麼：軍令卡（江湖頁「本週軍令」）與押糧（接下糧車、走到終點交軍令）、第 2 階行動、第 3／4 階行動（黃巾煽動起事、豪強修築塢堡與趁亂占據郡縣）、第 4 階席次的抄帳、
  管理者重發軍令／輪替席次／替人發召見。全部拆包第 33 批從 `Game` 搬來（17 個方法）；包名不叫 `orders`：`tianxia/orders.py`（軍令的規則）留在原位。
- 第 34 批加進來：**機緣**（情誼、累積、天時地利、拼圖、推理、集體密謀六種；`opp:` 前綴；`tianxia/opportunities.py` 搬來）與**伏筆**（聽片段、對話片段、最後一步、
  官銀、天機；`fs:` 前綴；`tianxia/foreshadow.py` 搬來），再加 5 個 `Game` 方法（`_settle_plots`、`_hear_after_stamina`、`admin_give_opportunity`、`admin_give_fragment`；
  `_foreshadow` 接 `choose` 掛鉤後沒人叫了，不留）。
- 導覽：`docs/guide/大勢人物與賽季.md` 的軍令與晉升那幾節
- 設計稿：`docs/superpowers/specs/2026-10-04-第一季陣營內容-軍令.md`、第一季正式版計畫戊（第 3、4 階行動）、丁（第 4 階席次）

## 檔案

| 檔 | 內容 |
|---|---|
| `__init__.py` | 登記：前綴 `opp`、`fs`（行動列的 `act:` 前綴是核心的）；認領 18 個欄位；掛鉤：`choose`（`opp:`、`fs:`，標題隨 `Outcome.title`）、`bot_pick`（都不按）、`defection()`（`clear` 的 `convoy`〔第 32 批〕與 `opportunities`、`leave` 的 `plots`）、`effects()`（`grain`、`fs_fragments`、`foreshadow` 三格，第 34 批） |
| `order_actions.py` | 軍令卡與記功 4 個：`order_options`（守勢與接糧車的選單）、`order_credit`（替自己記一次軍令）、`convoy_line`、`orders_view`（江湖頁「本週軍令」卡） |
| `order_cards.py` | 軍令卡上怎麼出力那一行與它的字（`order_how`、`siege_how`、`strike_how` 與 17 個常數，第二輪第 97 批從 `atlas` 搬來；`_strike_place` 輿圖包也讀，留 `atlas`） |
| `convoy_actions.py` | 押糧 2 個：`take_convoy`、`convoy_arrives`（走到終點：可能撞上截糧隊、記捐獻與貢獻、軍令記功）；叛投 `clear` 位置的 `convoy` 那一格 `defect_clear`（第 32 批） |
| `step_actions.py` | 第 2 階與第 3、4 階行動 6 個：`rank2_options`、`check_cost_note`、`rank2`、`rank_action_options`、`rank_action_line`、`rank_action` |
| `seat_actions.py` | 第四階席次抄帳：`report_seat`（賽季時鐘暫停中什麼都不做） |
| `admin_actions.py` | 管理者的軍令與召見：`issue_orders`、`rotate_seats`、`summons_plan`、`summon`，與回話用的五個常數 |
| `rank_rules.py` | 第 3、4 階行動的規則（原 `tianxia/rank_actions.py`，舊名留成指到同一個模組的別名） |
| `opp_rules.py` | 機緣的規則（原 `tianxia/opportunities.py`，舊名是別名）：六種機緣、閒著的選單、`act`（`opp:` 按下去）、第 2 階行動、密謀、線索、對話話題、叛投清進度 |
| `fs_rules.py` | 伏筆的規則（原 `tianxia/foreshadow.py`，舊名是別名）：聽片段、對話片段、最後一步、答題、官銀、天機、效果三格 |
| `opp_actions.py` | 機緣的動作：`settle_plots`、`give_opportunity`，與核心原位要問機緣的委派本體（選單、打贏記一處、第 2 階行動名字、管理頁選單、對話話題、之後記次數）；`HEARD_TITLE` |
| `fs_actions.py` | 伏筆的動作：`foreshadow`（`fs:` 按下去）、`hear_after_stamina`（伏筆先、機緣後）、`give_fragment`，與核心原位要問伏筆的委派本體（答題選單與場景、閒著的選單、打贏官銀、事件片段、對話片段、管理頁選單） |
| `bots.py` | 假人看到 `opp:`、`fs:` 都不按；第 2 階行動、接下糧車、應召的分數（第 60 批，`Verb.bot`，常數同值） |

`Game` 上的名字掛在 `game_api.py` 的表（第 33 批）：`_order_options`、`_rank2_options`、`_rank_action_options`、`_rank2`、`_rank_action`、`_take_convoy`、`_convoy_arrives`、`_order_credit`、
`_report_seat`、`_summons_plan`、`orders_view`、`convoy_line`、`admin_issue_orders`、`admin_rotate_seats`、`admin_summon`；`_check_cost_note`、`_rank_action_line` 只有包裡自己叫，沒有委派。
第 26 批（事件機制）拿掉 `_convoy_arrives`（抵達那一刻改由這一包登記事件 `arrive` 的 `convoy` 那一格，見下面「事件的格」），剩 14 個。
第 34 批再留 16 個：`_settle_plots`、`_hear_after_stamina`、`admin_give_opportunity`、`admin_give_fragment`（原本就有的）與新增的 `_fs_asking_options`、`_omen_options`、`_rank2_action`、`_fs_after_win`、`_opp_on_win`、`_admin_omen_choices`、`_hear_from_event`（事件檢定經 `ctx` 叫）、`_omen_talk_options`、`_fs_hear_talk`、`_opp_hear_topic`、`_opp_after_success`（後四個是人物情誼包、出陣包經 `ctx` 問的查詢服務）。

## 認領的欄位（`PlayerState`，換季全部跟著新角色重來，沒有帶走的）

`convoy`（押著的糧車；這一包寫，叛投那一刻也由這一包清成 None）、`rank2_days`（第 2 階行動今天做了幾次）、`rank_action_weeks`（第 3、4 階行動這週做了幾次；`rank_rules.count` 寫）。
第 34 批再認領 15 個：伏筆 7 個（`fragments`、`clue_items`、`fs_counters`、`fs_done`、`fs_cooldown_until`、`fs_asking`、`fs_asked`）、機緣 8 個（`opp_done`、`opp_counts`、`opp_items`、`opp_fronts`、`opp_clues`、`opp_tried`、`opp_pieces`、`opp_settled`）。叛投時 `opportunities` 那一格清掉機緣的進度，但 `opp_clues`、`opp_settled`、`fragments` 留著（企劃者裁決 E5.2：知道的事；結算過的密謀不會因為叛投再結算一次）。全服的集體密謀 `world.plots` 是共用賽季，不是 `PlayerState`，不認領。
包外直接讀 `fs_asking` 的：共用規則層的 `atlas.travel_block`（正在答話，先作罷才能安排前往）第 50 批改問核心的 `omen_base.fs_answering`（`fs_rules` re-export 同一個函式）；`engine.py` 兩處（選單換成答題的那幾顆、條件裡的「不在答題中」）照舊直接讀，交 PM 排批。
`donations`（押糧與捐糧效果都寫）、`summons`、`qualified`、`rank`、`contrib_weeks`、`rank_hinted`、`patron` 是共用或階級、席次規則層的，不認領。

## 還留在核心原位的接縫（理由在 `tests/core/boundary_tables.py` 的 `# military` 那一組）

- `act:rank2`、`act:convoy`、`act:summons`、`act:rank:<行動>`：第 57 批接進 `Verb`（按下去與紀錄標題；`act:rank:<行動>` 帶後綴走 `tail_run`、`tail_title`，`Verb` 的名字照 `RANK_ACTION_PREFIX` 算，前綴只寫一次）；選單第 56 批是 `MENU_ORDER["here"]` 的 `order`、`rank2`、`rank` 那三格。
- `_summons_hop`（往召見地點）：假人移動的分數，留 `bot_policy`（移動包的 `move:` 讀）。`rank2`、`convoy`、`summons` 的分數第 60 批搬進 `bots.py`（`Verb.bot`），`bot_always` 加 `fs:`、`opp:`（原本 `bot.FORESHADOW_OPTIONS`）。改 `bots.py` 的 `act:` 分數時另外跑 `tests/bots/test_bot_policy.py`、`tianxia/features/sortie/tests/test_bot_policy_conquest.py`、`tests/bots/test_bot_policy_stuck.py`（`test_for` 挑不到，第 60 批）。
- `_report_seat`：`choose`、`travel` 與事件檢定的兩處（`answer_event`、`answer_branch`）叫，位置固定（回話與紀錄的先後算行為），沒有掛鉤可接；同步那一下第 55 批換成 `sync.deliver` 的 `seat` 那一格。
- 抵達那一刻經事件 `arrive` 的 `convoy` 那一格（`FEATURE.bus()`：`convoy_actions.convoy_arrives`，排在懸賞護送之前，順序在核心的 `BUS_ORDER`；第 26 批起，委派 `_convoy_arrives` 拿掉）。`_order_credit`：核心的單打服務（`_squad_encounter`）打贏之後記功；出陣、決戰、大勢人物也經 `ctx._order_credit` 叫。
- 「你這一步」的格（`FEATURE.steps()`，全部拆包第 36 批；順序在核心的 `STEP_ORDER`）：`order`（`order_actions.step_items`／`step_place`：沒做完的軍令一道一件、目標是最近的摸清了的那一處、護糧還沒接這一道的糧車多 `then`；`ORDER_GAIN` 從 `weekcard` 搬來，字一個不改；原本 `weekcard._steps` 的軍令那一段與 `step._order_places`、`_target`、`_then` 的軍令那一支）、`foreshadow`（`fs_actions.step_items`／`step_place`：讀伏筆的 `next_step`、`next_trip` 就是這一格回答，核心不再經舊名 `foreshadow` 讀，第 34 批 PM 認定第 1 條）。`step_items` 讀殼算好傳進來的 `orders_view` 那一份、不重算；不問 `enabled`；目標的最近一處問新手引導包的查詢服務 `ctx._nearest_to`、地點寫法用核心 `tianxia.step.place`。
- `server.py` 的 `orders`、`convoy` 兩個鍵（`/api/main`）照舊叫 Game 的委派；管理者三顆鈕第 68 批搬進 `routes.py` 的 `admin_tools`（鈕的順序在 `web/admin.js`，`FEATURE_ADMIN_ACTIONS` 只是查表用的 dict，第 33 批認定第 2 條收掉）。
- `orders.py`（軍令規則）、`ranks.py`、`seats.py` 不在這一包（共用規則層；`orders`、`ranks` 全部拆包第 40 批收進 `registry.SHARED`）。
- **第 34 批留在核心／共用層的接縫**（理由在邊界測試 `# military` 的第二段）：答題中的選單（`_fs_asking_options`，位置在店面之後、閉關之前）（答題的場景第二輪第 91 批改登記 `SCENE_ORDER` 的 `own/omen`）、閒著的選單上機緣與伏筆最後一步（`_omen_options`，夾在 `_rank_action_options` 與託付之間）、遊歷打贏之後的官銀與密謀一處（`_fs_after_win`、`_opp_on_win`；第 26 批量過留原位：夾在懸賞那一個發布點前面、讀先算好的記功，只在單打服務那一處有）、`_hear_after_stamina`（`choose` 結尾與 `travel`，伏筆先機緣後、共用 `self.rng`）、`_settle_plots`（`sync` 與 `choose` 結尾）。都因位置固定或順序算行為，沒有對應的掛鉤。
- **查詢服務 `tianxia/core/omen_base.py`**（核心本體）：核心的 `rules`（`grain_min` 的需求量換算；第 40 批起 `check_condition` 的 `clue_items` 也經它的 `clue_count` 讀）、`content`（天機表、題目）、共用規則層的 `ranks`（召見問這一階的機緣做過沒）、叛投確認畫面（`in_plot`）讀機緣、伏筆的「只讀」那一半，不 import 本包；`fs_rules`、`opp_rules` 從它 re-export 同一批名字。第 40 批多收了伏筆、機緣「讀」的那一半：`fs_active`、`event_ids`、`held_items`、`heard_texts`（連同填字那一串）、`opp_active`、`heard_clues`，另加新的 `clue_count`（`fs_rules`、`opp_rules` 照原名 re-export 同一個物件）。`content.py` 的 `check_foreshadows`、`check_opportunities` 因為夾在別的檢查中間、吃 `known` 與幾個局部變數，接不了 `check_content` 掛鉤（錯誤訊息的先後算行為），留在核心。
- `events`、`narration`、`rumor_view`、`server.py` 讀伏筆、機緣的規則，第 40 批起改問核心的 `omen_base`（原本走舊名別名 `foreshadow`、`opportunities`；`rumor_view` 同一批收進共用規則層）。`step`、`weekcard` 第 36 批起收進核心、不再讀別名：伏筆那一件改由這一包登記的 `foreshadow` 那一格（上面「你這一步」的格）。

## 過渡（手冊 3.11）

過渡 import 共 3 處（`test_feature_boundaries.py` 數，全部拆包第 40 批合完重印；第 33 批 8 處，第 34 批 11 處）：`order_actions`→`atlas`；`step_actions`→`events`；`fs_actions`→`atlas`。
第 50 批合完重印 **1 處**：`step_actions`→`events`。`order_actions`（`_strike_place`、`is_known`；`order_how` 第二輪第 97 批起讀自己這一包的 `order_cards.py`）、`fs_actions`（`region_of`）讀 `atlas` 的改註「共用規則層」（`atlas` 第 50 批收進 `registry.SHARED`，接第 34 批第 6 條）。
原本另外 8 處（`admin_actions`→`orders`、`ranks`；`convoy_actions`→`orders`；`order_actions`→`orders`；`rank_rules`→`ranks`；`fs_rules`→`figures`；`opp_rules`→`figures`、`ranks`）：`orders`、`ranks`、`figures` 第 40 批收進共用規則層（`registry.SHARED`），不算過渡，行尾註改寫成「共用規則層」；`atlas`（第 50 批）、`events` 等後面的批。
服務清單（`tianxia/core/services_list.md`）這一包加的：`_order_credit`（共用服務，出陣、決戰、大勢人物也經 `ctx` 叫）、`RANK_ACTION_PREFIX`、`_duty_option`（出陣包的委派，`order_options` 叫它）。
叛投那一刻經核心的叛投掛鉤（`core/features.py` 的 `DEFECT_ORDER`）`clear` 位置的 `convoy` 那一格清（`convoy_actions.defect_clear`：`p.convoy = None`，押著的糧車留給舊陣營；全部拆包第 32 批，原本 `defection.clear_progress` 直接寫）。軍令記下的貢獻（`contrib`、`contrib_weeks`）照舊由叛投自己的 `progress` 那一格清。釘住這一格的測試在包外、改這一包時 `test_for` 挑不到：`tianxia/features/faction/tests/test_defection.py::test_defect_resets_rank_and_old_progress`（叛投之後 `convoy` 是 None；下面「改這一包時連它們一起跑」那一串已經列了這個檔）。
事件的格（全部拆包第 26 批「事件機制」）：抵達一站（移動包 `departure.arrive` 的 `ctx.publish("arrive", loc_id)`，`Game._arrive` 掛在 `game_api.py` 的表）經核心的事件表（`core/features.py` 的 `BUS_ORDER`）`arrive` 的 `convoy` 那一格交糧車（`convoy_actions.convoy_arrives`），排在懸賞護送（懸賞榜包登記，第 45 批）之前；原本 `_arrive` 經委派 `_convoy_arrives` 直接叫。

## 內容歸屬

這一包 `content/` 底下：`promotions.json`、`events/promotion.json`（第 2 階晉升奇遇）、`opportunities.json`（機緣）、`foreshadows.json`（伏筆）、`events/foreshadow_fragments.json`（伏筆片段事件）、`events/foreshadow_prep.json`（伏筆的準備事件）歸這一包，`__init__.py` 的 `content` 宣告；檔名照舊，`content.py` 照它到這一包的 `content/` 載。

設計稿：軍令（見上）；機緣（正式版乙一、乙二）、伏筆（計畫 T7、伏筆文件）。導覽：`docs/guide/大勢人物與賽季.md`。

## 測試

- 這一包的 `tests/`：`test_rank_actions.py`（第 3、4 階行動：內容表、選單、做一次、做滿、推滿，67 個函式，原 `tests/core/`，整檔搬）、
  `test_military_smoke.py`（煙霧三條：黃巾第 3 階煽動起事；`opp:`、`fs:` 歸這一包、按下去走掛鉤；管理者兩個工具回拒絕）。
  第 34 批整檔搬進來的（只改路徑字串）：`test_opportunities.py`（93，六種機緣、第 2 階行動、密謀；原 `tests/figures/`）、`test_opportunities_two.py`（89，第二批的拼圖、推理、密謀、線索；原 `tests/figures/`）、`test_foreshadow.py`（37，片段、最後一步、鎖定、天機、官銀；原 `tests/figures/`）、`test_item7_foreshadow_cooldown.py`（4，答錯的冷卻）、`test_real_foreshadows.py`（27，真實內容的鏈每一條做得完；原 `tests/season/`，沒標 slow）。沒有 `military_stage.py`：這一包沒有掛鉤給選項，契約測試擺「平常」就夠（`STAGE_PACKAGES` 只列有擺局面檔的包）。
- `test_admin_triggers.py`（31 個函式）**留在 `tests/figures/`**：14 個是管理者的軍令、席次、召見，13 個是給機緣、給片段（這一包），其餘是開戰，混合檔不拆。

## 另外要跑的混合檔

改 `order_cards.py`（第二輪第 97 批）另外跑：`tests/acts/test_conquest_flip.py`、`tests/acts/test_conquest_siege.py`、`tests/figures/test_orders.py`、`tests/server/test_push_resistance.py`、`tianxia/features/map/tests/test_open_map.py`，與 `tianxia/features/sortie/tests/` 的 `test_sortie`、`test_sortie_duel`、`test_sortie_duel_words`、`test_sortie_duel_howto`。

混著別的功能、留在原處的（`條數＝碰到這一包的／全檔`，用語法樹數過，函式為單位，數字是粗的）；改這一包時連它們一起跑：

- 軍令卡、記功、押糧、席次抄帳：`tests/figures/test_orders.py`（20／85，`orders_view`、`_order_credit`、糧車）、`tests/figures/test_seats.py`（`_report_seat`）、
  `tianxia/features/faction/tests/test_defection.py`（2／41）、`tests/figures/test_gentry_allied.py`（`_summons_plan`）、`tests/ranger/test_season21_daily.py`（2／29）、`tests/figures/test_week7_season.py`
- 抵達那一刻交糧車（事件 `arrive` 的 `convoy` 那一格，第 26 批）：上面的 `tests/figures/test_orders.py`（糧車）；格的先後與登記由核心契約 `tests/core/test_contract_core.py`（`# core_eventbus`）鎖住。
- 「你這一步」的 `order`、`foreshadow` 兩格（第 36 批）：`tests/bots/test_step.py`（2／9：軍令的目標與 `then`、伏筆的目標〔換 `tianxia.foreshadow.next_trip`〕）、`tests/map/test_weekcard.py`（2／7：卡上的先後、新角色沒有伏筆那一件）；格的先後與登記由核心契約 `tests/core/test_contract_core.py`（`# core_step`）鎖住。
- 機緣與伏筆（第 34 批，粗數）：`tests/figures/test_promotions_huang.py`（32／56，第 4 階機緣與晉升）、`tests/figures/test_rumor_layers.py`（11／70，見聞頁的片段與線索）、`tianxia/features/guide/tests/test_hints.py`（9／108）、`tests/web/test_admin_triggers_web.py`（4／16，管理頁兩顆鈕與選單）、`tianxia/features/guide/tests/test_prologue.py`（3／101，序章不抽片段）、`tests/core/test_contract_core.py`（效果與叛投的格）、`tests/figures/test_promotions_high.py`、`tests/figures/test_gentry_allied.py`、`tianxia/features/faction/tests/test_defection.py`（叛投確認畫面問 `in_plot`）、`tests/core/test_rules.py`、`tests/core/test_content.py`（驗內容讀天機表與題目）
- 引導與網頁：`tianxia/features/guide/tests/test_opening.py`（2／9，`orders_view`）、`tests/map/test_weekcard.py`、`tianxia/features/guide/tests/test_prologue.py`（2／101）、`tests/web/test_prologue_web.py`（3／81）、`tests/web/test_jianghu_page_web.py`（1／134）
- 別包叫進來的：`tianxia/features/sortie/tests/test_sortie.py`（出陣不花出陣次數）、`tests/server/test_server.py`（2／385）
- 改這一包時：`python scripts/test_for.py --base HEAD tianxia/features/military/order_actions.py`

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.deliver` 的 `plots`（`opp_actions.deliver_plots`，經 `ctx._settle_plots`，寫「密謀」、存季）、`seat`（`seat_actions.deliver_seat`，寫「席次」）：兩格的回話都進同步的回話；`seat` 排在 `arrive`、`plots` 之後（`tests/figures/test_seats.py` 守）。

**第 56 批（選單收接縫，核心批）**：`take/omen`、`here/order`、`here/rank2`、`here/rank`、`here/omen`、`idle/omen` 是這一包登記的格（`fs_asking` 包外三處都改問核心 `omen_base.fs_answering`）；先後在 `core/features.py` 的 `MENU_ORDER`；委派 `_order_options`、`_rank2_options`、`_rank_action_options`、`_fs_asking_options`、`_omen_options` 拿掉；上面寫「留委派」「原位」的以這一句為準。

**第 57 批（分派與標題收接縫，核心批）**：`verbs()` 是新開的（`rank2`、`rank`、`convoy`、`summons`）。委派 `_rank2`、`_rank_action`、`_take_convoy`、`_rank2_action` 拿掉，engine 不再 import `step_actions`、`convoy_actions`；engine 模組層的 `_rank_action_id` 拿掉；`RANK_ACTION_PREFIX` 留在 engine（`features/military/tests` 從那裡拿）。上面寫「留委派」「原位」的以這一句為準。應召經 `ctx._present`、照模組屬性問 `ranks.summons_event`：`tests/bots/test_event_rotation.py`、`tests/core/test_engine.py`（`-k summons`）換的是這兩個名字，改這幾格另外跑。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`main` 表 `convoy`（軍令 `orders` 那一格留殼：本週卡也讀同一份）。
- 畫面：`web/military.js`（`ordersHtml`）、`web/military.css`（全部拆包第 67 批從 `main.js`、`style.css` 切出來，一個字不改）；`.order-*` 跟懸賞、奪璽卡共用，留 `style.css`。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `admin_tools`：`issue_orders`、`rotate_seats`、`summon`、`give_opportunity`、`give_fragment`。動到別人存檔的名單 `PLAYER_ADMIN_ACTIONS` 留在殼。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_admin_triggers.py`（原 `tests/figures/`）。

照條拆來：`test_military_shell.py`（1 條，從 `tests/server/test_server.py` 拆來）；兩邊都用的小工具在 `tests/kit/`（`engine_kit`、`server_kit`、`jianghu_kit`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- 表的名單加 `admin_player_choices`（`admin_actions.player_choices`，路由在管理者包，第 90 批）。
- `check_promotions`、`check_opportunities`、`check_foreshadows` 在這一包的 `checks.py`，原位經 `check_at` 叫，`known` 與局部變數照舊當參數傳（第 100 批）。
- `step_actions` → `events` 第 87 批起是共用規則層，不算過渡。
- 另外要跑的：改 `checks.py` 時 `test_for` 帶得到 `tests/core/test_content.py`（PM 定，第二輪 F 波），帶不到 `tests/core/test_content_packs.py`。
