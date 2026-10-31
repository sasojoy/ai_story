# 酒肆（`tianxia/features/tavern/`）

帶「酒肆」標籤的城鎮裡的一間：聽消息、查人、打聽交情與素材、題壁、請全店喝一輪、藏行跡、反查、託酒家留意、買殺手與保鏢、問酒家（鎖外三段式）、鄰桌閒談。主動搬六包第 10 批搬進來的是引擎那一半（計畫 `docs/superpowers/plans/2026-10-31-酒肆包-第1批.md`）；網頁那一半（`web/app.js` 的 `tav*`、`style.css` 的酒肆那一塊）留到第 3 階再切。

- 導覽：`docs/guide/裝備與店面.md` 的酒肆那一條。
- 設計稿：沒有版本號——https://claude.ai/artifact/3CfrzfpT1HzCxy6S985Q5W（企劃者 2026-10-18 核可；第三節託付留意、第六節買殺手、第八節問酒家）。

## 裡面有什麼

- `rules.py`：純規則（原 `tianxia/tavern.py`）。`ask.py`：問酒家照問句找事實（原 `tianxia/tavern_ask.py`）。兩個舊名都留成 `sys.modules` 別名（同一個模組物件）：`bot_policy`、`howto`（名望來源）、`server`（`chatter_write`、`ask_write`）、`scripts/try_tavern_ask.py`、走一趟借的 `BANNED_WORDS`（`Game.outing_say`）與測試照舊 import 舊名，`monkeypatch.setattr(tavern, ...)` 照樣打得到包裡。
- `actions.py`：原本 `Game` 上酒肆的 43 個方法，加 `tavern_sign`（`act:tavern` 那一下紀錄的標題）。
- `bots.py`：假人看到 `tavern:*` 怎麼按（原 `bot_policy.score` 那一段：只按出酒肆）。打聽那一步（`bot_policy._tavern`、`TAVERN_CHANCE`、`TAVERN_RESERVE`、`TAVERN_ASKS`）是 `take_turn` 的一步，不是分數，照舊在 `bot_policy`（測試直接換它們）。
- 掛鉤：`enabled`（`rules.on` 或此刻還坐在酒肆裡）、`choose`（`tavern:*`）、`bot_pick`、`bot_always = ("tavern:",)`（`bot.py` 的排除清單原本就有這一個，重複無害，第 11 批收）。

## 認領的欄位（手冊 3.5：留在原地）

- `PlayerState`：`picking_tavern`、`tavern_notes`、`tavern_heard`、`tavern_known`、`tavern_treat_day`、`whispers`、`hidden_until`、`tavern_watches`、`tavern_guard_until`、`tavern_shield_until`（換季全部跟著新角色重來，`carried` 是空的）。
- `WorldState`：`tavern_walls`、`tavern_whispers`、`tavern_treats`、`tavern_hits`、`tavern_hit_seq`、`tavern_chatter`（照季存）。
- `state.py` 的 `TavernNote`、`Whisper`、`WallNote`、`TavernWatch`、`TavernHit`；`models.py` 的 `Config.tavern`（`TavernTuning`）。

## 委派與留在原位的接縫

`Game` 留 19 個一行委派（公開 6：`tavern_do`、`tavern_view`、`tavern_ask_request`、`tavern_ask`、`tavern_chatter_request`、`apply_tavern_chatter`；私有 13：`_tavern_open`、`_tavern_enter`、`_tavern_price`、`_tavern_options`、`_tavern_sign`、`_tavern_run`、`_tavern_hit_problem`、`_tavern_hit_check`、`_tavern_hit_fight`、`_tavern_ask_facts`、`_deliver_watches`、`_deliver_hits`、`_deliver_whispers`）。位置算行為的接縫照舊在 `Game` 原位（批次表第二節；`tests/core/test_feature_boundaries.py` 的 `# tavern` 那一段寫了理由）：

