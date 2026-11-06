# 陣營（`tianxia/features/faction/`）

投靠（兩步確認、豪強選依附哪一軍）、拜入門派、豪強改幫（三陣營四勝利）、叛投（確認、驗證、同伴回江湖、清舊陣營的進度）、季末結局卡與三方卡。全部拆包第 35 批搬進來，行為一個字不變。
**跟 `tianxia/factions.py` 不是同一個東西**：`factions.py`（多一個 s）是陣營規模的換算（席次 `seats` 讀），在共用規則層（`registry.SHARED`），這一批沒搬；這一包管的是玩家對陣營做的事。

- 導覽：`docs/guide/大勢人物與賽季.md`（叛投、三方卡、結局卡）。
- 設計稿（都在 `docs/superpowers/specs/`）：`2026-10-02-第一季黃巾之亂-design.md` 5.1（投靠與叛投）、`2026-10-02-傳聞分層-design.md` 第五節（叛投的軍情）；
  三陣營四勝利是 `2026-10-24-減法季-整合設計.md` 第三章（整合版，取代 `2026-10-23-減法季-回到文字互動-design.md`）；豪強選依附哪一軍是
  `2026-10-15-第一季豪強分屬兩軍-design.md`；叛投時同伴回江湖是 `2026-10-18-歷史武將同行-design.md` 9.5。
- 計畫：`docs/superpowers/plans/2026-11-06-陣營包-第1批.md`。

## 裡面有什麼

- `join_actions.py`：投靠與拜入門派——`sect_options`（`_sect_options`）、`sect_choose`（`sect:` 端出那一則事件）、`ally_options`、`faction_step`（投靠兩步：按、確定／再想想；選邊）、`bot_lean`、`join_lean`（`_join_lean`）、`faction_prompt`（`_faction_prompt`）；
  加 `pending_options`（選單「接管整個選單」的三段：拜入要依附的門派之後還沒挑一邊、投靠確認、叛投確認；原本寫在 `_everyday_options` 裡）與 `SECT_LABEL`（原本寫在 `engine.py`）。
- `lean_actions.py`：改幫三個——`lean_options`（`_lean_options`）、`lean_anytime`（`_lean_anytime`：選單上沒有它時照樣收）、`lean_step`。
- `defect_actions.py`：叛投——`defect_step`（兩步：按、確定／再想想）、`left_names`、`leave_behind`、`defect_targets`；加 `defect_options`（`_everyday_options` 的叛投迴圈）與 `scene`（`_own_scene_text` 叛投確認畫面那一段）。
- `defection.py`（原 `tianxia/defection.py`，舊名是別名）：叛投的規則——能不能叛投、去哪些槽、確認畫面的話（`prompt`）、`clear_progress`／`_clear_own`／`defect`。
- `ending_actions.py`：季末與三方卡——`season_grant`（換季開場照上一季論功發起手資源與稱號）、`four_wins`、`ending_card`、`tier_outlook`、`tier_hint`、`gentry_now`、`sides_card`。
- `bots.py`：假人的分數（原本 `bot_policy.score` 的 `defect`、`sect` 兩段；`faction:` 原本落到最後的 `None`）：三個前綴一律回 `None`。投靠與確認仍走 `bot_policy._toward_faction`（不經 `score`）。
- 內容檔：`content = ("sects.json", "events/sects.json")`（門派與拜入門派的事件，總表附錄甲歸陣營；`content.py` 照舊讀）。
- 掛鉤：`prefix = ("faction", "defect", "sect")`；`choose` 接這三個前綴（標題在動作之前拿；`sect` 的標題問核心的 `_action_title`，落到最後的「提前出關」，隨後被事件標題換掉）；`bot_pick` 一律 `None`；
  `bot_always = ("defect:", "faction:lean:")`；`enabled` 一直是 `True`；`on_drop_stale`（內容改版後拿掉的陣營，三個 pending 欄位作廢；原本在 `_drop_stale_references` 中段）；`defection()` 登記叛投兩格——`clear` 的 `progress`（`_clear_own`）與 `after` 的 `leave_behind`（`DEFECT_ORDER` 一個字不動）。
