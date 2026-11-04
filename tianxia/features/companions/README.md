# 人物情誼（`tianxia/features/companions/`）

跟歷史人物打交道的事：招募同伴與名下（歷史武將同行）、人物心意（勸他做什麼）、託付與勸降、來信與委託、人物頁。全部拆包第 19 批（人物情誼一）搬進來；人物對話與 NPC 智能（`companion_agent`、`parley`，`talk:`、`parley:`）是第 20 批，交友求見是第 21 批。

- 導覽：`docs/guide/大勢人物與賽季.md` 的「人物情誼（功能包 `tianxia/features/companions/`）」那一節，規則在同一份的「人物心意與託付」「人物活起來」。
- 設計稿：沒有版本號——減法季整合設計 5.4、5.5、5.9（主機側計畫 Task 6-1、6-2：心意與託付，企劃者 2026-10-24）；大勢人物擴充第二批「人與人」第五節（書信，https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2）；歷史武將同行 `docs/superpowers/specs/2026-10-18-歷史武將同行-design.md`。
- 計畫：`docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md`。

## 裡面有什麼

- `actions.py`：原本 `Game` 上的 29 個方法（名字去掉前導底線），加上原位搬來的 `recruit_options`（選單招募那一段）、`deliver_mail`（同步書信那一格）、`errand_ask`（勸降只叫出輸入框）、`errand_title`（`choose` 掛鉤的標題）。
- `stances.py`（行動那一半：跟人物說話記一筆、人物頁、行狀、假人挑心意）、`errands.py`、`letters.py`：舊名 `tianxia/stances.py`、`errands.py`、`letters.py` 留成 `sys.modules` 別名（同一個模組物件，`monkeypatch.setattr(letters, "write", …)` 照樣有效）。
- **心意的世界那一半在共用規則層 `tianxia/stance_world.py`**（這一週的計數、誰照哪一個做事、門檻、換手、每週歸零）：核心的 `rules`、事件檢定與舊模組 `world`、`figures`、`events` 讀它；`stances.py` re-export，`from tianxia import stances; stances.check(...)` 照舊。
- `routes.py`：`/api/figure`（原本在 `server.py`）。
- 掛鉤：`enabled` 一直是 True（招募 `Config.companions`、書信 `Config.figure_life.letters`、心意與託付 `Config.jianfa` 各有自己的開關，包本身沒有總開關）；`choose`（`errand:` 那幾顆）；`routes`；`bot_always`（`errand:`：整季機器人不收託付，原本寫在 `bot.pick` 的清單）；`player_fields`。
- **沒有 `bots.py`**：`bot_policy.score` 沒有 `errand:` 那一段（`take_turn` 打分數之前就濾掉，那一行留著）；假人直接記一筆心意走 `Game.voice_stance`（`bot_policy.voice_stance` 叫，不是選項）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`stance_notes`、`errands`、`letters`、`letter_day`、`letter_seq`、`cheers`（換季全部跟著新角色重來）。`parted_done`（同伴回江湖的減半記號）第 7 批決戰包認領了，寫它的 `settle_partings` 還在決戰包，照留。
- 季上的：`WorldState.stance_counts`、`stance_active`、`stance_week`（世界那一半讀寫，`stance_world`）；全服名下：`CompanionProgress`（共用規則層 `roster`）。
- 內容：`content/events/stances.json`（`content` 宣告；`content.py` 照舊讀）；人物表上的 `stances`、`errands` 在 `content/figures.json`、驗證在 `content.py`（核心，這一批不動）。

## 委派與留在原位的接縫

`Game` 留 29 個一行委派（26 個原本的方法＋`_recruit_options`、`_deliver_mail`、`_errand_ask`；`add_to_team`、`remove_from_team`、`release_companion` 帶 `@_not_while_preparing`，裝飾器第 23 批進核心）；`_errand_act`、`_errand_reward`、`_errand_persuade` 只有包裡叫，沒有委派。`Game.SELF_IN_TEAM`、`FOLLOWER_IN_TEAM` 指到包的常數（`test_ranks` 讀）；`Game._persuade_said` 是寄放（`choose` 前段與包都讀）。

核心原位碰這一包的都沒有第 11 批的掛鉤，改叫委派、記進邊界測試的 `GAME_DELEGATE_CALLERS`（11 對），**沒有新增 `GAME_DIRECT`**：

- 選單（`_everyday_options` × `_recruit_options`、`_errand_options`）：選項的順序算行為，`options` 掛鉤在體力玩法之後。
- 同步（`sync` × `_stance_annals`、`_deliver_mail`）：紀錄與行狀的先後算行為，`deliver_notices`、`on_sync` 位置不對。
- `act:recruit`、`act:recruit:<id>`（`_act` × `_recruit`、`_recruit_one`）：核心 `act:` 的子動詞，第 57 批接進 `Verb`（`recruit:<id>` 那一格要照前綴認）。`choose` 的 FB-363（慢一步按到有主的人）與 `_action_title` 的招募那一格也留給第 57 批（讀的是共用規則層 `roster`）。
- 勸降只叫出輸入框（`choose` × `_errand_ask`）：查完選單、建紀錄之前，同 `battle:`（第 7 批 PM 認定第 1 條），第 57 批一起接。
- 人物對話（`_talk`、`_road_say` × `_stance_before`、`_stance_credit`）：第 20 批搬進同一包。

