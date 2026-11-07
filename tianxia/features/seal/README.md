# 玉璽碎片（`tianxia/features/seal/`）

七片傳國玉璽碎片的季流程：時刻表決戰集結那一刻擲現世與璽動、領地爭奪的季開季藏一片與探索撿到、時刻表決戰收場（挑挑戰者、現世的得主、喚回）、補送到每個人手上、天命之季與天命之爭、換季的隱沒與散去，與管理者的強制現世（現在藏一片）、隱沒判斷、蓋天命之季。全部拆包第 27 批「玉璽一」搬進來（引擎那一半；網頁 `web/seal.js` 第 66 批從 `app.js` 切出來）。

**第 28 批「玉璽二」搬進來的**：奪璽單挑的純規則（`duel_rules.py`，原 `tianxia/seal_duel.py` 整份）、奪璽單挑的玩法（`duel_actions.py`）、碎片卡與七種獨門行動（`card.py`）、管理者六個（`admin.py` 加 `stir`、`assign`、`duel`、`fix`、`cancel`、`choices`）、`seal:` 前綴與假人那一段（`bots.py`）。`Game` 上的名字掛在 `game_api.py` 的表（`_seal_challenge`、`_my_seal_duel` 沒有呼叫端、不留；`_seal_act_season` 只有 `seal_use` 叫、包內互叫，不留）。獨門行動的規則 `tianxia/seal_acts.py`（761 行）第 51 批才拆，`card.py`、`admin.py` 讀它（過渡）。

- 導覽：`docs/guide/玉璽碎片.md`。
- 設計稿：`docs/superpowers/specs/2026-10-11-玉璽碎片-design.md`（現世、璽動、挑人、易手、隱沒、抄本、天命之季）、`docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md`（常駐效果、持有者平時藏起來）；領地爭奪設計 3.9、4.8（藏一片、探索撿到）。
- 計畫：`docs/superpowers/plans/2026-11-07-玉璽包-第1批.md`（第 27 批）、`docs/superpowers/plans/2026-11-06-玉璽包-第2批.md`（第 28 批）。

## 裡面有什麼

