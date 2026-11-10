# 親衛隊長（`tianxia/features/guard/`）

- 做什麼：取代酒肆招募的同伴系統（Joy 2026-11-09）。10 級那一路撞見一個快死的孩子，救下、收養，之後一件一件的事由玩家決定怎麼待他；情分（善待往上、虐待往下）與性向兩條帳，紀事是他的記憶。最後他一定成為你的親衛隊長，被虐待大的帶著恨追隨。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「親衛隊長」那一節
- 設計稿：https://claude.ai/artifact/7Sra7sBo7njyH34B2Nr7Su（源檔在專案資料夾 `design/親衛隊長/設計稿v1.html`；Joy 2026-11-09「其他都按照建議」）
- 開關：`Config.guard.enabled`（預設關；數字在 `tianxia/core/tuning/guard.py`，全是【草】）

## 第一批：遇見與成長

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：options、menu、choose（`guard:`）、status（`main.guard`）、on_sync、after_action（自己問 enabled）、on_season_start、bot_pick、outlock、seams（`season.carry` 的 `guard` 那一格） |
| `rules.py` | 純規則：心性五檔（`band`）、夾法（`clamp_choice`：情分 ±step_cap、模型的 ±2、性向只留清單上的）、固定事件（`fixed_event`）、記帳（`apply`）、給模型的提示（`write_event` 生一件事＋溫嚴狠三個做法、`judge_say` 評自己寫的那一句） |
| `texts.py` | 固定的字：六種開場、男女名字表、八件家裡的事、四件路上的事（模型壞了與假人用；全部待 joy 潤） |
| `actions.py` | 「此地還能做」那幾顆、接管的選單、每天保底的家裡的事（on_sync）、帶他出門花了體力那一下冒出的路上的事（after_action）、三段式的 A、C 段、改名、出門帶不帶、親衛隊長那一頁那一份、換季照帶 |
| `routes.py` | `/api/do/guard_rename`、`guard_along`、`guard_say`（鎖外三段式）；背景寫字 `guard`（OutlockJob，表外的格接在表尾） |
| `bots.py` | 假人也養一個（別人之後看得到他）：只走固定事件、不叫模型；每個假人一種待人的路數（七成溫、兩成嚴、一成狠） |
| `web/guard.js`、`web/guard.css` | 俠客頁「同伴」最上面的親衛隊長那一頁（`cultivation.js` 的同伴那一頁叫 `guardHtml`） |

- 流程：`met`（眼前有個孩子：救／不管）→ `saved`（收養少年、少女，或救了不帶走）→ `grow`。不管、不帶走都是 `left`：他留在那裡，回到那個地點「回去看看那個孩子」。
- 事件從哪來：模型叫得到時 on_sync／after_action 只記 `want`，放鎖之後背景寫字生（`write_event`），回來 C 段重驗同一張單子才收；寫不出來、等過 `wait_seconds`、假人、伺服器沒模型，一律換固定事件。
- 自己寫的那一句：A `say_request` → B `judge_say`（跟這件事無關的回 relevant=false，C 段回「沒聽懂」不算這一次）→ C `apply_say` 重驗同一件。
- 數字由引擎定：模型評的情分夾到 ±2，固定事件寫死的最多 ±`step_cap`，總帳夾在 ±`qing_cap`；畫面不露數字（心性一檔、墨線位置）。

**認領的欄位**：`PlayerState.guard`（`GuardBook`、`GuardEvent`、`GuardChoice`、`GuardEntry`；`None` 不寫進存檔，在 `state.QUIET_DEFAULTS`）。換季照帶（`carried`）：`season.carry` 的 `guard` 那一格整份照帶（不看開關），`on_season_start` 收拾眼前那一件、天的帳，求學剩下的時間照帶。資料庫不升版。

## 第二批：求學、出師、投效

- 流程接著 `grow`：成長期三段走完（第五批；不看等級）出現「{name}該出去學點本事了」→ `picking`（選單換成七處去處＋再等等；錢不夠那幾顆按不下去）→ `study`（花 `schools[去處].silver`、推那一處的性向、動情分；學 `study_days` 天，7 天季 `week7_study_days`，看時間不看等級）。
- 求學期間寫 `letters`（2）封信回來（kind `letter`，平均排在求學那幾天裡；回信也是三個做法或自己寫）；家裡、路上的事停掉。
- 期滿 → `trial`：出師考驗一件（kind `trial`，照分數最高的出路出題）。答了 → `settle`：出師結算。
- 結算（`rules.top_paths` 照性向平均挑前 `path_options` 條出路）：模型挑一條、取稱號、讀紀事寫生平（`bio_max` 字內）與立誓那一段（`rules.settle`，鎖外背景寫字，預算 `settle_budget_seconds`）；C 段 `clamp_settled` 夾：出路只能是交出去的那幾條、稱號 2～4 字且過 `naming.name_problem`，不行換固定的（`texts.TITLES`）。叫不到模型、假人、等太久一律 `fixed_settle`。
- → `oath`：跪誓那一件（字是結算寫好的 `oath`，三個做法固定：扶起來、受這一拜、轉身就走）。答了 → `sworn`：親衛隊長。親衛隊長那一頁名帖旁寫出路與稱號，多一段只有自己看得到的生平。
- 恨線：心性照情分，立誓那一段照心性寫；恨極的照樣立誓投效（永遠不背叛），專長與台詞是第三批。

## 第三批：投效之後

