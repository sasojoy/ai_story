# 玉璽碎片（`tianxia/features/seal/`）

七片傳國玉璽碎片的季流程：時刻表決戰集結那一刻擲現世與璽動、領地爭奪的季開季藏一片與探索撿到、時刻表決戰收場（挑挑戰者、現世的得主、喚回）、補送到每個人手上、天命之季與天命之爭、換季的隱沒與散去，與管理者的強制現世（現在藏一片）、隱沒判斷、蓋天命之季。全部拆包第 27 批「玉璽一」搬進來（引擎那一半；網頁 `web/` 第 3 階才切，`app.js` 歸這一包的那幾個是第 66 批）。

**這一批沒搬的**（第 28 批「玉璽二」）：碎片卡（`seal_view`）、七種獨門行動（`seal_use`）、奪璽單挑（`tianxia/seal_duel.py`、`_seal_challenge`、`_seal_challengers`、`_seal_spectators`、`_seal_side_of`、`_my_seal_duel`、`_seal_tick`、`_seal_act`、`seal_gamble`、`seal_duel_card`、`seal_watch`）、`seal:` 前綴與 `bot_policy` 的 `seal:` 那一段、管理者的指定、強制璽動、開單挑、取消單挑、管理頁的玉璽一組（`admin_seal_choices`）。璽效查詢 `tianxia/seal_acts.py` 是第 51 批。

- 導覽：`docs/guide/玉璽碎片.md`。
- 設計稿：`docs/superpowers/specs/2026-10-11-玉璽碎片-design.md`（現世、璽動、挑人、易手、隱沒、抄本、天命之季）、`docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md`（常駐效果、持有者平時藏起來）；領地爭奪設計 3.9、4.8（藏一片、探索撿到）。
- 計畫：`docs/superpowers/plans/2026-11-07-玉璽包-第1批.md`。

## 裡面有什麼

