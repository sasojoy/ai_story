# 大勢人物的行動（`tianxia/features/figure_acts/`）

- 做什麼：玩家對大勢人物做的事——挑戰本人（閉門不見、勝算、對手那一路、打一場、打贏的一串〔心得與經驗、他敗走、掉寶物、三階、四階〕、僵持）、護衛犒軍探望（`aid:`）、
  助他一臂或壞他的事（`plan:`）、月旦評三段式的 A、C 兩段、管理者救回人物。全部拆包第 31 批從 `Game` 搬來（24 個方法、388 行）；包名不叫 `figures`：`tianxia/figures.py`（人物表與聲威的規則）留在原位。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「大勢人物的行動」那一節
- 設計稿：`docs/superpowers/specs/2026-10-04-第一季陣營內容-軍令.md` 4.5 與 `2026-10-11-挑戰大勢人物每季都有-design.md`（挑戰本人）、護衛犒軍探望照 Joy 2026-10-17 清單第 6 條、盤算與月旦評是「大勢人物擴充」（`docs/superpowers/plans/` 內該批計畫）；搬家計畫 `docs/superpowers/plans/2026-11-04-大勢人物包-第1批.md`

## 檔案

| 檔 | 內容 |
|---|---|
| `__init__.py` | 登記：前綴 `aid`、`plan` 的 choose 掛鉤（標題一起給）、`bot_always = ("aid:",)`、假人分數 |
| `challenge.py` | 挑戰本人 13 個：`snubbed`、`snubbed_character`、`options`、`odds`、`figure_squad`、`challenge`、`win_reward`、`draw`、`rout`、`treasure`、`tier3`、`tier4`、`held_tier3` |
| `aid_actions.py` | 護衛犒軍探望：`options`、`act`、`title`、`deliver_guard_credits`（同步補名望與心得） |
| `plan_actions.py` | 盤算：`options`、`act`、`title`、`plan_view`（江湖頁的盤算卡）、`place_deeds_view`（此地舊事） |
| `yuedan_actions.py` | 月旦評 A 段（`request`）、C 段（`apply`）；B 段在 `server.yuedan_once` → `yuedan.write` |
| `admin_actions.py` | 管理者「叫回人物」：`fallen`、`revive_figure` |
| `figure_aid.py`、`yuedan.py` | 規則模組（舊名 `tianxia/figure_aid.py`、`tianxia/yuedan.py` 留成指到同一個模組的別名） |
| `bots.py` | 假人看到 `aid:`、`plan:` 都不按（原本 `bot_policy.score` 的 `("ambush", "works", "aid")` 那一行拆出 `aid`） |

## 認領的欄位（`PlayerState`，換季全部跟著新角色重來，沒有帶走的）

`snubbed_until`（閉門不見到幾時）、`figure_wins`（這一季打贏每位人物幾次；本命兵器 `signature_arms.py` 也讀）、`figure_dented`（聲威哪天扣過）、`figure_rare_drops`、`tier3_drops`、
`tier4_wins`、`tier4_challenge_drops`（三階與四階的帳）、`plans_paid`（領過盤算結果的站；寫的是舊模組 `plans.py`）。`treasure_drops` 是寶物的帳，不認領。

**世界狀態**（`WorldState`）：`figure_guards`、`aid_tally`、`guard_credits`、`plans`、`yuedan`、`yuedan_week` 屬於世界，留在原地。

## 還留在核心原位的接縫（理由在 `tests/core/test_feature_boundaries.py` 的 `# figure_acts` 那一段）

- `act:challenge:<人物>`：`_everyday_options` 的選單那一格、`_act` 的按下去、`_action_title`、`_fight_squad` 的對手隊伍——act 子動詞帶後綴接不了 `Verb`（總表第 57 批），Game 留 `_challenge_options`、`_challenge`、`_figure_squad`、`_snubbed_character`、`challenge_odds` 的一行委派。
- 選單末段 `護衛 + features_core.options + 盤算`：護衛那串在包選項之前、盤算在之後，`options` 掛鉤接不了，Game 留 `_aid_options`、`_plan_options` 的委派。
- `sync` 的 `_deliver_guard_credits`：夾在 `_deliver_echoes` 與 `deliver_notices` 之間，留委派（接成 `deliver_notices` 掛鉤，酒肆的會跑在它前面，行狀順序會變）。
- `world.py` 的 `yuedan.tick`、`social.py` 的 `yuedan.line_for`、`figures.py` 的 `figure_aid.restore`：舊模組經別名讀（過渡；第 40 批、第 37 批各自換掉）。
- `bot_policy._stamina_play` 的 `("ambush:set:", "works:", "aid:")`、`models.ALLOW_FAMILIES` 的 `aid:`、`plan:`、`act:challenge:` 字串：核心原位。

## 測試

- 這一包的 `tests/`：`test_figure_aid.py`（護衛犒軍探望，7 條，原 `tests/figures/`，整檔搬）、`test_challenge_season.py`（挑戰每季都有的開關，27 條，原 `tests/core/`，總表附錄甲歸這一包，整檔搬）、`test_figure_acts_smoke.py`（煙霧）、`figure_acts_stage.py`（契約測試擺局面）。
- `test_figure_life_batch3.py`（9 條）**留在 `tests/figures/`**：4 條是月旦評（這一包），5 條是求援委託（`bounties` 的 rallies、`figure_life`，之後各自成包），混合檔不拆。

## 另外要跑的混合檔

混著別的功能、留在原處的（`條數＝碰到這一包的／全檔`，用語法樹數過，數字是粗的）；改這一包時連它們一起跑：

- 挑戰本人與大勢人物：`tests/figures/test_figures.py`（19／62，`challenge_odds`、`win_reward` 在這裡）、  `tests/figures/test_orders.py`（8／85）、`tests/figures/test_figure_life.py`（2／17，`rout`）、`tests/figures/test_admin_timetable.py`（`admin_fallen`、`admin_revive_figure`）、
  `tests/figures/test_figure_attrition.py`（4／9）、`tests/battle/test_rise.py`（4／10）、`tests/figures/test_gentry_allied.py`、`tests/figures/test_figure_life_batch3.py`（4／9，月旦評）
- 打贏的一串：`tests/gear/test_signature_arms.py`（7／25，換掉 `challenge.rout`）、`tests/gear/test_treasures.py`（6／56）、`tests/gear/test_weapons.py`（`tier3`）、
  `tianxia/features/sortie/tests/test_sortie_rewards.py`（`tier4`）、`tests/seal/test_seal_revamp.py`（`figure_squad`）、`tests/seal/test_seal_engine.py`（16／41）、`tests/seal/test_seal_duel.py`（12／27）
- 假人：`tests/bots/test_bot_policy.py` 這一類（`aid:`、`act:challenge:` 的分數）
- 改這一包時：`python scripts/test_for.py --base HEAD tianxia/features/figure_acts/challenge.py`