- `seal.py`（原 `tianxia/seal.py` 整份；舊名留成指到這裡的 `sys.modules` 別名，換掉的屬性兩邊都看得到——`tests/acts/test_conquest_rules.py` 換 `seal.find`、`scripts/measure_seal.py` 換 `seal.tier_for`、`seal.lean_shift`，`scripts/same_behavior.py` 的 `relic` 一軌換 `seal.secrets.token_hex`）：碎片的規則與字句。擲骰一律 `dice`（密鹽｜天機｜用途｜…），不碰 `Game.rng`。
- 核心與決戰包「不得不讀」的那一小半在**核心本體** `tianxia/core/seal_base.py`（PM 認定甲案，同第 34 批 `omen_base`、第 40 批 `smith_base`）：`on`、`revamp_on`、`filled`、`key`、`holders`、`mandate_event`、`mandate_battle`、`is_mandate_battle`、`mandate_now`、`deserted`、`threshold`、`challenger_ok`、`hint_names`、`merit_hint`、`stir_text`、`lean_shift`、`lean_text`、`shift_text`、`chronicle_block`、`sink_text` 與它們的字句；`seal.py` re-export 同一批函式物件（名字一個不改）。讀它的：核心的 `world.evaluate_ending`、`world.end_season`、`Game.admin_resolve_event`、`Game.chronicle_text`，決戰包的 `view.py`、`progress.py`。`tier_for`、`find` 不搬去（測試、量表換掉的，只有這一包與第 28 批的 Game 方法讀）。`lean_shift` 搬去了：這一包的 `seal._mandate_muster` 照模組屬性找、`measure_seal` 換得到；決戰畫面讀 `seal_base` 那一份（參數是集結那一刻的快照，算出來一樣）。
- `actions.py`：原本 `Game` 上的季流程——`copy_heirloom`（抄本照登記重抄）、`seal_find`（探索撿到）、`seal_bare`（戴著碎片時不含碎片的份量快照）、`mandate_weight`（天命之爭份量加權）、`deliver_results`（補送）、`file_seal`（奪璽單挑寫成戰報與紀錄）、`mandate_settle`（定天命）、`settle`（時刻表決戰收場）。包裡互叫直接叫；叫回 `Game` 的經 `ctx`：第 28 批的 `_seal_challenge`、自己的委派 `_mandate_settle`（`measure_seal` 換 `Game._mandate_settle`）。
- `admin.py`：`emerge`（強制現世；領地爭奪的季改成 `hide` 現在藏一片）、`sink_check`（隱沒判斷）、`mandate`（蓋天命之季：`now`、`next`、`cancel`）；第 28 批加 `stir`（強制璽動）、`assign`（指定持有者）、`duel`（開單挑）、`fix`（定單挑結果）、`cancel`（取消單挑）、`choices`（管理頁的玉璽一組）。
- `duel_rules.py`（第 28 批；原 `tianxia/seal_duel.py` 整份，468 行；舊名留成指到這裡的 `sys.modules` 別名，`scripts/measure_seal.py` 換 `finish`／`resolve`／`open_round` 兩邊都看得到）：奪璽單挑的純規則與字句（兩邊的快照、回合、在場與代打、放手一搏、再擲、卡片）。包內一律照模組屬性叫 `duel_rules.<名字>`，不寫 `from … import 函式`。
- `duel_actions.py`（第 28 批）：`challenge`（璽動那一場收場挑挑戰者、開單挑；`actions.settle` 直接叫）、`challengers`、`spectators`（`challenge` 經 `ctx._seal_challengers`／`ctx._seal_spectators` 叫，`scripts/measure_seal.py` 換的是 `Game` 上這兩個名字）、`side_of`、`my_duel`、`tick`（把單挑推到現在）、`options`、`act`（選單上的三招）、`free_text_prompt`、`free_text_note`、`text_request`、`gamble`（放手一搏的輸入框與兩段）、`duel_card`（江湖頁的奪璽卡）、`watch`（背景輪詢）。
- `card.py`（第 28 批）：`view`（持有者的碎片卡，`status_data["seal"]`）、`act_season`（卡上要的季況，只有 `view`、`use` 叫）、`use`（起用懷中那一片的獨門行動，`MAIN_ACTIONS["seal_use"]`）。
- `bots.py`（第 28 批）：`score(option)` 一律 `None`（奪璽單挑假人一律被代打，選單上的 `seal:` 招不按；原本 `bot_policy.score` 的 `seal` 那一段），`SealFeature.bot_pick` 叫它。
- `season.py`：原本核心 `sqlite_world` 的三段——`stamp_cache`（開季藏一片）、`stamp_mandate`（換季蓋天命之季的章）、`retire`（舊季收尾：隱沒、沒收場的奪璽單挑記成未分勝負、天命之季過後七片散去）。直接改傳進來的 `SharedWorldState`。
- 掛鉤（`__init__.py`，都不問 `enabled`，格裡自己問 `content.seal`、`Config.seal.enabled`：**散去不看開關、隱沒看開關**）：
  - 事件（`bus()`；位置照核心 `BUS_ORDER`）：`outing` 的 `seal`（探索一顆收尾撿碎片，排在打探懸賞之後；回 `list[str]`）、`battle_end` 的 `seal`（時刻表決戰收場，回 `None`）。發布點照舊在探索包 `explore_actions.explore_one`、決戰包 `progress.settle_showdown`。收場之後的補送 `ctx._deliver_seal_results()` 是查詢服務，**不併進 `battle_end`**（第 26 批認定第 3 條）。
  - 世界層（`world()`；位置照 `WORLD_ORDER`、簽名照原樣）：`muster` 的 `seal`（集結那一刻擲現世與璽動，`seal.on_muster`；「集結開始」就是這一格、不另開事件）、`open` 的 `seal.cache`、`next` 的 `seal.mandate`（`content.seal` 與 `Config.seal.enabled` 都開著才叫）與 `seal.cache`、`retire` 的 `seal`（回寫了上一季的江湖史沒）。`state.seal.opened_real = now` 那兩行是核心寫核心的資料，留在 `sqlite_world`。
  - 接縫（第 11 批）：`deliver_results`（`sync` 收場補送那一格：玉璽碎片的事補送到自己手上，`actions.deliver_results`；排在決戰包後面）。
  - 效果（`effects()`；位置照 `EFFECT_ORDER`）：`runic`（符文殘片；在叫的那一下才從 `tianxia.rules` 拿 `season_one`，PM 認定不統一成 import 時綁定）、`shard`（舊鏈的玉璽碎片，不認領欄位）。
