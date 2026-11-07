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
- `actions.py`：交友見不到人時的打發話 `no_audience_line`（會排提示、花亂數，不是純讀，所以不放 `view.py`）、交友 `socialize`（舊寫法）與 `precise_socialize`（一類一顆）、指名求見 `call`、被打發 `brush_off`、記一輪 `count_talk`、福緣 `fortune_gift`、`deliver_fortune`、
  沒碰上人物時抽事件 `encounter`、紀錄標題 `call_title`。
- `bots.py`：假人看到 `call:` 的選項怎麼按（原本 `bot_policy.score` 的 call 那一段）——只按「返回」，`call:<人物>` 一律不按（名望不夠的求見永遠按得下去，不能給分）。`act:call` 不按、`act:socialize`（`act_socialize`）第 60 批接進 `Verb.bot`；`Feature.bot_idle` 問 `idle_call`（整季機器人不按名望不夠的求見）。改 `bots.py` 的 `act:` 分數時另外跑 `tests/bots/test_bot_policy.py`、`tianxia/features/sortie/tests/test_bot_policy_conquest.py`、`tests/bots/test_bot_policy_stuck.py`（`test_for` 挑不到，第 60 批）。
- 掛鉤：`enabled` 一直是 True（一類一顆 `precise`、福緣 `roster` 各有自己的開關，包本身沒有總開關）；`prefix = "call"`；`choose` 接 `call:`（`Outcome.title` 在動作之前拿，
  `prepared` 經 `ctx._talk_turn` 寄放）；`bot_pick` 問 `bots.score`；`bot_always` 不宣告。`menu`、`scene` 沒接（見下）。
- 對話（`ctx._open_dialogue`）、事件呈現（`ctx._present`）、引導提示（`ctx._hint`）、閉門不見（`ctx._snubbed_character`）都經 `ctx`，不 import 人物情誼包；人物情誼包經 `ctx` 問這一包的
  `_can_meet`、`_socialize_figure`、`_count_talk`、`_social_plan`、`_brush_off`（服務清單二、查詢）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`talks_today`（`{人物: [第幾個遊戲日, 當天已聊幾輪]}`，遊戲日跟著季長縮）、`picking_audience`（求見名單開著）；`carried = ()`，換季全部跟著新角色重來。
  （第 20 批審查把這兩個留給這一批。）
- 內容：這一包的 `content/events/recruit.json`、`social_nanyang_yingchuan.json`、`social_north.json`、`social_runan.json`（交友事件；`content` 宣告，`content.py` 照它到這一包的 `content/` 載）。`figure_intros.json`（人物簡介）留在 `content/`：只有殼的 `server.py` 讀，`Content` 不讀、這一包不宣告。
  `recruit.json` 第 63 批歸這一包：7 則的 `actions` 都是 `socialize`、沒有 `recruit` 效果（跟附錄甲裁給人物情誼的招募 `_recruit*` 無關）。
- 共用的字：`AUDIENCE_HALL_FIGURES`、`SNUB_NOTE`、`SOCIAL_NO_ONE` 在核心 `core/services.py`（核心的選單、`sync`、挑戰本人也讀；`engine` 照舊 import 回來）；`SOCIAL_TALK`、
  `SOCIAL_LIST_INTRO`、`AUDIENCE_MEET` 在 `view.py`；`SOCIAL_LIST_TITLE` 留在 `engine.py`（場景文字讀）。
- 動身被擋（`atlas.travel_block`）：第 56 批選單收接縫起這一包登記 `MENU_ORDER["block"]` 自己那一格，讀 `picking_audience` 的只剩包裡；字與先後一字不動（`atlas` 不再讀）。

## 委派與留在原位的接縫

`Game` 上 16 個名字掛在 `game_api.py` 的表（邊界測試的 `GAME_DELEGATES` 從表算）；31 個方法裡其餘的只有包裡叫，不掛。主幹合回 D 段加的 `figures_here_view` 第 66 批拿掉（`/api/main` 改走 `status_slots`）。**沒有新增 `GAME_DIRECT`**。核心原位碰這一包的，接掛鉤的兩個：

- `choose` 的 `call:`、`_action_title` 的 `call:` 那一格（換成 `Outcome.title`）。

