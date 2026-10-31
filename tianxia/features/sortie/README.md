# 出陣 `tianxia/features/sortie/`

- **做什麼**：投靠了陣營的人在領地爭奪的區塊上出陣——別人的、中立的攻（打一場，推那一塊的進度），自家的守（零風險，把對面的進度拉下來）；出陣時撞上對面剛在這一塊推過的人是混戰（本人對本人，贏了推得多、輸了白跑）；打完那一下在「剛剛」底下多一塊出陣回報（進度條、一句話、小籤）。出陣沒有自己的開關：地盤（領地爭奪）開著就有。主動搬六包第 1 批（出陣本體、混戰、出陣回報）搬進來；出陣約戰（`sortie_duel`）是第 2 批。
- **導覽**：`docs/guide/行動與地盤.md` 講出陣、出陣回報、混戰的那幾段；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：沒有版本號，四份（都在 `docs/superpowers/specs/`）：`2026-10-14-出陣探索與地盤-design.md` 第二節（出陣本體）；`2026-10-20-輿圖簡化-design.md` 4.3（混戰、翻地與爭搶）；`2026-10-24-減法季-整合設計.md` 4.3（減法季的出陣與約戰）；`2026-10-28-出陣約戰網頁-草圖/`（約戰，第 2 批）。出陣回報是企劃者 2026-10-23 在草稿上選的「寫數字」、2026-10-26 小籤改「寫字」。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`SortieFeature`）：`enabled`＝`territory.on`（`rules.on` 同一個）、`player_fields`／`carried`（換季照帶今天出陣的次數：照帶本身照舊寫在 `Game._reset_player_for_new_season`、不看地盤開不開，同商城；不掛 `on_season_start`——遊戲當下的掛鉤只叫開著的包，地盤關著的那一季就不帶了）；`prefix` 是 None（出陣那一格是核心的 `act:train`） |
| `rules.py` | 純規則與字（原 `tianxia/sortie.py`；那個名字留成別名）：開關、次數、哪一種（攻、守）、灰格的原因、出陣回報 `report`、小籤的字、混戰的字 `CLASH_*` |
| `actions.py` | 原本 `Game` 上的 21 個方法：出陣本體（`sortie`、`sortie_option`、`sortie_line`、`train_title`、`sorties_left`、`sortie_foes`、`sortie_mode_of`、`sortie_mode`、`sortie_progress`、`sortie_host`、`sortie_hold`、`hold_share`）、混戰（`clash_target`、`do_clash`、`melee_record`）、出陣回報（`front_report`）、打贏的獎勵（`sortie_rewards`、`squad_drops`、`sortie_full`、`sortie_rare`、`sortie_drill`） |
| `tests/` | `test_sortie.py`（7 條，含煙霧一條）、`test_sortie_report.py`（8 條，整檔 slow）、`test_sortie_rewards.py`（15 條）：原本在 `tests/acts/`，整檔搬過來；`test_sortie_season_carry.py`（3 條，審查之後加的：換季照帶不看地盤開不開） |

**認領的欄位**（3.5，留在原地）：`PlayerState.sortie_day`、`sorties_today`（換季照帶，`carried`）、`sortie_treasures`、`sortie_horses`（出陣打贏掉寶物、良駒一季的上限，換季重來）；`WorldState.clashes`、`clashed`（混戰寫的那幾筆，跟截殺共用 `raids`、`raided` 那一本）；`JournalEntry.front`（`FrontReport`、`FrontRow`、`FrontChip`）；`Config.sortie`（`SortieRules`，約戰的欄位一起，第 2 批）。

**Game 上留的一行委派**（13 個，9 個私有；server、假人、腳本、測試與核心原位還在叫）：`sorties_left`、`_sortie_foes`、`sortie_mode`、`sortie_progress`、`_sortie_host`、`_sortie_hold`、`_sortie_line`、`_melee_record`、`_sortie_rewards`、`_train_title`、`_sortie_mode`、`_sortie_option`、`_sortie`。包裡只有 `sorties_left`、`_sortie_hold` 經 `ctx` 叫（`tests/bots/test_bot_policy_conquest.py` 換掉 `Game.sorties_left`、`scripts/sim_trend_sources.py` 換掉 `Game._sortie_hold`）。

**還留在原位的接縫（過渡；批次表第二節，第 11 批一次收）**：`Game._act` 的 `act:train` 分派（出陣開著走 `_sortie`，序章的雪恥與關著的季走 `_train`；並肩出陣包在外面）、`_everyday_options` 那一格（雪恥／遊歷／出陣、散人與不在爭奪之列的灰格）、`action_notes` 底下那一行、`_squad_encounter` 的 as_sortie（打贏回頭叫 `_sortie_rewards`）、`_push_progress`（地盤）寫、`_sortie` 讀的四個旗標（`_clash_won`、`_sortie_marked`、`_sortie_moved`、`_sortie_flipped`，服務清單的寄放段）、守勢行動（`_duty_option`、`_duty`）、輿圖（`map_state`、`_map_foes`）、約戰的 6 個方法；`server.main_view` 的 `sortie`、`front`、`sortie_card`、`sorties` 四個鍵（鍵的順序算行為）與 `may_judge_fight`；`bot_policy` 的出陣那幾段（`_train_value`、`_sortie_win`、`_outmatched`、`_focus_hop`……，這一批沒拿前綴，照舊叫 Game 的委派）；網頁一行沒動。`tests/core/test_feature_boundaries.py` 的 `GAME_DIRECT`、`GAME_DELEGATE_CALLERS` 逐條寫理由。
**改這一包時 `test_for` 挑不到、要另外跑的**（混在別人檔裡的測試，這一輪不拆，批次表第二節；dev/sortie-1 審查用突變量過）：改包的檔只挑這一包的 `tests/` 與核心契約，下面這幾個蓋著搬過來的程式卻不在包裡——
- 混戰（`clash_target`、`do_clash`、`melee_record`）：`tests/acts/test_conquest_flip.py` 原 `test_conquest_clash` 那一段（贏寫成平、不看冷卻、不記行狀都只有它紅）、`tests/ranger/test_raid.py::test_a_melee_and_an_ambush_note_the_rivals_name_to_keep_too`（`Game._melee_record`）。
- 一類一顆之前的出陣銀兩與三成（`sortie_drill`）、守不給銀兩：`tests/acts/test_econ_gather_sortie.py`。
- 照舊的合併閘門另外要的出陣 slow：`tests/bots/test_bot_policy_conquest.py`、`tests/web/test_core_loop_web.py`、`tests/acts/test_sortie_duel*.py`。
- 一起跑：`scripts/test_for.py --base <分支> <改的包檔> tests/acts/test_conquest_flip.py tests/ranger/test_raid.py tests/acts/test_econ_gather_sortie.py`（直接給的測試檔連 slow 一起跑）；要不要讓 `test_for` 把這幾個混合檔算進包，交 PM 定。

**過渡 import**：`actions.py` 17 行、`rules.py` 6 行、`__init__.py` 1 行 import 還沒搬的舊模組（`conquest`、`territory`、`orders`、`treasures`……，註「過渡：待搬」）；`sortie_duel`、`atlas`、`bounties`、`howto`、`mapview`、`orders`、`bot_policy`、`server` 照舊 `from tianxia import sortie`（別名）。
