# 交友求見（`tianxia/features/socialize/`）

交友（`act:socialize`）、指名求見（`act:call` 打開名單、`call:<人物>`）、名望不夠被打發、每位人物每個遊戲日談幾輪、結識奇遇（福緣）。全部拆包第 21 批搬進來，行為一個字不變。

- 導覽：`docs/guide/行動與地盤.md` 的交友求見那一節（交友與求見的次數、一類一顆）；人物對話本身看 `docs/guide/大勢人物與賽季.md` 的人物情誼（`tianxia/features/companions/`）。
- 設計稿：交友重做（Joy 10/6）；正式季整合 2.8（一類一顆的交友）；求見名單 FB-421；名望門檻武學與成長設計 9.1；次數與換日 day-scale、FB-102。
- 計畫：`docs/superpowers/plans/2026-11-04-交友求見包-第1批.md`。

## 裡面有什麼

- `view.py`：原本 `Game` 上的 18 個查詢與文字（讀存檔、第一個參數是 ctx；所以叫 `view` 不叫 `rules`——手冊 3.2 的 `rules.py` 純規則、不碰 Game，比照 `cultivation/view.py`、`battle/view.py`）——見不見得到 `figure_can_meet`（`Game._can_meet`）、`public_can_meet`（`can_meet_figure`）、差多少名望 `fame_gap`、
  這個遊戲日談幾輪 `talk_cap`、`talks_used`、`talks_left`、`talks_reopen`、談滿了怎麼寫 `talked_out_note`、一類一顆的交友這一下會做什麼 `social_plan`
  （選單、動作、對話備料、假人讀同一份）、交友會直接開口的人物 `socialize_figure`、`deep_interaction_target`、`audience_hall`、
  假人判斷 `starts_dialogue`、`is_futile`；結識事件 `meet_event`、福緣送得出的人 `fortune_free`。核心的 `rules.can_meet`（伏筆偷聽也用）是另一個，這裡 import 成 `core_can_meet`。
- `menus.py`：交友那一顆 `socialize_option`、一類一顆的交友 `precise_social_option`、求見的第二層名單 `audience_options`、求見畫面的說明 `audience_intro`；江湖頁「此地人物」那一排 `figures_here_view`（主幹合回 D 段從 `Game` 搬來：`talk.via`、`talk.why`、`aid`，只讀。它要問求見名單，所以放這裡不放 `view.py`：`menus` import `view`，反過來就循環）。陣營的名字走共用層 `figures.side_name`（人物情誼包的 `talk_view` 也問它）。
- `intros.py`（主幹合回 D 段從 `server.py` 搬來）：點大勢人物的簡介 `figure_intro`、`FIGURE_INTROS`。import 時讀一次 這一包的 `content/figure_intros.json`（正式內容、測試內容都讀 repo 這一份，不看設定），只有殼 import（`_main_view_body` 疊到 `figures_here[].intro`），引擎與假人程式不多讀。
- `actions.py`：交友見不到人時的打發話 `no_audience_line`（會排提示、花亂數，不是純讀，所以不放 `view.py`）、交友 `socialize`（舊寫法）與 `precise_socialize`（一類一顆）、指名求見 `call`、被打發 `brush_off`、記一輪 `count_talk`、福緣 `fortune_gift`、`deliver_fortune`、
  沒碰上人物時抽事件 `encounter`、紀錄標題 `call_title`。
- `bots.py`：假人看到 `call:` 的選項怎麼按（原本 `bot_policy.score` 的 call 那一段）——只按「返回」，`call:<人物>` 一律不按（名望不夠的求見永遠按得下去，不能給分）。
- 掛鉤：`enabled` 一直是 True（一類一顆 `precise`、福緣 `roster` 各有自己的開關，包本身沒有總開關）；`prefix = "call"`；`choose` 接 `call:`（`Outcome.title` 在動作之前拿，
  `prepared` 經 `ctx._talk_turn` 寄放）；`bot_pick` 問 `bots.score`；`bot_always` 不宣告。`menu`、`scene` 沒接（見下）。
