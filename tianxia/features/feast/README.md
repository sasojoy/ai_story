# 宴客 `tianxia/features/feast/`

- **做什麼**：大勢人物設宴（季的事）、玩家入席敬酒（固定的三句或自己寫一句、模型鎖外評分）、情誼照分數漲、散席時席間最佳那一句上天下大事、那個人補名望。第 1 階多搬的「有按鈕的小包」（開發規範手冊 3.10），驗 `options`、接管選單（`menu`）、`choose`、`on_sync`、`bot_pick` 這幾個商城用不到的掛鉤。
- **導覽**：`docs/guide/大勢人物與賽季.md` 的「宴客（功能包）」那一節；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：大勢人物擴充第三批「多人同服的玩法」（https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2）第 1 版（手冊之前的稿，沒有版本號），數字在 `Config.figure_life` 的 `feast_*`。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`FeastFeature`）：`enabled`＝宴客開著或這一季還有擺過的宴、`options`（入席）、`menu`（坐在席上）、`choose`（`feast:`，標題先算）、`on_sync`、`bot_pick`、`bot_always`＝`feast:` |
| `rules.py` | 純規則（原 `tianxia/feasts.py`） |
| `actions.py` | 原本 `Game` 上的 `_feast_seat`、`_feast_options`、`_feast_menu`、`_feast_act`、`feast_*`；`Game.feast_free_text_prompt`、`feast_text_request`、`feast_toast` 掛在 `game_api.py` 的表 |
| `bots.py` | 假人的分數（原 `bot_policy.score` 的 feast 那一段）：入席 8、敬酒 50、離席不按 |
| `tests/` | `test_feast.py`（原 `tests/figures/test_figure_life_batch3.py` 的「宴客」那一段）、`feast_stage.py`（契約測試擺局面）；第 271 批新開的 `test_feast_shell.py`（4 條，走真路由 `/api/do/feast_text`；(a)(b) 把 `feasts.score` 換成回 100、(c-2) 換成先讓那一場散了再回分數：`test_my_own_toast_that_crosses_an_affinity_mark_writes_the_deed_in_the_same_request`〔(a) 情誼 18 敬到 23，這一下的存檔就有「跟許劭的情誼到了 20。」、`annals_mark` 記 23、回話也寫進 `GameState.log`〕、`test_my_own_toast_that_crosses_no_mark_replies_the_same_and_is_logged`〔(b) 0 敬到 5：回話一字不變、照舊一則「宴客・許劭」、沒有情誼那一筆行狀、`GameState.log` 尾巴多這兩句〕、`test_a_toast_turned_away_before_the_model_says_the_same_line_and_writes_nothing`〔(c-1) A 段擋下（沒坐在席上）「你不在宴席上。」：紀錄、行狀、`GameState.log`、那一場的敬酒都不多〕、`test_a_toast_turned_away_after_the_model_says_the_same_line_and_only_logs_it`〔(c-2) C 段重驗擋下（評分的時候那一場散了）：回的那一句照舊、紀錄行狀敬酒都不多，那一句寫進 `GameState.log`〕；拿掉 `g._log` (a)(b)(c-2) 紅、(c-1) 綠） |

**認領的欄位**（3.5，留在原地）：`PlayerState.feasting`、`feasts_paid`（換季跟著新角色重來）；`WorldState.feasts`、`feast_seq`（這一季的宴席）；`Config.figure_life.feasts`、`feast_*`。`models.py` 序章不出現的前綴 `feast:join:`。
**世界層的格**（core_world：全部拆包第 25 批）：散席（季的推進；原本 `world.py` 直接叫 `feasts.settle`）是世界層 `step` 的 `feast` 那一格（`__init__.py` 的 `world()` → `rules.world_step`；夾在人物行事與盤算之間，先後在核心的 `WORLD_ORDER`；不問 `enabled`，同原位「開關關著也照散」）。
**世界層 `life` 那一格**（core_world2：全部拆包第 40 批）：設宴（原本 `figure_life.tick` 每一輪每一位對話人物直接叫 `feasts.maybe_open`）是世界層 `life` 的 `feast` 那一格（`__init__.py` 的 `world()` → `rules.maybe_open`；`figure_life.tick` 一輪取一次掛鉤，每一位對話人物先設宴、再求援，一位一位穿插，先後在核心的 `WORLD_ORDER`；包沒登記時不跑）。宴席「讀」的那一半（`on`、`find`、`is_open`、`open_feasts`、`hosting`、`toasted`、`_key`）搬到核心的 `tianxia/core/feast_base.py`，`rules.py` 照原名 re-export 同一個物件；`figure_life`（共用規則層）與 `letters.py` 邀宴（經 `figure_life.feast_invites`）改讀它，不再 import 這一包。
**還沒接掛鉤的**：`main_view` 的 `free_text`／`free_op` 叫 `Game.feast_*`（三段式 `feast_text` 第 69 批進了 `routes.py`，見最後一段）；坐在席上的場景卡第二輪第 91 批起走 `SCENE_ORDER`（`__init__.py` 的 `scenes()`）。`rules.py` import 共用層 `seal_acts`。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：新開的 `routes.py`（沒有路由，`routes` 掛鉤照舊回 None）：`feast_text`（`/api/do/feast_text`，`outlock` 掛鉤；殼留一行包裝）。`same_behavior` 的 `relay` 軌 selftest 改 `fallback=feasts.DEFAULT_SCORE` 那一句（全檔要剛好一處），不要拆行或改名。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。**C 段的回話經 `g._log`**（第 271 批，計畫 `docs/superpowers/plans/2026-11-26-宴席回話經紀錄-第271批.md`；企劃者 2026-11-26「兩處都修 (Recommended)」）：`shell.act(game, lambda g: g._log(g.feast_toast(request.text, rate, request)))`，含 C 段重驗擋下的拒絕句（暫停、不在席上、字數、那一場散了），跟固定敬酒走 `choose` 一樣——情誼往上跨過 `biography.affinity_marks` 的那一筆行狀這一下就寫（`annals.watch`），不再等下一個請求的同步。**`features_core.after_action` 在自己寫的這一條路沒叫**（固定敬酒經 `choose` 的一般那條路會叫；另外 `choose` 還做的清 `battle_card`、`guide_done`，`check_thresholds`、`_settle_plots`、`_story_tick`、`ranks.check_summons` 等也沒做），補不補還沒定（企劃者只點頭了「回話經紀錄」；第 271 批計畫第二節）。比對軌：`relay` 軌 feast 那一段走得到 C 段收下（兩下：保底分那一杯與分數 90 那一杯），走不到情誼跨段與 C 段重驗擋下，那兩樣靠 `test_feast_shell.py` 守。另外要跑的（`test_for` 挑不到）：`tests/server/test_server.py`、`tests/arts/test_in_lock_model_timeout.py`、`tests/server/test_outlock.py`。

場景卡（第二輪第 91 批）：`scene` 掛鉤換成登記 `SCENE_ORDER` 的 `own/feast`、`art/feast`；圖看 `feasting` 欄位、不看 `seat`。