留委派、記進 `GAME_DELEGATE_CALLERS` 的：

- `act:socialize`、`act:call`：第 57 批接進 `Verb`（按下去與紀錄標題，本體 `actions.press`、`actions.open_audience`）；選單與底下那幾行第 56 批是 `here/social`、`notes/socialize`，單人地點的「求見某某」那一顆同在這幾行裡。
- 求見名單（`_everyday_options` × `_audience_options`）與求見畫面（`_own_scene_text` × `_audience_intro`）：`menu`、`scene` 掛鉤坐在談著、選邊、投靠確認、叛投確認那幾個 `picking_*` 之前，
  名單夾在叛投確認與懸賞榜中間、畫面夾在叛投之後，接成掛鉤就改了它們並存時誰先；位置算行為，所以不接。
- 收起求見名單接 `on_drop_stale`（`_drop_stale_references` 最後那一個掛鉤；只差序章收尾挪人之後的地點）。福緣到期自己送上門第 55 批換成 `local` 的 `fortune` 那一格（夾在別的補算中間，`on_sync` 沒有對應的位置）。
- `choose` 做完之後的 `_guide(self._note_action("socialize"))`（`kind == "call" and arg != "back"`）與前段的 `_checked_prepared`：留在 `choose` 原位（掛鉤沒有「做完記引導」的位置）。
- 核心的表：`models.py` 的 `ALLOW_FAMILIES`（有 `call:`）與 `act:call`、`act:socialize`；`server.py` 備料判斷、整季機器人排除「名望不夠、會被打發的求見」第 60 批搬成這一包的 `bot_idle`（照舊問 `ctx.can_meet_figure`）。
- 行動列底下交友、求見那幾行（第 59 批搬進 `menus.action_notes`，句子在這一包的 `howto.py`）：第 56 批起是 `notes/socialize` 那一格，`Game.action_notes` 不留委派（第 59 批的 `_social_notes` 合第 B 波時收掉）。
- `/api/main` 的 `figures_here` 那一格（`status_slots`，第 66 批）：包給 `figures_here_view`；像 `figure_face` 要讀 `web/img`，留殼、經 `frame.shell` 叫。點大勢人物的簡介 `figure_intro` 在包裡的 `intro.py`（第二輪第 83 批；`persona_rules` 已在共用層，不再是包讀包），殼留 `FIGURE_INTROS` 別名；`figure_face` 仍留殼。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組（全部拆包第 40 批合完重印 3 處）：`events`（`view.py`、`menus.py`、`actions.py`：候選、這個地點有沒有、抽一則）。`ranks`（階級；`view.py`、`actions.py`）第 40 批收進共用規則層，不算過渡（原本 5 處）。
- 服務清單（`tianxia/core/services_list.md`）這一包加的：一、共用的字 `AUDIENCE_HALL_FIGURES`、`SNUB_NOTE`、`SOCIAL_NO_ONE`；二、查詢 `_can_meet`、`_socialize_figure`、`_count_talk`、
  `_social_plan`、`_brush_off`（本體搬進這一包）與 `_open_dialogue`（本體在人物情誼包）；三、過渡 `_snubbed_character`（主人大勢人物 `features/figures`，第 31 批；總表附錄甲，本體留在 Game，主人成包時改成查詢服務）。
- 測試換 `tianxia.engine.pick_event` 的那幾條（抽不到事件才走打發話），改成換 `tianxia.features.socialize.actions.pick_event`——本體搬走，換的名字跟著走。

## 測試

- 這一包的（`tianxia/features/socialize/tests/`，14 條，全部不是 slow，`-n 4` 約 7 秒）：`test_socialize_variety.py`（4：城鎮的交友不能每次都抽到茶館說書，補寫的事件在
  這一包的 `content/events/social_*.json`；第 21 批整檔從 `tests/core/` 搬進來，只改了 `CONTENT_DIR` 的路徑層數）、`test_socialize_smoke.py`（1，`smoke`：week7 的官軍在長社按交友打開名單、
  點皇甫嵩，沒有模型他無心多談、名單收起）、`test_socialize_bots.py`（`call:back` 0.0、`call:<人物>` 不按、policy 問這一包）、`socialize_stage.py`（契約測試擺局面：平常）。