- `name = "seal"`、`prefix = "seal"`（第 28 批登記；`menu`、`choose` 不接：選單是 `MENU_ORDER["front"]` 的 `seal` 那一格〔第 56 批；排在決戰選單前面、不看包是否開著〕、`choose` 的 `seal:` 是「選單上、不建紀錄」的 `MENU_ORDER["quick"]` 那一格〔第 57 批〕；沒有 `APIRouter`；管理者的 `seal_*`、`seal_use` 第 68 批搬進 `routes.py`，`seal_text` 是鎖外三段式，第 69 批也搬進來、接 `outlock` 掛鉤）、`bot_pick`、`enabled` 照 `seal.on`、`content = ("seal.json",)`。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields = ("heirloom", "seal_seen")`：傳承那一格的抄本、補送到全服登記第幾號。
- `carried = ("seal_seen",)`（`tests/core/test_contract_features.py::test_a_new_season_keeps_only_what_the_package_carries[seal]` 實跑定）：換季（`season.carry` 的 `seal` 那一格，第 55 批）兩個都照帶，可是 `heirloom` 換季後建 `Game` 時照全服登記重抄（`copy_heirloom`），弄髒的值會被清掉，所以不算帶走的。
- 包外讀寫這兩欄的（第 34 批認定第 9 條，照實記、排批）：核心 `_lose_silver`（讀 `heirloom.name`，碎片保銀那一句；第 55 批或銀兩出口那一批看）；共用層 `treasures`（`amount`、`power_scale` 等讀傳承那一格；第 51 批與璽效查詢一起看）；`skillview`（`SHARED_LATER`，讀）；酒肆包 `features/tavern/rules.py`（讀；酒肆下一次動到時改查詢服務）；探索包測試 `test_explore_one.py`（讀）。陣營包 `defection` 不讀這兩欄。
- **這一包讀別包的欄位**：`actions.seal_find` 讀探索包認領的 `PlayerState.explore_seq`（這個人第幾次探索，撿碎片的骰子用）——排給第 55 批（補算收接縫）改查詢服務。
- 資料在核心、不認領：`SharedWorldState.seal`（全服登記）、`seal_duels`、`jade_seal_fragments`（舊鏈的碎片），`WorldState.mandate`、`mandate_result`。

## 委派與留在原位的接縫（理由在 `tests/core/boundary_tables.py` 的 `# seal` 那一組）

`Game` 上的名字掛在 `game_api.py` 的表（`_copy_heirloom` 第 55 批換成 `sync.heirloom`、`stale.mid` 兩格，拿掉）：`_deliver_seal_results`、`_seal_bare`、`_mandate_settle`（核心原位叫）、`_mandate_weight`（決戰包經 `ctx`）、`_seal_find`、`_seal_settle`、`_file_seal`（**只剩測試叫**：寫進手冊「拆完之後的收尾：只剩測試叫的委派」，第 42 批認定第 3 條）、`admin_seal_emerge`、`admin_seal_sink_check`、`admin_seal_mandate`（殼的 `ADMIN_ACTIONS` 與測試）。`_admin_seal_hide` 只有強制現世叫（包內互叫），不留。

第 28 批再加 20 個（第二輪第 72 批起都在 `game_api.py` 的表）：`_seal_challengers`、`_seal_spectators`（量表 `scripts/measure_seal.py` 換它們，包內經 `ctx` 叫）、`_seal_side_of`（只剩測試叫）、`_seal_tick`、`_seal_options`、`_seal_act`（`world_tick`／`options`／`choose` 原位叫）、`seal_view`、`seal_duel_card`（測試叫；`seal_watch` 第 66 批拿掉，狀態列三個鍵改走 `status_slots`）、`seal_free_text_prompt`、`seal_free_text_note`、`seal_text_request`、`seal_gamble`、`seal_use`（殼的 `server.py` 叫；測試換 `Game.seal_use`，所以一定留）、`admin_seal_stir`、`admin_seal_assign`、`admin_seal_duel`、`admin_seal_fix`、`admin_seal_cancel`、`admin_seal_choices`（殼的 `ADMIN_ACTIONS`）。`GAME_DIRECT` 16 → 3（第 27 批留的 13 筆「過渡：第 28 批收」全收了）；`GAME_DELEGATE_CALLERS` 刪 7 對（`_deliver_seal_results`、`_showdown_status`、`_duel_side` 改成包經 `ctx` 叫，列在 `core/services_list.md` 的 `# seal`）、加 7 對（`world_tick`／`options → _seal_tick`、`options → _seal_options`、`choose → _seal_act`；`status_data` 那三對第 66 批刪；理由在邊界測試）。