- 投效以後（`sworn`）照樣有家裡、路上的事（他已長大，提示裡寫出路與稱號）；心性一季最多換 `band_steps_per_season` 檔（`rules.season_clamp`，照 `season_qing`：這一季開始或投效那一刻的情分）。
- 你做完一件事氣血掉到 `hurt_ratio` 以下、而且比做之前少：他照心性說一句（`texts.HURT_LINES`，一天一次；留在住處的不說）。
- 每季開季先來一段（kind `season`，模型寫；固定的照心性 `texts.SEASON_LETTERS`）。
- 專長走核心唯讀掛鉤 `tianxia/core/guard_base.py`（Joy 2026-11-09「好」）：`perk(state, content, key)` 只讀 `PlayerState.guard` 與 `Config.guard.perks`（照出路）、`band_perks`（照心性），開關關著、沒投效、沒帶在身邊是 0。各原位問一次、夾一次；鍵與原位對照在 `guard_base` 的檔頭。數字第三批全是 0，第四批量過才填（見第四批）。農夫回體力在這一包的 `on_day`。

## 第四批：別人看得見他（Joy 2026-11-10「全部做完一起上」）

- 酒肆不再招同伴：開季那一刻 `Config.guard.enabled` 開著就蓋章 `WorldState.guard_on`（`world_state.stamp_season`），hire 包的 `on` 看它；正在跑的那一季照招到收季。
- 你在決戰（或攻城戰）裡倒下：帶在身邊、投效了的他照心性說一句（`texts.FELL_LINES`），同一場一次（`GuardBook.fell_battle`；讀 `ctx._battle_now()`，邊界名單 `("guard", "battle")`）。
- 截殺：戰報裡多他的那一句（核心 `guard_base.raid_lines`：自己帶著的照心性、照勝負；對手帶著的寫「某某身邊跟著親衛隊長…」），peers 包 `raid_record` 讀。
- 名帖與玩家卡：「親衛隊長小明（將軍）」（`guard_base.card_line`）：玩家卡多一個 `guard` 鍵（`web/peers.js` 畫 `.peer-guard`），名帖頭銜池（`mingtie.earned`）多這一條。
- 列傳：收養、投效各記一則行狀（`annal_base.DEED`），季末的傳照行事寫。
- 上陣：照設計稿是專長＋台詞，不佔隊上的位子、不進 team 的名冊（打法不變）。
- 專長的數字照 `scripts/measure_guard.py` 量過填進 `core/tuning/guard.py`：人人養得到，一格不超過玉璽碎片（威力 ×1.10、閃避 +0.03）的一半。將軍大場面 +3 個百分點、謀士與殺手威力 ×1.05、遊俠賞銀 +10%、鐵匠造化分 +4、農夫每天 +24 體力、乞丐問酒家多 1 次、弓箭手 +3 個百分點、醫者少扣 +5%、斥候破境丹機會 ×1.25；恩深擋刀 +0.02、敬重 +0.01。
- 比對軌 `scripts/sb/tracks/guard.py`（`--track guard`）。

## 還沒做

酒肆裡別人親衛的傳聞、切磋論武時他在旁邊說一句、決戰兩邊的親衛隔陣相望（設計稿第五節後三條）；hire 包整包刪掉（關掉一季沒事之後）。江湖頁有事時要一條提示列（`main.js` 的 `jhHintsHtml`，殼）要 Joy 點頭才加，現在是「此地還能做」裡那一顆。

## 測試

- `tests/test_guard_seen.py`（第四批）、`tests/test_guard.py`（14 條）、`tests/test_guard_study.py`（12 條，第二批）、`tests/test_guard_sworn.py`（7 條）與 `tests/test_guard_perks.py`（9 條，第三批）、`tests/test_guard_smoke.py`（1 條 smoke）。

## 第五批：成長期三段與每天教他（Joy 2026-11-10 設計稿 https://claude.ai/artifact/GzVzRdBgshFJpvYsNd8E91「好」）

- Joy 11/10「沒有跟他互動幾次就要把她送出去求學 你應該多參考一些養成的遊戲」「我們收留他的時候已經12-13歲 應該沒有所謂的幼年」：
  求學不再看等級（`study_level` 拿掉），改看成長期三段 `GuardBook.phase`：0 初來（十二三歲）、1 相熟（十三四歲）、2 長成（十五六歲）、3 走完。
- 每一段一起過 `phase_days` 天（換日才算；7 天季 `week7_phase_days`）、經歷 `phase_events` 件事（家裡、路上的事答了、每天教他那一下都算；7 天季 `week7_phase_events`），
  兩樣都到了 on_sync 要這一段的大事（kind `milestone`：發燒守夜、打架與身世、說出想做什麼人；模型照 `rules.MILESTONE_ASK` 寫，叫不到換 `texts.MILESTONES`），答了 `rules.grew` 長一段。三段走完才有「送他去求學」。
- 每天教他什麼（`guard:teach:<課>`，一天一次，`texts.LESSONS` 八樣；推的性向與情分在 `Config.guard.lessons`；「讓他自己玩」照心性往俠或暗）。
- 頁上：墨線底下「最近：…」（`rules.look`，最重的兩種性向換白話）與這一段走到哪（`status.grow`）；「今天教他什麼」一排八顆（`status.lessons`）。
- 立繪：初來是 `child/<m|f>-saved`、相熟 `child/<m|f>-grown`、長成 `child/<m|f>-teen`（主機本機畫；沒放上來前照相熟那張，`rules.teen_art`）。
- 換季：段、日子、件數照帶；`phase_day`、`teach_day` 歸零。假人從選單上教（`bots.score` 照名號與天挑）。
- 新欄位（`GuardBook` 裡，跟著 `PlayerState.guard` 不寫空的）：`phase`、`phase_day`、`phase_days`、`phase_n`、`teach_day`。換回舊程式：這幾格丟掉、照等級求學（多出來的鍵 pydantic 照忽略）。