- 對話（`ctx._open_dialogue`）、事件呈現（`ctx._present`）、引導提示（`ctx._hint`）、閉門不見（`ctx._snubbed_character`）都經 `ctx`，不 import 人物情誼包；人物情誼包經 `ctx` 問這一包的
  `_can_meet`、`_socialize_figure`、`_count_talk`、`_social_plan`、`_brush_off`（服務清單二、查詢）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`talks_today`（`{人物: [第幾個遊戲日, 當天已聊幾輪]}`，遊戲日跟著季長縮）、`picking_audience`（求見名單開著）；`carried = ()`，換季全部跟著新角色重來。
  （第 20 批審查把這兩個留給這一批。）
- 內容：這一包的 `content/events/social_nanyang_yingchuan.json`、`social_north.json`、`social_runan.json`（交友事件；`content` 宣告，`content.py` 照它到這一包的 `content/` 載）。`figure_intros.json`（人物簡介）也宣告在 `content`：`Content` 不讀它，只有 `intros.py` 讀（全部拆包第 62 批）。
  `recruit.json` 分區調查列在這一包，但招募（`_recruit*`）附錄甲裁給人物情誼，這一批不宣告，等 PM 定。
- 共用的字：`AUDIENCE_HALL_FIGURES`、`SNUB_NOTE`、`SOCIAL_NO_ONE` 在核心 `core/services.py`（核心的選單、`sync`、挑戰本人也讀；`engine` 照舊 import 回來）；`SOCIAL_TALK`、
  `SOCIAL_LIST_INTRO`、`AUDIENCE_MEET` 在 `view.py`；`SOCIAL_LIST_TITLE` 留在 `engine.py`（場景文字讀）。
- 共用規則層的 `atlas.travel_block` 直接讀 `picking_audience`（動身被擋的那一句；全部拆包第 50 批照實記下，第 56 批選單收接縫時改成掛鉤、一張先後表）。

## 委派與留在原位的接縫

`Game` 留 21 個一行委派（邊界測試的 `GAME_DELEGATES`）；31 個方法裡另外 10 個只有包裡叫，沒有委派。主幹合回 D 段再加一個 `figures_here_view`（只有殼在叫）。**沒有新增 `GAME_DIRECT`**。核心原位碰這一包的，接掛鉤的兩個：

- `choose` 的 `call:`、`_action_title` 的 `call:` 那一格（換成 `Outcome.title`）。

留委派、記進 `GAME_DELEGATE_CALLERS` 的：

- `act:socialize`、`act:call`（`_act` × `_socialize`，`_everyday_options`、`action_notes` 的交友與求見那幾行）：核心 `act:` 的子動詞，第 57 批接進 `Verb`。單人地點的「求見某某」那一顆同在這幾行裡。
- 求見名單（`_everyday_options` × `_audience_options`）與求見畫面（`_own_scene_text` × `_audience_intro`）：`menu`、`scene` 掛鉤坐在談著、選邊、投靠確認、叛投確認那幾個 `picking_*` 之前，
  名單夾在叛投確認與懸賞榜中間、畫面夾在叛投之後，接成掛鉤就改了它們並存時誰先；位置算行為，所以不接。