別的舊模組經別名碰這一包（3.11）：`bot_policy`、`companion_agent`（`stances`）、`weekcard`（`errands.step_items`）、`bounties`（`letters.thank`）、`server`（`letters.mail_day`、`letters.write`；鎖外重寫信、勸降的三段式照舊在殼）。`server` 的 `main_view`、`MAIN_ACTIONS`（`letter_read`、`letter_decline`）、`MENXIA_ACTIONS`（`join`、`leave`、`release`）照舊叫 `Game` 委派（總表第 66、68 批）。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組 8 處：`actions.py` 第 9 行（`annals` 第 29 批、`figures` 第 40 批）、`errands.py`（`atlas` 第 50 批、`figures`，函式裡）、`letters.py`（`bounties` 第 45 批、`figure_life` 第 40 批、`atlas`，函式裡）、`stances.py`（`figures`，函式裡）。
- **`letters._feast_letter` 問 `figure_life.feast_invites`**：書信不能 import 宴客包（包 import 包），`figure_life` 本來就延後 import 宴客包設宴；第 40 批 `figure_life` 收進共用規則層時連同設宴一起處理。
- `figure_life.spread` 記道賀走核心 `services.note_cheer`（`letters.note_cheer` 是同一個函式）；`_settle_partings` 是決戰包的查詢服務（服務清單二）。
- 服務清單（`tianxia/core/services.py`）這一包加的：一、共用 `_deed_points`、`_apply`、`note_cheer`、`CHEERS_KEEP`；二、查詢 `_settle_partings`、`_recruit_target`、`_recruitable_here`；四、寄放 `_persuade_said`。

## 測試

- 這一包的（第 19 批整檔搬進來，共 135 條，全部不是 slow，`-n 4` 約 23 秒）：`tests/test_companions.py`（17：十五位、招募、放走、叛投帶不走）、`test_recruit_gate.py`（5：情誼門檻）、`test_errands.py`（13）、`test_errands_fix6.py`（16）、`test_errands_weekcard.py`（4）、`test_stances.py`（21）、`test_stances_bots.py`（5）、`test_stances_fix6.py`（9）、`test_stances_server.py`（7，連 `/api/figure` 與勸降三段式）、`test_stances_tie.py`（17）、`test_relations_letters.py`（20：書信與委託；前半測共用規則層 `relations` 與人物倒下的反應，同第 22 批 `test_newbie_hours` 的做法，照總表歸這一包）、`test_companions_smoke.py`（1）。`tests/kit/stances_kit.py` 留在 kit（第 20 批的測試也用）。
- **`test_for` 挑不到的、另外要跑的**（這一輪不搬、不拆）：
  - 改世界那一半（`tianxia/stance_world.py`）：共用規則層只挑自己檔名的測試＋煙霧＋邊界（總表第六節第 5 條），沒有 `test_stance_world`——連這一包一起跑。
  - 網頁（第 3 階跟網頁檔一起搬）：`tests/web/test_errands_web.py`（4，slow）、`test_opening_web.py`、`test_hero_mates_web.py`（`from test_companions import _player`）。
  - 混著別的功能的：`tests/core/test_engine.py`（名下）、`tests/battle/test_ranks.py`（部下那一句）、`tests/battle/test_companions_battle.py`（第 7 批，同伴隨你出陣）、`tests/server/test_server.py`（換掉 `Game.roster_lines`、`remove_from_team`）、`tests/server/test_web_push.py`（09:00 來信）、`tests/season/test_real_content.py`（`_recruit_targets`）、`tests/figures/test_figure_life.py`、`test_figure_life_batch3.py`（道賀、邀宴）、`tests/core/test_jianfa_switch.py`、`tests/bots/test_zh.py`、宴客包 `test_feast.py`、引導包 `test_opening.py`；第 20 批的 `tests/ranger/test_parley.py`、`tests/figures/test_parley_two.py`、`tests/bots/test_companion_agent.py`（對話記心意）。
  - 改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/companions/actions.py tianxia/stance_world.py tests/web/test_errands_web.py tests/web/test_opening_web.py tests/web/test_hero_mates_web.py tests/core/test_engine.py tests/battle/test_ranks.py tests/battle/test_companions_battle.py tests/server/test_server.py tests/server/test_web_push.py tests/season/test_real_content.py tests/figures/test_figure_life.py tests/figures/test_figure_life_batch3.py tests/core/test_jianfa_switch.py tests/bots/test_zh.py tianxia/features/feast/tests/test_feast.py tianxia/features/guide/tests/test_opening.py tests/ranger/test_parley.py tests/figures/test_parley_two.py tests/bots/test_companion_agent.py`。
- 前後一字不變：`scripts/same_behavior.py` 的 `companions` 一軌（`--tracks companions`）。
