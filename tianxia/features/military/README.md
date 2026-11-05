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
| `convoy_actions.py` | 押糧 2 個：`take_convoy`、`convoy_arrives`（走到終點：可能撞上截糧隊、記捐獻與貢獻、軍令記功）；叛投 `clear` 位置的 `convoy` 那一格 `defect_clear`（第 32 批） |
| `step_actions.py` | 第 2 階與第 3、4 階行動 6 個：`rank2_options`、`check_cost_note`、`rank2`、`rank_action_options`、`rank_action_line`、`rank_action` |
| `seat_actions.py` | 第四階席次抄帳：`report_seat`（賽季時鐘暫停中什麼都不做） |
| `admin_actions.py` | 管理者的軍令與召見：`issue_orders`、`rotate_seats`、`summons_plan`、`summon`，與回話用的五個常數 |
| `rank_rules.py` | 第 3、4 階行動的規則（原 `tianxia/rank_actions.py`，舊名留成指到同一個模組的別名） |
| `opp_rules.py` | 機緣的規則（原 `tianxia/opportunities.py`，舊名是別名）：六種機緣、閒著的選單、`act`（`opp:` 按下去）、第 2 階行動、密謀、線索、對話話題、叛投清進度 |
| `fs_rules.py` | 伏筆的規則（原 `tianxia/foreshadow.py`，舊名是別名）：聽片段、對話片段、最後一步、答題、官銀、天機、效果三格 |
| `opp_actions.py` | 機緣的動作：`settle_plots`、`give_opportunity`，與核心原位要問機緣的委派本體（選單、打贏記一處、第 2 階行動名字、管理頁選單、對話話題、之後記次數）；`HEARD_TITLE` |
| `fs_actions.py` | 伏筆的動作：`foreshadow`（`fs:` 按下去）、`hear_after_stamina`（伏筆先、機緣後）、`give_fragment`，與核心原位要問伏筆的委派本體（答題選單與場景、閒著的選單、打贏官銀、事件片段、對話片段、管理頁選單） |
| `bots.py` | 假人看到 `opp:`、`fs:` 都不按 |

`Game` 留 15 個一行委派（第 33 批）：`_order_options`、`_rank2_options`、`_rank_action_options`、`_rank2`、`_rank_action`、`_take_convoy`、`_convoy_arrives`、`_order_credit`、
`_report_seat`、`_summons_plan`、`orders_view`、`convoy_line`、`admin_issue_orders`、`admin_rotate_seats`、`admin_summon`；`_check_cost_note`、`_rank_action_line` 只有包裡自己叫，沒有委派。
第 26 批（事件機制）拿掉 `_convoy_arrives`（抵達那一刻改由這一包登記事件 `arrive` 的 `convoy` 那一格，見下面「事件的格」），剩 14 個。
第 34 批再留 16 個：`_settle_plots`、`_hear_after_stamina`、`admin_give_opportunity`、`admin_give_fragment`（原本就有的）與新增的 `_fs_asking_options`、`_fs_asking_text`、`_omen_options`、`_rank2_action`、`_fs_after_win`、`_opp_on_win`、`_admin_omen_choices`、`_hear_from_event`（事件檢定經 `ctx` 叫）、`_omen_talk_options`、`_fs_hear_talk`、`_opp_hear_topic`、`_opp_after_success`（後四個是人物情誼包、出陣包經 `ctx` 問的查詢服務）。

## 認領的欄位（`PlayerState`，換季全部跟著新角色重來，沒有帶走的）

`convoy`（押著的糧車；這一包寫，叛投那一刻也由這一包清成 None）、`rank2_days`（第 2 階行動今天做了幾次）、`rank_action_weeks`（第 3、4 階行動這週做了幾次；`rank_rules.count` 寫）。
第 34 批再認領 15 個：伏筆 7 個（`fragments`、`clue_items`、`fs_counters`、`fs_done`、`fs_cooldown_until`、`fs_asking`、`fs_asked`）、機緣 8 個（`opp_done`、`opp_counts`、`opp_items`、`opp_fronts`、`opp_clues`、`opp_tried`、`opp_pieces`、`opp_settled`）。叛投時 `opportunities` 那一格清掉機緣的進度，但 `opp_clues`、`opp_settled`、`fragments` 留著（企劃者裁決 E5.2：知道的事；結算過的密謀不會因為叛投再結算一次）。全服的集體密謀 `world.plots` 是共用賽季，不是 `PlayerState`，不認領。
`donations`（押糧與捐糧效果都寫）、`summons`、`qualified`、`rank`、`contrib_weeks`、`rank_hinted`、`patron` 是共用或階級、席次規則層的，不認領。

## 還留在核心原位的接縫（理由在 `tests/core/test_feature_boundaries.py` 的 `# military` 那一段）