- `GAME_DELEGATE_CALLERS` 6 對（`sync`、`_drop_stale_references → _copy_heirloom` 第 55 批換成格，拿掉）：`_battle_marks → _seal_bare`（戰力快照是單打服務）、`admin_resolve_event → _mandate_settle`（時刻表的救場工具是核心）、第 28 批的 `_seal_tick`／`_seal_act`／`seal_gamble`／`admin_seal_cancel` 各配 `_deliver_seal_results`。
- `sync` 的玉璽補送（原本緊接在 `features_core.deliver_results(self)` 後面的 `self._deliver_seal_results()`）修正輪改接接縫掛鉤 `deliver_results`（`SealFeature.deliver_results` 叫 `actions.deliver_results`）：那個掛鉤照 `registered()` 問、不看開關，只有 `sync` 叫；決戰包排在前面、玉璽包排在後面，先後跟原本那兩行一樣。委派 `_deliver_seal_results` 照留（第 28 批的四個方法與決戰包 `progress.py` 經 `ctx` 叫）。
- `GAME_DIRECT` 第 28 批全收（13 筆都拿掉；剩下 3 筆不是玉璽的）。
- 選項前綴 `seal:`：`options`、`choose` 是 `MENU_ORDER` 的 `front`、`quick` 那兩格（第 56、57 批），`_shop_open`（`startswith(("battle:", "seal:"))` 核心的字面比對）原位；`bot_policy.score` 的那一段第 28 批搬進 `bots.py`。

**第 51 批「玉璽三」搬進來的**：`tianxia/seal_acts.py` 的包這一半進 `acts.py`（目標、灰掉的原因、碎片卡、字句、次數與時間，約 520 行，逐字）；別包讀的 16 個璽效查詢留在共用規則層 `tianxia/seal_acts.py`（登記進 `registry.SHARED`，不留搬走的名字的別名）。`Game` 沒動，選項前綴、路由、`PlayerState` 欄位都沒動。
另外要跑的（共用層說明字串同一串）：`tianxia/features/seal/tests/`、`tests/figures/test_plans.py`、`tests/acts/` 的 `test_conquest_flip`、`test_conquest_rules`、`test_conquest_siege`。

## 過渡（手冊 3.11）

- 包 → 舊模組：第 51 批之後 `card.py`、`admin.py` 讀的 `seal_acts`（`on`、`EPS`）是共用規則層，不算過渡；包裡沒有別的過渡 import。`seal.py` 函式裡讀的 `atlas`（藏碎片要認大區）開發時是舊模組，第 50 批收進了共用規則層：合進 `split/trunk` 之後不算過渡，那一行的註改成「共用規則層」。第 27 批的 `actions.py` → `seal_duel` 第 28 批收了。
- 舊模組 → 包（經舊名 `tianxia.seal`）：engine（`seal_rules`）、`bot_runner`（叫醒持璽的假人）、`howto`、`skillview`、`seal_duel`（現在也是別名，指到 `duel_rules.py`）、殼 `server.py`、`run_bots.py`（`ensure_salt`）、`scripts/measure_seal.py`（也直接換包的 `actions.settle`）、`measure_tactics.py`、`same_behavior.py`。`SHARED_PENDING` 的四條 `(conquest|figures|figure_life|plans, seal_acts)`：`seal_acts` 函式裡 import `seal`，連帶載入玉璽包。

## 內容歸屬