- `seal.py`（原 `tianxia/seal.py` 整份；舊名留成指到這裡的 `sys.modules` 別名，換掉的屬性兩邊都看得到——`tests/acts/test_conquest_rules.py` 換 `seal.find`、`scripts/measure_seal.py` 換 `seal.tier_for`、`seal.lean_shift`，`scripts/same_behavior.py` 的 `relic` 一軌換 `seal.secrets.token_hex`）：碎片的規則與字句。擲骰一律 `dice`（密鹽｜天機｜用途｜…），不碰 `Game.rng`。
- 核心與決戰包「不得不讀」的那一小半在**核心本體** `tianxia/core/seal_base.py`（PM 認定甲案，同第 34 批 `omen_base`、第 40 批 `smith_base`）：`on`、`revamp_on`、`filled`、`key`、`holders`、`mandate_event`、`mandate_battle`、`is_mandate_battle`、`mandate_now`、`deserted`、`threshold`、`challenger_ok`、`hint_names`、`merit_hint`、`stir_text`、`lean_shift`、`lean_text`、`shift_text`、`chronicle_block`、`sink_text` 與它們的字句；`seal.py` re-export 同一批函式物件（名字一個不改）。讀它的：核心的 `world.evaluate_ending`、`world.end_season`、`Game.admin_resolve_event`、`Game.chronicle_text`，決戰包的 `view.py`、`progress.py`。`tier_for`、`find` 不搬去（測試、量表換掉的，只有這一包與第 28 批的 Game 方法讀）。`lean_shift` 搬去了：這一包的 `seal._mandate_muster` 照模組屬性找、`measure_seal` 換得到；決戰畫面讀 `seal_base` 那一份（參數是集結那一刻的快照，算出來一樣）。
- `actions.py`：原本 `Game` 上的季流程——`copy_heirloom`（抄本照登記重抄）、`seal_find`（探索撿到）、`seal_bare`（戴著碎片時不含碎片的份量快照）、`mandate_weight`（天命之爭份量加權）、`deliver_results`（補送）、`file_seal`（奪璽單挑寫成戰報與紀錄）、`mandate_settle`（定天命）、`settle`（時刻表決戰收場）。包裡互叫直接叫；叫回 `Game` 的經 `ctx`：第 28 批的 `_seal_challenge`、自己的委派 `_mandate_settle`（`measure_seal` 換 `Game._mandate_settle`）。
- `admin.py`：`emerge`（強制現世；領地爭奪的季改成 `hide` 現在藏一片）、`sink_check`（隱沒判斷）、`mandate`（蓋天命之季：`now`、`next`、`cancel`）。
- `season.py`：原本核心 `sqlite_world` 的三段——`stamp_cache`（開季藏一片）、`stamp_mandate`（換季蓋天命之季的章）、`retire`（舊季收尾：隱沒、沒收場的奪璽單挑記成未分勝負、天命之季過後七片散去）。直接改傳進來的 `SharedWorldState`。
- 掛鉤（`__init__.py`，都不問 `enabled`，格裡自己問 `content.seal`、`Config.seal.enabled`：**散去不看開關、隱沒看開關**）：
  - 事件（`bus()`；位置照核心 `BUS_ORDER`）：`outing` 的 `seal`（探索一顆收尾撿碎片，排在打探懸賞之後；回 `list[str]`）、`battle_end` 的 `seal`（時刻表決戰收場，回 `None`）。發布點照舊在探索包 `explore_actions.explore_one`、決戰包 `progress.settle_showdown`。收場之後的補送 `ctx._deliver_seal_results()` 是查詢服務，**不併進 `battle_end`**（第 26 批認定第 3 條）。
  - 世界層（`world()`；位置照 `WORLD_ORDER`、簽名照原樣）：`muster` 的 `seal`（集結那一刻擲現世與璽動，`seal.on_muster`；「集結開始」就是這一格、不另開事件）、`open` 的 `seal.cache`、`next` 的 `seal.mandate`（`content.seal` 與 `Config.seal.enabled` 都開著才叫）與 `seal.cache`、`retire` 的 `seal`（回寫了上一季的江湖史沒）。`state.seal.opened_real = now` 那兩行是核心寫核心的資料，留在 `sqlite_world`。
  - 效果（`effects()`；位置照 `EFFECT_ORDER`）：`runic`（符文殘片；在叫的那一下才從 `tianxia.rules` 拿 `season_one`，PM 認定不統一成 import 時綁定）、`shard`（舊鏈的玉璽碎片，不認領欄位）。
- `name = "seal"`、`prefix = None`（沒有選項、選單、店面、路由）、`enabled` 照 `seal.on`、`content = ("seal.json",)`。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields = ("heirloom", "seal_seen")`：傳承那一格的抄本、補送到全服登記第幾號。
- `carried = ("seal_seen",)`（`tests/core/test_contract_features.py::test_a_new_season_keeps_only_what_the_package_carries[seal]` 實跑定）：核心換季（`Game._reset_player_for_new_season`）兩個都照帶，可是 `heirloom` 換季後建 `Game` 時照全服登記重抄（`copy_heirloom`），弄髒的值會被清掉，所以不算帶走的。
- 包外讀寫這兩欄的（第 34 批認定第 9 條，照實記、排批）：核心換季重設（`_reset_player_for_new_season` 那兩行，核心本體，不動）；核心 `_lose_silver`（讀 `heirloom.name`，碎片保銀那一句；第 55 批或銀兩出口那一批看）；共用層 `treasures`（`amount`、`power_scale` 等讀傳承那一格；第 51 批與璽效查詢一起看）；`skillview`（`SHARED_LATER`，讀）；酒肆包 `features/tavern/rules.py`（讀；酒肆下一次動到時改查詢服務）；探索包測試 `test_explore_one.py`（讀）。陣營包 `defection` 不讀這兩欄。
- **這一包讀別包的欄位**：`actions.seal_find` 讀探索包認領的 `PlayerState.explore_seq`（這個人第幾次探索，撿碎片的骰子用）——排給第 55 批（補算收接縫）改查詢服務。
- 資料在核心、不認領：`SharedWorldState.seal`（全服登記）、`seal_duels`、`jade_seal_fragments`（舊鏈的碎片），`WorldState.mandate`、`mandate_result`。

## 委派與留在原位的接縫（理由在 `tests/core/test_feature_boundaries.py` 的 `# seal` 那一段）