- **`test_for` 挑不到的、另外要跑的**（混著別的功能，這一輪不搬、不拆）：`tests/core/test_precise_actions.py`（`_social_plan`、`_deliver_fortune`）、`tests/figures/test_day_scale.py`
  （`_talks_left`、`_talked_out_note`、`_audience_intro`）、`tests/figures/test_promotions_high.py`（`_brush_off`）、`tianxia/features/guide/tests/test_hints.py`、`tests/arts/test_renown_explain.py`、
  `tests/core/test_engine.py`（`call:`、`can_meet_figure`、`_talks_used`、抽不到事件的打發話）、`tianxia/features/admin/tests/test_admin_timetable.py`、`tests/bots/test_bot_policy.py`
  （`socialize_*`）、`tests/figures/test_figures.py`、`tests/server/test_server.py`、`tianxia/features/seal/tests/test_seal.py`／`test_seal_revamp.py`（`_talk_cap`）、`tianxia/features/guide/tests/test_explain.py`、
  `tianxia/features/peers/tests/test_social.py`、`tests/season/test_real_content.py`（`_deep_interaction_target`）。網頁測試（`tianxia/features/guide/tests/test_explain_web.py`、`test_jianghu_page_web.py`）第 3 階。改 `figures_here_view`、`server.figure_intro` 另跑 `tests/web/test_revamp_web.py`（此地人物那一排與簡介，`test_for` 挑不到）。
- 前後一字不變：`scripts/same_behavior.py` 的 `socialize` 軌（`--tracks socialize,companions,talk,guide`）；此地人物那一排與對話框是 `here` 軌（主幹合回 D 段）。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`local` 的 `fortune`（`actions.fortune_due`，原位的判斷搬過來；`Game._deliver_fortune` 留給測試）。

**第 56 批（選單收接縫，核心批）**：`take/audience`、`here/social`、`notes/socialize`、`idle/audience`、`block/audience` 是這一包登記的格（`_everyday_options` 那一段搬進 `menus.here_cell`，`action_notes` 那一段搬進 `menus.action_notes`，鍵的順序算行為；讀 `howto` 是過渡，第 59 批收）；先後在 `core/features.py` 的 `MENU_ORDER`；委派 `_precise_social_option`、`_socialize_option`、`_fame_gap`、`_audience_options` 拿掉（第 57 批的 `Verb.cell`、`Verb.note` 不必再開）；上面寫「留委派」「原位」的以這一句為準。

**第 57 批（分派與標題收接縫，核心批）**：`verbs()` 是新開的（`call`、`socialize`）。`actions.press` 照原位的先後一字搬：先問召見、再扣體力、端晉升奇遇（這一支不排提示）或交友、排 `h_bond`；委派 `_socialize` 留著、格裡經 `ctx` 叫（`tianxia/features/guide/tests/test_explain.py` 換 Game 上的名字）。改這兩格另外跑：`tianxia/features/guide/tests/test_explain.py`、`tianxia/features/peers/tests/test_social.py`、`tests/bots/test_event_rotation.py`、`tests/core/test_engine.py -k "summons or call or socialize"`、`tianxia/features/companions/tests/test_companions_facade.py -k "call or socialize"`、`tianxia/features/travel/tests/test_travel_facade.py -k call`（第 61 批搬走的；這一包的 3 條在 `test_socialize_facade.py`，`test_for` 挑得到）。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（交友、求見那幾行與說明頁交友那一條），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`main` 表 `figures_here`。

## 第 61 批搬進來的測試（混合測試檔歸位）

照條拆來：`test_socialize_facade.py`（23 條，從 `tests/core/test_engine.py` 拆來）、`test_socialize_page_web.py`（1 條，從 `tests/web/test_jianghu_page_web.py` 拆來）、`test_socialize_shell.py`（3 條，從 `tests/server/test_server.py` 拆來）；兩邊都用的小工具在 `tests/kit/`（`engine_kit`、`server_kit`、`jianghu_kit`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- 改 `intro.py` 另跑 `tianxia/features/persona/tests/test_persona.py`、`tests/web/test_revamp_web.py`（`test_for` 挑不到）。
- `events`（`view.py`、`menus.py`、`actions.py`）第 87 批起是共用規則層，這 3 處不算過渡。