這一包的 `content/seal.json`（七片）；`content.py` 照它到這一包的 `content/` 載、照舊驗（`validate_seal` 在這一包的 `checks.py`，原位經 `check_at` 叫、不接 `check_content`，第二輪第 100 批）。`Config.seal`（`SealTuning`）留在 `models.py`。時刻表上標 `seal`（`emerge`／`stir`）與 `mandate_only` 的決戰在 `content/timetable.json`；`content.mandate_timetable` 只准 `timetable.py`、`content.py`、`models.py` 與 `core/seal_base.py` 讀（`test_seal_mandate.py` 守門）。

## 測試

- 包裡（`tests/`，第 27 批整檔搬來的五個只改路徑字串，第 41 批認定第 6 條：沒有人用裸名 import 的）：`test_seal_mandate.py`（天命之季與天命之爭；守門 `test_only_the_gatekeepers_read_the_mandate_timetable` 的範圍加了包的資料夾、白名單加 `core/seal_base.py` 與包的 `seal.py`，判斷不動）、`test_seal_revamp_hidden.py`、`test_seal_revamp_sidedoor.py`（持有者平時藏起來、側門看不穿）、`test_seal_acts_hidden.py`（獨門行動不具名）、`test_measure_seal_args.py`（量表腳本的參數，原本在 `tests/season/`），加上新寫的 `test_seal_smoke.py`（包的宣告與格、舊名是同一個模組、week7 探索一顆走到藏處撿到）與 `seal_stage.py`（契約測試擺「懷璽」的局面）。第 28 批整檔搬來 `test_seal_duel.py`（27 個測試函式，只改位置；它用裸名 `from test_seal import …`，`tianxia/features/seal/tests/test_seal.py` 反過來在函式裡 `from test_seal_duel import _duel`，兩個資料夾都在 `sys.path` 上）；`test_seal_smoke.py` 加前綴與舊名別名一條。
- **第 61 批整檔搬來**（被別的檔用裸名 import，第 41 批認定第 6 條留到這一批；兩份 conftest 都把每包的 `tests/` 放上 `sys.path`，照舊拿得到）：`test_seal.py`（`test_seal_acts`、`duel`、`engine`、`mandate`、`revamp`、`revamp_hidden`、`revamp_sidedoor` 拿）、`test_seal_engine.py`（`test_seal_duel`、`test_seal_mandate` 拿）、`test_seal_revamp.py`（`test_seal_duel`、`acts`、`revamp_hidden`、`revamp_sidedoor` 拿）、`test_seal_acts.py`、`test_seal_acts3.py`（`tianxia/features/seal/tests/test_seal_acts_web.py` 拿）。`test_seal_duel.py` 是第 28 批；`test_wins_tiers.py` 歸核心（`final_owner.json`）。`test_seal.py` 掃原始碼找 `exclude_if` 的那一條，範圍改成跟搬之前同一批（`tianxia/*.py`）再加包的資料夾與核心本體 `core/seal_base.py`（只改範圍；`core/seal_base.py` 是合進 `split/trunk` 時補的，審查 nit）。
- **另外要跑的混合檔與核心代叫**（`test_for` 改這一包挑不到，或只挑到一部分）：
  - `tianxia/features/peers/tests/test_social.py`（import `seal`）。
  - 效果的兩格：`tests/core/test_rules.py`（舊鏈的玉璽碎片 5 條）、`tests/figures/test_promotions_huang.py`（符文殘片，含叛投不清殘片）。
  - 事件 `outing` 的 seal 那一格：探索包 `tianxia/features/explore/tests/test_explore_one.py`（出門一趟收尾撿碎片）；`battle_end` 那一格與決戰包讀 `seal_base`：`tianxia/features/battle/tests/`。
  - 管理者工具與領地爭奪的季：`tests/acts/test_conquest_rules.py`（換 `seal.find`、叫 `_seal_find`）、`tests/figures/test_week7_season.py`、輿圖包 `tianxia/features/map/tests/test_mapdata.py`、`test_real_map.py`、地盤包 `tianxia/features/territory_acts/tests/test_xingshi.py`。
  - 誰登記了哪幾格：`tests/core/test_contract_core.py`、`tests/core/test_contract_features.py`（`test_a_new_season_keeps_only_what_the_package_carries[seal]` 定 `carried`）、`tests/core/boundary_tables.py`（`# seal` 那一組）；名望來源清單 `tianxia/features/guide/tests/test_explain2.py`（奪璽單挑那一行在 `features/seal/actions.py`）。
  - 世界層五格（第 25 批認定第 7 條：`seal` 原本是 `world.py` 模組說明點名的世界層代叫舊模組，`test_for` 挑不到 `test_world` 那一串）：`tests/core/test_world.py` 與 `world.py` 模組說明「另外要跑的」那一串——`tests/figures/test_timetable.py`、`test_seats.py`、`tianxia/features/admin/tests/test_season_pause.py`、`tianxia/features/companions/tests/test_stances_tie.py`、`tests/figures/test_week7_season.py`、`tianxia/features/bounties/tests/test_bounties.py`、`test_season21_daily.py`、`tests/figures/test_season21_frame.py`、`test_season21_caps.py`、`test_plans.py`、`test_figure_life.py`、`test_figure_attrition.py`、`tests/battle/test_fronts.py`、`tests/figures/test_front_lines.py`、`test_finale.py`、`test_admin_triggers.py`、`test_calendar.py`、`tianxia/features/seal/tests/test_seal.py`、`test_seal_engine.py`（換季把沒收場的奪璽單挑記成未分勝負）、`test_seal_acts.py`、`tests/acts/test_conquest_rules.py`、`tianxia/features/stamina_plays/tests/test_stamina_plays.py`、`tests/core/test_chapters.py`、`test_marks_wired.py`、`tianxia/features/looks/tests/test_looks_mvp.py`（`tianxia/features/map/tests/test_world_map.py` 整檔 slow）。
  - 量表：`scripts/measure_seal.py` 換 `seal.tier_for`、`seal.lean_shift`、包的 `actions.settle`、`Game._mandate_settle`、`Game._seal_challengers`、`Game._seal_spectators`、`seal_duel.finish`／`resolve`、`BotRunner._add_bot`、`SqliteWorldStore.open_season`——改這一包的收場、定天命、集結時跑一次小參數確認數字有記到（`open_season`、`lean_shift`、`_mandate_settle` 只在 `--mandate` 底下換；week7 預設 `--hours 60` 走不到天命之爭，要 `--hours 160`，修正輪量過）。比對：`scripts/same_behavior.py` 的 `relic`、`herald`、`world`、`effects`、`battle`、`progress` 幾軌與 `explore-compare`。