- `act:rank2`、`act:convoy`、`act:rank:<行動>`：核心 `_act` 的 act 子動詞（總表第 57 批才擴 `Verb`），選單三段（`_everyday_options`，順序算行為）和按下去（`_act`）留在核心原位叫 Game 的委派。
- `act:summons`（人已在召見地點時按的應召）、`_summons_hop`（往召見地點）、`bot_policy.score` 的 `rank2`、`convoy`、`summons` 分數、`_summons_hop`：假人行動列的分數，留原位。
- `_report_seat`：`sync`、`choose`、`travel` 與事件檢定的兩處（`answer_event`、`answer_branch`）叫，位置固定（回話與紀錄的先後算行為），沒有掛鉤可接。
- 抵達那一刻經事件 `arrive` 的 `convoy` 那一格（`FEATURE.bus()`：`convoy_actions.convoy_arrives`，排在懸賞護送之前，順序在核心的 `BUS_ORDER`；第 26 批起，委派 `_convoy_arrives` 拿掉）。`_order_credit`：核心的單打服務（`_squad_encounter`）打贏之後記功；出陣、決戰、大勢人物也經 `ctx._order_credit` 叫。
- `server.py` 的 `orders`、`convoy` 兩個鍵（`/api/main`）與管理者三顆鈕（`/api/do` 的路由留原位，批次表第二節；`ADMIN_ACTIONS` 只是查表用的 dict，照包分是第 68 批）照舊叫 Game 的委派。
- `orders.py`（軍令規則）、`ranks.py`、`seats.py` 不在這一包（共用規則層，總表第 40 批）。
- **第 34 批留在核心／共用層的接縫**（理由在邊界測試 `# military` 的第二段）：答題中的選單（`_fs_asking_options`，位置在店面之後、閉關之前）與場景文字（`_fs_asking_text`，在拜入／投靠／叛投／求見的畫面之後）、閒著的選單上機緣與伏筆最後一步（`_omen_options`，夾在 `_rank_action_options` 與託付之間）、遊歷打贏之後的官銀與密謀一處（`_fs_after_win`、`_opp_on_win`；第 26 批量過留原位：夾在懸賞那一個發布點前面、讀先算好的記功，只在單打服務那一處有）、`_hear_after_stamina`（`choose` 結尾與 `travel`，伏筆先機緣後、共用 `self.rng`）、`_settle_plots`（`sync` 與 `choose` 結尾）。都因位置固定或順序算行為，沒有對應的掛鉤。
- **查詢服務 `tianxia/core/omen_base.py`**（核心本體）：核心的 `rules`（`grain_min` 的需求量換算）、`content`（天機表、題目）、共用層待收的 `ranks`（召見問這一階的機緣做過沒）、叛投確認畫面（`in_plot`）讀機緣、伏筆的「只讀」那一半，不 import 本包；`fs_rules`、`opp_rules` 從它 re-export 同一批名字。`content.py` 的 `check_foreshadows`、`check_opportunities` 因為夾在別的檢查中間、吃 `known` 與幾個局部變數，接不了 `check_content` 掛鉤（錯誤訊息的先後算行為），留在核心。
- `events`、`narration`、`rumor_view`、`step`、`weekcard`、`server.py` 讀伏筆、機緣的規則，走舊名別名（它們是舊模組，還沒收進共用層）；各自收進共用層時改成查詢服務。

## 過渡（手冊 3.11）

過渡 import 共 11 處（`test_feature_boundaries.py` 數；第 33 批 8 處，第 34 批拿掉 `step_actions`→`opportunities`、加 `fs_actions`→`atlas`、`fs_rules`→`figures`、`opp_rules`→`figures`、`ranks`）：`admin_actions`→`orders`、`ranks`；`convoy_actions`→`orders`；`order_actions`→`atlas`、`orders`；`rank_rules`→`ranks`；`step_actions`→`events`；`fs_actions`→`atlas`；`fs_rules`→`figures`；`opp_rules`→`figures`、`ranks`。
`orders`、`ranks`、`figures` 是共用規則層（第 40 批收進 `SHARED`），`atlas`（第 50 批）、`events` 等後面的批。
服務清單（`tianxia/core/services.py`）這一包加的：`_order_credit`（共用服務，出陣、決戰、大勢人物也經 `ctx` 叫）、`RANK_ACTION_PREFIX`、`_duty_option`（出陣包的委派，`order_options` 叫它）。
叛投那一刻經核心的叛投掛鉤（`core/features.py` 的 `DEFECT_ORDER`）`clear` 位置的 `convoy` 那一格清（`convoy_actions.defect_clear`：`p.convoy = None`，押著的糧車留給舊陣營；全部拆包第 32 批，原本 `defection.clear_progress` 直接寫）。軍令記下的貢獻（`contrib`、`contrib_weeks`）照舊由叛投自己的 `progress` 那一格清。釘住這一格的測試在包外、改這一包時 `test_for` 挑不到：`tests/figures/test_defection.py::test_defect_resets_rank_and_old_progress`（叛投之後 `convoy` 是 None；下面「改這一包時連它們一起跑」那一串已經列了這個檔）。
事件的格（全部拆包第 26 批「事件機制」）：抵達一站（`Game._arrive` 的 `ctx.publish("arrive", loc_id)`）經核心的事件表（`core/features.py` 的 `BUS_ORDER`）`arrive` 的 `convoy` 那一格交糧車（`convoy_actions.convoy_arrives`），排在懸賞護送（核心代叫，第 45 批）之前；原本 `_arrive` 經委派 `_convoy_arrives` 直接叫。