- `sync`：下線那一段的殺手（`_tavern_hit_check(away_from)`）、人不在酒肆了就收店、三個 deliver（放進 `on_sync` 會改江湖紀錄的先後；它們不看酒肆開關：關掉之後雇主照樣領退款、風聲照樣送到）。
- `_everyday_options`：坐在酒肆裡時選單整個是酒肆那一串（`menu` 掛鉤只有一個位置）、`act:tavern` 入口；`_act`：`act:tavern` → `_tavern_enter`；`choose` 最後那一下殺手檢查。
- `shop_view` 的 `if shop == "tavern": return self.tavern_view()`（鐵匠鋪那條線緊貼著它改）、`_action_title`（`act:tavern` 的標題叫 `_tavern_sign`）、`_drop_stale_references` 收店、`_hint_triggers`、`_newbie_go`、`outing_say`（`BANNED_WORDS`）、`_shop_open`、`_depart`、`_idle`（只讀 `picking_tavern`）、`LEAVE_SHOP_IDS`（寫字面 `"tavern:back"`）。
- `server.py`：`MAIN_ACTIONS["tavern"]`、`tavern_ask` 三段式、鄰桌閒談的背景執行緒（`write_chatter`、`chatter_once`）。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組 24 處：`actions.py` 9（`annals`、`battlelog`、`bounties`、`encounter`、`equipment`、`renown`、`roster`、`shopview`、`social`）、`rules.py` 14（`annals`、`atlas`、`figures`、`renown`、`territory`、`treasures`，函式裡的 `prologue`、`arena`、`figure_life` 三處、`allied`、`zh` 兩處）、`ask.py` 1（`figures`）。
- 服務清單（`tianxia/core/services.py`）這一包加的：`_shop_say`、`_shop_after`、`_idle`、`_last_wear`（共用）、`_battle_now`（過渡，決戰）、`_tavern_seek_exact`、`_tavern_reply`（寄放）。

## 測試

- 這一包的：`tests/test_tavern.py`（32 條，1 條 smoke）、`test_tavern_seek_presence.py`（7，查人的「此刻就在…」不比「此地還有」寬）、`test_tavern_web.py`（4，假瀏覽器跑整支 `app.js` 的酒肆那幾頁）、`test_tavern_package.py`（4，別名、開關關著時出得去、掛鉤的標題）。`pytest tianxia/features/tavern/tests -n 4 -m "slow or not slow"`。
- **`test_for` 挑不到的混在別人檔裡的**（這一輪不拆）：`tests/seal/test_seal_acts.py`（FB-643 併進來的玉璽 × 酒肆）、`test_seal_acts3.py`、`test_seal_acts_hidden.py`、`test_seal_revamp.py`（`_tavern_hit_fight`）、`test_seal_revamp_hidden.py`、`tests/bots/test_zh.py`（`ask_clean`、`chatter_clean`）、`tests/acts/test_sortie_duel_bots.py`（換掉 `bot_policy._tavern`）、`tests/arts/test_explain2.py`（名望來源）、`test_hints.py`（`h_tavern`）、`tests/server/test_server.py`、`tests/season/test_real_content.py`。改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/tavern/actions.py tests/seal/test_seal_acts.py tests/seal/test_seal_acts3.py tests/seal/test_seal_acts_hidden.py tests/seal/test_seal_revamp.py tests/seal/test_seal_revamp_hidden.py tests/bots/test_zh.py tests/acts/test_sortie_duel_bots.py tests/arts/test_explain2.py tests/arts/test_hints.py tests/server/test_server.py`（`--slow` 連整檔 slow 的那幾個；`test_real_content` 改內容時 `test_for` 自己會挑）。
- **改 `rules.py`、`actions.py` 時 `test_for` 挑的比搬之前窄**（審查量的）：搬之前改 `tianxia/tavern.py` 會挑到 import `tavern` 的 `test_zh` 與五個 seal 檔（8 個檔 120／176 條）；現在程式在包裡，改 `rules.py` 或 `actions.py` 只挑包的 4 個檔＋核心契約與邊界（7 個檔 118／119 條，不含／含 slow）。例：`rules.chatter_clean` 拿掉 `zh.stray_latin` 那一關只有 `test_zh` 紅、`tavern_hit_fight` 的 `hit_win_fame` 加倍只有 `test_explain2` 紅——上面這條指令兩個都抓得到，`test_for` 只給包的檔抓不到。這一輪不讓 `test_for` 把混合檔算進包（同出陣 README），交 PM 定。
- 前後一字不變：`scripts/same_behavior.py` 的 `tavern` 一軌（`--tracks tavern`）。