- 一起跑（不含 slow；第 27 批 Task 3 跑過同一串加世界層那一串——那時這一包的五個檔還在 `tests/seal/`、還沒有煙霧——1,568 條、`-n 4` 約 58 秒）：`python -m pytest -q -n 4 tianxia/features/seal/tests tests/seal tests/core/test_rules.py tests/figures/test_promotions_huang.py tests/acts/test_conquest_rules.py tests/figures/test_week7_season.py tianxia/features/map/tests/test_mapdata.py tianxia/features/map/tests/test_real_map.py tianxia/features/territory_acts/tests/test_xingshi.py tianxia/features/explore/tests/test_explore_one.py tianxia/features/guide/tests/test_explain2.py tests/core/test_test_for.py tianxia/features/peers/tests/test_social.py tianxia/features/seal/tests/test_seal_acts_web.py tianxia/features/seal/tests/test_seal_web.py tianxia/features/battle/tests tests/core/test_world.py`，加上面世界層那一串。

## 量到的（第 27 批 Task 5）

包的測試 83 條（含 slow 11）`-n 4` 11.9 秒；改包任一檔挑到 83 條（加核心契約與邊界一共 357 條）；包 → 舊模組 2 處（`actions.py` → `seal_duel`、`seal.py` → `atlas`；合進 `split/trunk` 重印剩 1 處：`atlas` 第 50 批收進了共用規則層）；Game 委派 11 個；`GAME_DIRECT` 13 個（第 28 批收）、`GAME_DELEGATE_CALLERS` 9 對（修正輪 `sync` 那一對改接 `deliver_results` 掛鉤，剩 8 對）；`engine.py` 6,626 行（搬之前 6,954）。`same_behavior` 全部 42 軌與 `explore-compare` 三種設定整段、半舊半新、假人逐位元組一樣；`measure_seal.py --seeds 1 --force-stir --holders 7`（week7，約 6 分鐘）搬之前、之後印的數字一樣。細節見計畫 `docs/superpowers/plans/2026-11-07-玉璽包-第1批.md` 第五節。