- 收起求見名單接 `on_drop_stale`（`_drop_stale_references` 最後那一個掛鉤；只差序章收尾挪人之後的地點）。福緣到期自己送上門（`_advance_player_local` × `_deliver_fortune`）：夾在別的補算中間，`on_sync` 沒有對應的位置。
- `choose` 做完之後的 `_guide(self._note_action("socialize"))`（`kind == "call" and arg != "back"`）與前段的 `_checked_prepared`：留在 `choose` 原位（掛鉤沒有「做完記引導」的位置）。
- 核心的表：`models.py` 的 `ALLOW_FAMILIES`（有 `call:`）與 `act:call`、`act:socialize`；`server.py` 備料判斷、`bot.py` 排除「名望不夠、會被打發的求見」（問 `can_meet_figure`）不動。
- `howto.py` 的 `social_line`、`call_line`、`CALL_LINE`（玩法說明的文字）留核心（引導與說明頁共用）。
- 組 `/api/main` 的 `figures_here` 那幾行留在殼（`server._main_view_body`）：包給 `figures_here_view` 與 `figure_intro`，像 `figure_face` 要讀 `web/img`，留殼。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組（全部拆包第 40 批合完重印 3 處）：`events`（`view.py`、`menus.py`、`actions.py`：候選、這個地點有沒有、抽一則）。`ranks`（階級；`view.py`、`actions.py`）第 40 批收進共用規則層，不算過渡（原本 5 處）。
- 服務清單（`tianxia/core/services.py`）這一包加的：一、共用的字 `AUDIENCE_HALL_FIGURES`、`SNUB_NOTE`、`SOCIAL_NO_ONE`；二、查詢 `_can_meet`、`_socialize_figure`、`_count_talk`、
  `_social_plan`、`_brush_off`（本體搬進這一包）與 `_open_dialogue`（本體在人物情誼包）；三、過渡 `_snubbed_character`（主人大勢人物 `features/figures`，第 31 批；總表附錄甲，本體留在 Game，主人成包時改成查詢服務）。
- 測試換 `tianxia.engine.pick_event` 的那幾條（抽不到事件才走打發話），改成換 `tianxia.features.socialize.actions.pick_event`——本體搬走，換的名字跟著走。

## 測試

- 這一包的（`tianxia/features/socialize/tests/`，14 條，全部不是 slow，`-n 4` 約 7 秒）：`test_socialize_variety.py`（4：城鎮的交友不能每次都抽到茶館說書，補寫的事件在
  這一包的 `content/events/social_*.json`；第 21 批整檔從 `tests/core/` 搬進來，只改了 `CONTENT_DIR` 的路徑層數）、`test_socialize_smoke.py`（1，`smoke`：week7 的官軍在長社按交友打開名單、
  點皇甫嵩，沒有模型他無心多談、名單收起）、`test_socialize_bots.py`（`call:back` 0.0、`call:<人物>` 不按、policy 問這一包）、`socialize_stage.py`（契約測試擺局面：平常）。
- **`test_for` 挑不到的、另外要跑的**（混著別的功能，這一輪不搬、不拆）：`tests/core/test_precise_actions.py`（`_social_plan`、`_deliver_fortune`）、`tests/figures/test_day_scale.py`
  （`_talks_left`、`_talked_out_note`、`_audience_intro`）、`tests/figures/test_promotions_high.py`（`_brush_off`）、`tests/arts/test_hints.py`、`tests/arts/test_renown_explain.py`、
  `tests/core/test_engine.py`（`call:`、`can_meet_figure`、`_talks_used`、抽不到事件的打發話）、`tests/figures/test_admin_timetable.py`、`tests/bots/test_bot_policy.py`
  （`socialize_*`）、`tests/figures/test_figures.py`、`tests/server/test_server.py`、`tests/seal/test_seal.py`／`test_seal_revamp.py`（`_talk_cap`）、`tests/core/test_explain.py`、
  `tests/core/test_social.py`、`tests/season/test_real_content.py`（`_deep_interaction_target`）。網頁測試（`tests/web/test_explain_web.py`、`test_jianghu_page_web.py`）第 3 階。改 `figures_here_view`、`intros.py` 另跑 `tests/web/test_revamp_web.py`（此地人物那一排與簡介，`test_for` 挑不到）。
- 前後一字不變：`scripts/same_behavior.py` 的 `socialize` 軌（`--tracks socialize,companions,talk,guide`）；此地人物那一排與對話框是 `here` 軌（主幹合回 D 段）。