- 「你這一步」的格 `steps()`（全部拆包第 36 批；順序在核心的 `STEP_ORDER`，排最後）：`join`（`join_actions.join_step_items`／`join_step_place`：散人、劇本有陣營、季沒收才有那一件，目標是最近的投靠點〔問新手引導包的查詢服務 `ctx._nearest_to`；一樣近照劇本陣營的順序〕；`JOIN_STEP` 從 `weekcard` 搬來，字一個不改；投靠點的地名照 `weekcard._places` 抄一份 `_join_place_names`〔三方卡照用 `weekcard` 那一份，包不 import `weekcard`〕；原本 `weekcard._steps` 最後那一段與 `step._target` 的去投靠那一支）。不問 `enabled`。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`pending_faction`、`pending_defect`、`pending_ally`（按了投靠／叛投還在確認畫面上、挑好的依附那一軍）；`carried` 沒有（換季重來）。
- 不認領：`faction`、`ally`、`sect`、`season_title`（身份，核心與 `social.affiliation` 到處讀）；`defected`（叛投寫它，但 `battle_instance`、狀態列、`guide` 都讀）；`ledgers`、`lean_changed`（`wins.set_lean` 在共用規則層寫，叛投時 `_clear_own` 清）。
- 共用規則層的 `atlas.travel_block` 直接讀 `pending_faction`、`pending_defect`（動身被擋的那一句；全部拆包第 50 批照實記下，第 56 批選單收接縫時改成掛鉤、一張先後表）。

## 委派與留在原位的接縫

`Game` 留 13 個一行委派：`_season_grant`、`_sect_options`、`_lean_options`、`_lean_anytime`、`_join_lean`、`_faction_prompt`、`_four_wins`、`ending_card`、`tier_hint`、`sides_card`，加三個新的——
`_faction_pending_options`（選單接管整個選單的待確認三段，位置固定）、`_defect_options`（選單的叛投迴圈）、`_defect_scene`（叛投確認畫面的場景）。`_ally_options`、`_left_names` 沒有原位的呼叫端，不留委派。
其餘 `_faction_step`、`_bot_lean`、`_lean_step`、`_defect_step`、`_leave_behind`、`_tier_outlook`、`_gentry_now` 只有包裡叫，沒有委派。
核心原位接掛鉤的：`choose` 的 `faction`／`defect`／`sect` 與 `_action_title` 的 `faction`／`defect`（`Outcome`）、`bot_policy.score` 的 `defect`／`sect`、`bot.py` 的 `defect:`／`faction:lean:` 排除（`bot_always`）、叛投兩格（`_CLEAR_CORE`、`_DEFECT_AFTER_CORE` 拿掉）。
還留在原位的：`bot_policy.take_turn` 的選項濾掉 `faction:lean:`／`defect:`（裡面還有別包與核心的前綴，且不用 `bot_always`）、`bot_policy._toward_faction`（投靠與確認，不經 `score`）、`bot.py` 的 `sect:` 看過才排除（條件式）。
核心還直接碰這一包認領欄位或前綴的：`options` 的 `defect:cancel`（叛投確認畫面上的「再想想」，`pending_defect` 有值時核心原位加進戰鬥選單）、`_own_scene_text` 選邊與投靠確認的場景判斷（叛投那一段已是 `_defect_scene` 委派）、`atlas.py` 讀 `pending_faction`／`pending_defect`；這幾處沒有掛鉤可接，位置算行為，留原位。
包裡自己叫自己的 `four_wins` 一律直接叫（沒有測試換掉它）；`Game._four_wins` 只剩決戰包經 ctx 問的那一條（`services.py` 二、查詢服務 `# faction`）。
叛投確認畫面問押糧經核心的 `core/convoy_base.py`（第 35 批 PM 認定第 3 條認了，照 `omen_base` 前例；它只讀軍情包認領的 `PlayerState.convoy`、不寫，`held(state)` 一個函式）。