`Game` 留 11 個一行委派：`_copy_heirloom`、`_deliver_seal_results`、`_seal_bare`、`_mandate_settle`（核心原位叫）、`_mandate_weight`（決戰包經 `ctx`）、`_seal_find`、`_seal_settle`、`_file_seal`（**只剩測試叫**：寫進手冊「拆完之後的收尾：只剩測試叫的委派」，第 42 批認定第 3 條）、`admin_seal_emerge`、`admin_seal_sink_check`、`admin_seal_mandate`（殼的 `ADMIN_ACTIONS` 與測試）。`_admin_seal_hide` 只有強制現世叫（包內互叫），不留。

- `GAME_DELEGATE_CALLERS` 9 對：`_battle_marks → _seal_bare`（戰力快照是單打服務）、`admin_resolve_event → _mandate_settle`（時刻表的救場工具是核心）、`sync → _copy_heirloom`、`sync → _deliver_seal_results`、`_drop_stale_references → _copy_heirloom`（**接不了 `on_sync`／`on_drop_stale` 是開關**：那兩個掛鉤只問開著的包，碎片關著時 `_copy_heirloom` 照樣要叫、傳 `None` 把抄本清掉；第 42 批認定第 7 條；第 55 批收）、第 28 批的 `_seal_tick`／`_seal_act`／`seal_gamble`／`admin_seal_cancel` 各配 `_deliver_seal_results`。
- `GAME_DIRECT` 13 筆（過渡：第 28 批收）：還沒搬的第 28 批方法本體直接讀玉璽包的規則與字句（`_seal_challenge`、`_seal_challengers`、`_seal_spectators`、`_seal_side_of`、`_my_seal_duel`、`_seal_tick`、`seal_view`、`seal_use`、`seal_duel_card`、`seal_watch`、`admin_seal_assign`、`admin_seal_duel`、`admin_seal_choices`）。engine 經舊名 import，改叫 `seal_rules`（同 `prologue_rules`、`tavern_rules`：戰力快照 `_battle_power`、`_battle_scores`、`_spar_power` 的參數也叫 `seal`）。
- 選項前綴 `seal:`（碎片卡、獨門行動、奪璽單挑）在 engine 的 `options`、`choose`、`_shop_open`、`_seal_options` 與 `bot_policy.score`：第 28 批。

## 過渡（手冊 3.11）

- 包 → 舊模組：`actions.py` → `seal_duel`（奪璽單挑的字 `WIN_VERDICTS`、`side_tier`、`CALL`、`CALL_QA`；第 28 批）、`seal.py` → `atlas`（函式裡，藏碎片要認大區；第 50 批）。
- 舊模組 → 包（經舊名 `tianxia.seal`）：engine（`seal_rules`）、`bot_runner`（叫醒持璽的假人）、`howto`、`skillview`、`seal_duel`、`seal_acts`（函式裡）、殼 `server.py`、`run_bots.py`（`ensure_salt`）、`scripts/measure_seal.py`（也直接換包的 `actions.settle`）、`measure_tactics.py`、`same_behavior.py`。`SHARED_PENDING` 的四條 `(conquest|figures|figure_life|plans, seal_acts)`：`seal_acts` 函式裡 import `seal`，連帶載入玉璽包。

## 內容歸屬

`content/seal.json`（七片）；`content.py` 照舊讀、照舊驗（`_validate_seal` 留原處、不接 `check_content`，第 34 批認定第 2 條）。`Config.seal`（`SealTuning`）留在 `models.py`。時刻表上標 `seal`（`emerge`／`stir`）與 `mandate_only` 的決戰在 `content/timetable.json`；`content.mandate_timetable` 只准 `timetable.py`、`content.py`、`models.py` 與 `core/seal_base.py` 讀（`test_seal_mandate.py` 守門）。