## 內容歸屬

`content/promotions.json`、`content/events/promotion.json`（第 2 階晉升奇遇）、`content/opportunities.json`（機緣）、`content/foreshadows.json`（伏筆）、`content/events/foreshadow_fragments.json`（伏筆片段事件）、`content/events/foreshadow_prep.json`（伏筆的準備事件）歸這一包，`__init__.py` 的 `content` 宣告；檔名照舊，`content.py` 照舊讀。

設計稿：軍令（見上）；機緣（正式版乙一、乙二）、伏筆（計畫 T7、伏筆文件）。導覽：`docs/guide/大勢人物與賽季.md`。

## 測試

- 這一包的 `tests/`：`test_rank_actions.py`（第 3、4 階行動：內容表、選單、做一次、做滿、推滿，67 個函式，原 `tests/core/`，整檔搬）、
  `test_military_smoke.py`（煙霧三條：黃巾第 3 階煽動起事；`opp:`、`fs:` 歸這一包、按下去走掛鉤；管理者兩個工具回拒絕）。
  第 34 批整檔搬進來的（只改路徑字串）：`test_opportunities.py`（93，六種機緣、第 2 階行動、密謀；原 `tests/figures/`）、`test_opportunities_two.py`（89，第二批的拼圖、推理、密謀、線索；原 `tests/figures/`）、`test_foreshadow.py`（37，片段、最後一步、鎖定、天機、官銀；原 `tests/figures/`）、`test_item7_foreshadow_cooldown.py`（4，答錯的冷卻）、`test_real_foreshadows.py`（27，真實內容的鏈每一條做得完；原 `tests/season/`，沒標 slow）。沒有 `military_stage.py`：這一包沒有掛鉤給選項，契約測試擺「平常」就夠（`STAGE_PACKAGES` 只列有擺局面檔的包）。
- `test_admin_triggers.py`（31 個函式）**留在 `tests/figures/`**：14 個是管理者的軍令、席次、召見，13 個是給機緣、給片段（這一包），其餘是開戰，混合檔不拆。

## 另外要跑的混合檔

混著別的功能、留在原處的（`條數＝碰到這一包的／全檔`，用語法樹數過，函式為單位，數字是粗的）；改這一包時連它們一起跑：

- 軍令卡、記功、押糧、席次抄帳：`tests/figures/test_orders.py`（20／85，`orders_view`、`_order_credit`、糧車）、`tests/figures/test_seats.py`（`_report_seat`）、
  `tests/figures/test_defection.py`（2／41）、`tests/figures/test_gentry_allied.py`（`_summons_plan`）、`tests/ranger/test_season21_daily.py`（2／29）、`tests/figures/test_week7_season.py`
- 第 2 階行動與召見：`tests/figures/test_admin_triggers.py`（14／31）
- 機緣與伏筆（第 34 批，粗數）：`tests/figures/test_promotions_huang.py`（32／56，第 4 階機緣與晉升）、`tests/figures/test_admin_triggers.py`（13／31，給機緣、給片段）、`tests/figures/test_rumor_layers.py`（11／70，見聞頁的片段與線索）、`tests/arts/test_hints.py`（9／108）、`tests/web/test_admin_triggers_web.py`（4／16，管理頁兩顆鈕與選單）、`tests/core/test_prologue.py`（3／101，序章不抽片段）、`tests/core/test_contract_core.py`（效果與叛投的格）、`tests/figures/test_promotions_high.py`、`tests/figures/test_gentry_allied.py`、`tests/figures/test_defection.py`（叛投確認畫面問 `in_plot`）、`tests/core/test_rules.py`、`tests/core/test_content.py`（驗內容讀天機表與題目）
- 引導與網頁：`tianxia/features/guide/tests/test_opening.py`（2／9，`orders_view`）、`tests/map/test_weekcard.py`、`tests/core/test_prologue.py`（2／101）、`tests/web/test_prologue_web.py`（3／81）、`tests/web/test_jianghu_page_web.py`（1／134）
- 別包叫進來的：`tianxia/features/sortie/tests/test_sortie.py`（出陣不花出陣次數）、`tests/server/test_server.py`（2／385）
- 改這一包時：`python scripts/test_for.py --base HEAD tianxia/features/military/order_actions.py`