## 測試

`tianxia/features/faction/tests/`（整檔屬於這一包的，原樣搬來，只改路徑；`tests/conftest.py` 的 `LONG_FIRST` 兩行跟著改路徑）：

- `test_defection.py`（41，原 `tests/figures/`）、`test_four_wins_wiring.py`（13，原 `tests/battle/`）、`test_gentry_allied_fixes.py`（13，原 `tests/acts/`）、`test_four_wins_gentry_bots.py`（10，原 `tests/season/`）、
  `test_sides_card.py`（9，原 `tests/figures/`）、`test_four_wins_lean_anytime.py`（9，原 `tests/map/`）、`test_season_end_tiers.py`（2，原 `tests/core/`）：共 97 條。
- `test_faction_smoke.py`（1 條，**新寫的煙霧**，手冊 4.1 每一包至少一條）：散人在官軍的投靠點按投靠、確定；走到黃巾的投靠點看到叛投、按了又再想想。
- 不放 `faction_stage.py`：選單上的待確認畫面由 `Game._everyday_options` 的 `_faction_pending_options` 委派給，位置算行為；契約測試的擺局面用預設的「平常」。

**不搬、另外要跑的混合檔**（含這一包的測試，但整檔不屬於這一包，不拆；數字是全檔條數，用到這一包的條數未逐條量）：

- `tests/core/test_contract_core.py`（46）：叛投兩格的順序、核心與包把每一格剛好各拿一次（約 710～776 行；第 35 批這兩條的擺法改了：假包自己登記 `progress`、`leave_behind` 兩格〔`DefectHook`〕，原本 `monkeypatch` 換掉 `defection._clear_own`／`Game._leave_behind` 的兩行拿掉，`g2._defect_step` 改叫 `defect_actions.defect_step(g2, ...)`，
  `calls` 的內容與先後、預期表照登記表換主人改，斷言的意思不變；第 35 批 PM 認定第 2 條認了，比照第 34 批認定第 4 條，寫在手冊第十五節）。
- `tests/figures/test_gentry_allied.py`（47）、`tests/core/test_gentry_ledgers.py`（16）、`tests/core/test_factions.py`（2）、`tests/core/test_faction_events.py`（3）：豪強、兩本帳、陣營規模與事件。
- `tests/figures/test_promotions_huang.py`（56）、`test_promotions_high.py`（130）、`test_seats.py`（83）、`test_rumor_layers.py`（70）：只有幾處 `import defection`（晉升、席次、傳聞分層）。
- `tests/web/test_gentry_allied_web.py`（2）：網頁（第 3 階）。
- 「你這一步」的去投靠那一格（第 36 批）：`tests/bots/test_step.py`（9：去投靠的目標是最近的投靠點、先後在新手目標之後）、`tests/map/test_weekcard.py`（7：散人的卡最後一件是去投靠）；格的先後與登記由核心契約 `tests/core/test_contract_core.py`（`# core_step`）鎖住。
- `tests/core/test_feature_boundaries.py`、`tests/core/test_contract_features.py`（核心契約）：這一包的邊界、前綴、欄位、換季都在裡面守。

## 過渡（手冊 3.11）

過渡 import 1 處（行尾標「過渡：待搬」；全部拆包第 45 批合完重印）：懸賞榜第 45 批成包，`join_actions.py`、`lean_actions.py`、`defection.py` 改讀核心 `core/bounty_base`（`stranded`、`STRANDED_*`、`drop_stranded`）；
`events.event_candidates`（`join_actions.py`：拜入門派那一顆）。`ranks`（階與稱號；`defection.py`）第 40 批收進共用規則層，不算過渡（原本 5 處）。叛投的 `stranded` 格第 45 批由懸賞榜包登記（`BountiesFeature.defection()`），`_STRANDED_CORE` 空了留 `{}`。
確認畫面讀押糧不直接碰軍情包的欄位：問核心的 `core/convoy_base.py`（`held(state)`，同 `omen_base` 的先例；它只讀軍情包認領的 `convoy`，不寫）。