## 量到的（第 28 批）

`Game` 委派 556 → 576（`_seal_challenge`、`_my_seal_duel` 沒有呼叫端，不留；包內直接叫 `challenge`、`my_duel`）；`GAME_DIRECT` 16 → 3、直連 197 → 184；`GAME_IMPORTS` 92 → 93（拿掉 `tianxia.seal`、加 `card`、`duel_actions`）。`engine.py` 頂端的 `seal_rules`、`seal_duel` 拿掉。包裡 `tests/` 129 條。`selftest` 目標句（`MUTATIONS` 45、`EXPLORE_MUTATIONS` 4）在搬完的檔裡都找得到一次；新軌 `carve` 的目標句在 `duel_actions.py`。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.heirloom`、`stale.mid` 的 `seal` 重抄抄本（`actions.copy_heirloom`：碎片關著時也要叫、傳 `None` 把抄本清掉，所以接不了 `on_sync`、`on_drop_stale`）；`tick` 的 `seal` 推奪璽單挑（`duel_actions.tick`）；`season.carry` 的 `seal` 照帶 `heirloom`、`seal_seen`。

**第 56 批（選單收接縫，核心批）**：`tick`、`front` 是這一包登記的格（原本 `options` 原位叫 `_seal_tick`、`_seal_options`）；先後在 `core/features.py` 的 `MENU_ORDER`；那兩個委派拿掉；上面寫「留委派」「原位」的以這一句為準。

**第 57 批（分派與標題收接縫，核心批）**：`quick/seal` 是這一包登記的格；委派 `_seal_act` 拿掉（上面寫它的以這一句為準，`(_seal_act, _deliver_seal_results)` 那一對第 28 批就在包裡經 `ctx` 叫了）。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（別節中間的兩處插句（`fame_seal`、`land_seal`，核心 `HOWTO_INSERTS`）），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

## 畫面與狀態列（全部拆包第 66 批）

- 畫面：`web/seal.js`（奪璽卡、碎片卡與獨門行動）、`web/seal.css`（獨門行動，第 67 批；奪璽卡的 `.order-*` 跟軍令、懸賞共用，留 `style.css`）；`sealWatched`、`sealTitle` 留 `app.js`，點擊分派第二輪第 84 批進這支 js。
- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`status` 表 `seal`（`seal_duel`、`seal`、`seal_watch` 三個鍵）。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`seal_use`；`admin_tools`：`seal_emerge`、`seal_stir`、`seal_assign`、`seal_duel`、`seal_fix`、`seal_cancel`、`seal_sink_check`、`seal_mandate`（時間 `shell.time.time()`，引擎不讀時鐘）。`admin_seal_stir` 的委派搬完之後沒人叫（寫進回報）。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：`routes.py` 的 `seal_text`（奪璽單挑的放手一搏，`/api/do/seal_text`，`outlock` 掛鉤）；`GambleVerdict`、`assess_gamble`、保底值照舊經 `shell.battle_instance`，`Scene` 用 `tianxia.core.duel_base.Scene`（單挑包 `duel.Scene` 是它 re-export 的同一個）。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。另外要跑的（`test_for` 挑不到）：`tests/server/test_outlock.py`。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_seal.py`（原 `tests/seal/`）、`test_seal_acts.py`（原 `tests/seal/`）、`test_seal_acts3.py`（原 `tests/seal/`）、`test_seal_acts_web.py`（原 `tests/web/`）、`test_seal_engine.py`（原 `tests/seal/`）、`test_seal_revamp.py`（原 `tests/seal/`）、`test_seal_web.py`（原 `tests/web/`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- 舊模組 → 包少 `skillview`（`gear_rows` 第 88 批改讀核心 `seal_base.on`）。這一包多登記 `admin` 表的 `seal` 格（第 90 批）。
- 另外要跑的：改 `checks.py` 時 `test_for` 帶得到 `tests/core/test_content.py`（PM 定，第二輪 F 波），帶不到 `tests/core/test_content_packs.py`。
