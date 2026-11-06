# 體力玩法 `tianxia/features/stamina_plays/`

- **做什麼**：後期體力玩法第一批（Joy 2026-10-16）的兩樣。**設伏劫道**：花體力守在一段路上，敵對的人走過就打一場（本人對本人，同截殺），贏的搶走輸的一點銀兩與素材；**屯糧練兵**：第一季規則開著的季，兩軍在自家控制的地方屯糧，下一場時刻表決戰開集結那一刻換成起點的偏移（修築工事 2026-10-27 跟著舊拔河拿掉）。
- **導覽**：`docs/guide/行動與地盤.md` 的「後期體力玩法」那一段（體力玩法〔設伏、屯糧〕與閉關在這一塊；PM 補導覽的標題，這一批沒動 `docs/guide/`）。
- **設計稿**：後期體力玩法第一批（Joy 2026-10-16；`docs/guide/行動與地盤.md` 記規則，沒有單獨的設計稿檔，沒有版本號），數字在 `Config.ambush`、`Config.stockpile`。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`StaminaPlaysFeature`）：`enabled`＝一律開著（`choose`、`bot_pick` 原位本來就不看開關）、`prefix`＝`ambush`、`works`（`choose`：標題先算，設伏「設伏・地點」「收伏」、屯糧「屯糧練兵・地點」）、`bot_pick`、`bot_always`＝`ambush:`、`works:`、`world()`（世界層 `muster` 的 `works` 那一格） |
| `ambush_rules.py` | 設伏的純規則（原 `tianxia/ambush.py`；那個名字留成別名）。`MOVE_BLOCKED` 在核心 `core/services.py`，這裡 re-export |
| `works_rules.py` | 屯糧的純規則（原 `tianxia/works.py`；那個名字留成別名）；`on_muster` 是世界層那一格的身體 |
| `ambush_actions.py` | 原本 `Game` 上的 `_ambush_act`、`_ambush_expire`、`_ambush_check`、`_ambush_fight`、`_ambush_spoils`、`_ambush_record`；`Game` 留 4 個一行委派（`_ambush_expire`、`_ambush_check`、`_ambush_spoils`、`_ambush_record`） |
| `works_actions.py` | 原本 `Game._works_act`（只有 `choose` 叫，沒有委派） |
| `actions.py` | 原本 `Game._stamina_play_options` 的前半（設伏／收伏、屯糧兩段選項）；`Game._stamina_play_head` 留一行委派 |
| `bots.py` | 假人的分數（原 `bot_policy.score` 的 `ambush`／`works` 那一段）：一律 `None`（由 `take_turn` 的 `_stamina_play` 做） |
| `tests/` | `test_stamina_plays.py`、`test_stamina_plays_off.py`（原 `tests/acts/`，整檔搬）、`test_stamina_plays_smoke.py` |

**認領的欄位**（3.5，留在原地）：`PlayerState.ambush`（`AmbushPost`，換季照 `_reset_player_for_new_season` 重來）；`WorldState.ambushes`、`supply`、`forts`（`Fort`，修築工事拿掉後欄位留著，只在 `state.py` 註解提到）；`BattleState.supply_lean`（決戰包的，屯糧只寫它）；`Config.ambush`（`AmbushRules`）、`Config.stockpile`（`StockpileRules`）。
**世界層的格**（core_world：全部拆包第 25 批；第 39 批換主人）：開集結那一刻結算屯糧是世界層 `muster` 的 `works` 那一格（`__init__.py` 的 `world()` → `works_rules.on_muster`；位置在 `WORLD_ORDER` 的「起點」之後、「玉璽」之前，一個字不動；不問 `enabled`，判斷在 `on_muster` 裡）。
**選單順序（不能改成 `Feature.options`）**：「設伏／收伏 → 屯糧 → 護衛（`_aid_options`）→ 功能包的選項（`features_core.options`）→ 盤算（`_plan_options`）」。設伏屯糧改成 `Feature.options` 會排進 `FEATURES` 的順序、跑到護衛之後。所以 `Game._stamina_play_options` 留著當接縫，前半叫 `actions.options`。
**接縫在原位的位置不能動**（位置就是行為）：`sync` 的 `_ambush_expire`（`drop_shops` 之後、`_arrivals` 之前）、`_arrivals` 迴圈中途的 `_ambush_check`（每換一段才查）、移動被擋（`engine.py` 的 `_move_option`，讀 `p.ambush` 與核心的 `MOVE_BLOCKED`）。
**過渡**：`ambush_rules.py` import `bounties`（`has_prey`、`hostile`，第 45 批懸賞榜成包）、`atlas`（第 50 批）；`ambush_actions.py` import `annals`（行狀）；設伏贏了揭通緝交差走 `ctx._raid_bounty`（服務清單三、過渡，主人懸賞榜）。假人的 `_stamina_play`（`bot_policy.py`）挑 `ambush:set:`、`works:`、`aid:`，叫 `game.choose` 公開動作，留在原位。`tianxia/howto.py`、`scripts/measure_stamina_plays.py`、`test_conquest_flip.py` 用舊名 `ambush`、`works`（別名，同一個模組物件）。
**審查守的**：`encounter.resolve_encounter` 一律用模組屬性叫（`same_behavior` 的 `stamina` 軌換掉這個屬性強制伏兵必勝／必敗）；`_ambush_fight` 的亂數用 `random.Random(f"設伏|…")`、不動 `Game.rng`；兩個人之間的函式（`fight`、`record`）帶兩個 ctx。
**另外要跑的混合檔**（設伏、屯糧的用法散在別人的檔裡，這一輪不拆；改包任一檔時 `test_for` 挑不到，合併閘門要跑「相關的 slow」就靠這一張清單）：
- `tests/gear/test_four_tiers.py`（叫 `_ambush_spoils`）、`tianxia/features/peers/tests/test_raid.py`（叫 `_ambush_record`）、`tests/acts/test_conquest_flip.py`（import `works` 舊名）。
- `tests/seal/test_seal_revamp_sidedoor.py`（slow 的 `test_an_ambush_report_names_the_rivals_bare_power`，借用包的測試檔 `test_stamina_plays` 的 `_player`、`_plays_on`、`_reload`、`_set`；那幾個輔助函式改名或搬動時它會壞）。
- 世界層 `muster` 代叫（`works` 那一格）：`tests/core/test_world.py`、`tests/battle/test_fronts.py`、`tests/figures/test_timetable.py`。
- 一起跑：`pytest tianxia/features/stamina_plays/tests tests/gear/test_four_tiers.py tianxia/features/peers/tests/test_raid.py tests/acts/test_conquest_flip.py tests/seal/test_seal_revamp_sidedoor.py tests/core/test_world.py tests/battle/test_fronts.py tests/figures/test_timetable.py -n 4 -m "slow or not slow"`。

**行狀記一筆改 import 核心**（全部拆包第 29 批之二）：本包原本「包 → `tianxia.annals`」的過渡 import 改成 `from tianxia.core import annal_base as annals`（核心本體，不算過渡，行尾註拿掉「過渡：待搬」）；上面各處寫到 `annals` 的過渡句（含處數）是這一批之前的舊寫法，現在那幾處不算過渡，數字一律以 `python tests/core/test_feature_boundaries.py` 重印為準（舊名 `tianxia/annals.py` 是指到列傳包 `standing.py` 的別名，那一份 re-export 核心那一半）。
