# 玩家互動一（`tianxia/features/peers/`）

此地還有誰、玩家卡與卡上的動作登記表、邀請框（打招呼、名帖、切磋、論武、結伴同行共用的 `invite:` 選項）、打招呼、贈物、名帖（定稿、遞、回帖、檢舉、管理者撤下與放回）。全部拆包第 37 批搬進來，行為一個字不變。
第 38 批再搬進來：切磋、論武（三段式首創取名）、截殺（含策馬脫身），與假人答切磋、答論武、截殺（`spar`、`discuss`、`raid` 三個模組）。
通緝（`wanted.py`）第 45 批搬進懸賞榜包（`tianxia/features/bounties/`），卡上動作的登記表搬進核心 `core/cards.py`；結伴同行（`_join`、`join_refusal`）第 48 批搬進移動包（`tianxia/features/travel/party.py`，`Game` 上的名字掛在 `game_api.py` 的表）。

- 導覽：`docs/guide/散人與玩家互動.md`（玩家卡、切磋、論武）。
- 設計稿：玩家互動（企劃者 2026-10-08）；名帖（Joy 2026-10-19，設計稿 https://claude.ai/artifact/YLTXjaX77DJRsCmMX57xAi）。
- 計畫：`docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md`、`docs/superpowers/plans/2026-11-07-玩家互動包-第2批.md`。

## 裡面有什麼

- `social.py`（原 `tianxia/social.py`）：玩家卡 `card`、贈物、打招呼（`Gesture`、`calls`）。卡上動作的登記表 `ACTIONS`／`CardAction`／`CardButton`／`register`（切磋、論武、截殺、通緝也登記進同一張）在核心 `tianxia/core/cards.py`（第 45 批），`social` re-export 同一批物件。
  「此地還有」的判斷（`here`、`visible`）與身分字（`side`、`affiliation`、`GONE`）不在這裡：先拆成核心的查詢服務 `tianxia/core/presence.py`（窗口 `Config.presence_seconds`），`social` 從那裡 re-export 同一批函式物件；
  酒肆（客人名單、查人）、探索（結算卡的「此地還有」）、狀態列都直接問核心。
- `invites.py`（原 `tianxia/invites.py`）：邀請的帳（`WorldState.invites`）；`mingtie.py`（原 `tianxia/mingtie.py`）：名帖的規則；`mingtie_card.py`（原 `tianxia/mingtie_card.py`）：遞名帖掛上玩家卡，載入這一包時登記進 `social.ACTIONS`（原本是 `engine.py` 頂端 import 它）。
- `actions.py`：原本 `Game` 上的 6 個方法——`peers_here`、`peer`（`_peer`）、`peer_card`、`peer_request`、`peer_act`、`calls_here`。
- `invite_actions.py`：7 個——`options`（`_invite_options`）、`invite`（`_invite`）、`answer_invite`、`answer_on_card`、`greet_back`、`tell_sender`、`status`（`_invite_status`）；加 `title`（原 `_action_title` 的 invite 那一支）與兩句邀請沒成局的字（`INVITE_LAPSED`、`INVITE_LAPSED_AWAY`，`engine` 照舊拿得到）。
- `pair_actions.py`：6 個——同一對人的帳（`pair_key`、`pair_left`、`pair_tick`）與贈物（`gifts_left`、`gift_day_left`、`gift_day_tick`）。切磋、論武的帳還是它們自己用（第 38 批）。
- `mingtie_actions.py`：12 個——`shared_or_none`、`face`、`view`、`screen`、`make`、`send_problem`、`send`、`swap`、`report`、`admin_reports`、`admin_remove`、`admin_restore`。
- `spar.py`／`discuss.py`／`raid.py`（原 `tianxia/spar.py`、`discuss.py`、`raid.py`）：切磋、論武、截殺掛上玩家卡，載入這一包時登記進 `social.ACTIONS`（切磋 50、論武 55、截殺 60；通緝 65 還在 `engine.py` 頂端登記，第 45 批）。
- `spar_actions.py`：7 個——`who_problem`（論武、截殺也問）、`left`、`answer_problem`、`refusal`、`send`、`spar`、`spar_record`。
- `discuss_actions.py`：12 個——`left`、`items`、`cost_of`、`refusal`、`send`、`forge_pair`、`request`（A 段）、`forge`、`merge_problem`、`invite_problem`、`item_problem`、`discuss`（C 段），加 `DISCUSS_SAME`、`THEIR_SIDE`、`_refusal`。
  三段式的 B 段（`prepare_peer`、`screen_peer`）第 69 批進了 `routes.py`，路由照舊經 `shell.` 叫（殼留一行包裝：`tianxia/features/peers/tests/test_discuss.py` 換 `server.prepare_peer`、`server.screen_peer`）。
- `raid_actions.py`：9 個——`is_shown`、`refusal`、`odds_word`、`targets`、`raid`、`flee_odds`、`fled`、`take_spoils`、`raid_record`，加 `RAID_AFTER_CLASH`、`RAID_SHIELD_CLASH`。
  打贏的交差 `ctx._raid_bounty` 是事件 `raid_win` 的發布點（第 45 批搬進懸賞榜包 `actions.raid_bounty`，位置不動）；懸賞榜的 `hunting`、`official_hit`、`BEATEN_OFFICIAL` 三處第 45 批改讀核心 `core/bounty_base`。
- `routes.py`：`/api/peer`、`/api/peer/act`、`/api/mingtie`、`/api/mingtie/{op}`。鎖外三段式的 `screen_peer`、`prepare_peer`（論武的首創取名，第 69 批搬進來）；`screen_text`（探索包也用）、`boards_now` 留在殼，經 `shell.` 叫。
- `bots.py`：假人收到打招呼、結伴邀請、名帖的回法（`answer_call`、`_roll` 與那幾個比例）、做名帖（`_make_card`）、遞名帖（`_hand_card`），以及第 38 批搬來的答切磋（`_answer_invite`）、答論武（`answer_discuss`，首創要取名時回一份資料、由 `bot_policy._answer_discuss` 包成 `DiscussJob`；`DiscussJob` 照鐵匠鋪 `ForgeJob` 的前例留在 `bot_policy`）、截殺（`_raid`）與 `INVITE_YES`、`RAID_CHANCE`、`RAID_ODDS`（`bot_policy` 的 `CHALLENGE_ODDS` 還有 `score` 在用，所以包裡寫一份同值）；`bot_policy` 照舊 import 這幾個名字。叫它們的順序（`take_turn`）一個字不動。
- 掛鉤：`prefix = "invite"`；`choose` 接 `invite:*`（標題在動作之前拿）；`bot_always = ("invite:",)`；`on_season_start` 把這一季值得留名的頭銜寫進 `title_book`（原本在 `Game._reset_player_for_new_season`）；`routes`；
  `enabled` 一直是 `True`（名帖開關 `Config.mingtie.enabled` 只管名帖那幾顆，不管整包）。`content = ("mingtie.json",)`（名帖現成的畫與假人的自題句庫，`content.py` 照它到這一包的 `content/` 載）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`mingtie`、`mingtie_box`、`mingtie_day`、`mingtie_made`、`mingtie_sent`、`mingtie_hidden`、`taunt_muted`、`gift_day`、`gifts_today`。
- `carried`：全部（自己的名帖、收到的、檢舉過的、不接誰的挑釁話、一天的次數都跨季；第 55 批起是 `season.carry` 的 `peers` 那一格〔`actions.carry_season`〕）。
- `Game.peer_brief` 由這一包的 `scratch()` 宣告（第二輪第 92 批，不進存檔）。
- 不認領：`title_book`（過去幾季掙到的頭銜，名帖印得出來）——換季時要加上這一季掙到的，不是原樣帶走，由 `on_season_start` 接；`tagalong`（結伴同行的跟隨）屬移動包。
- 全服帳（`SharedWorldState`，不分季）：`mingtie_reports`、`mingtie_removed`、`mingtie_cleared`；這一季的 `WorldState`：`invites`、`gift_tally`。第 38 批的 `spar_tally`、`discuss_tally`、`raids`、`raided`（混戰、設伏共用）、`clashes`、`clashed`（混戰寫、截殺的拒絕話讀）：資料在核心、不認領。沒有 `PlayerState` 欄位，資料表沒改。

## 委派與留在原位的接縫

`Game` 上的名字掛在 `game_api.py` 的表（第 66 批拿掉 `_invite_status`，狀態列改走 `status_slots`）：第 38 批加了 13 個（論武 `discuss_items`、`_discuss_cost`、`discuss_problem`、`discuss_item_problem`，截殺 `raid_shown`、`raid_refusal`、`raid_odds`、`raid_targets`、`raid`、`raid_flee_odds`、`_raid_fled`、`_raid_spoils`、`_raid_record`），拿掉沒人叫的 `_pair_left`，其餘 20 個是第 37 批留的（下面括號裡第 37 批的清單，`_pair_left` 除外）（`peers_here`、`_peer`、`peer_card`、`peer_request`、`peer_act`、`calls_here`、`_invite_options`、`_invite`、`answer_invite`、`_tell_sender`、
`gift_day_left`、`_spar_pair`、`_pair_left`、`_pair_tick`、`mingtie_view`、`make_mingtie`、`report_mingtie`、`admin_mingtie_reports`、`admin_mingtie_remove`、`admin_mingtie_restore`，其中管理者三個給 server 的 `admin_choices`、`ADMIN_ACTIONS`），
另加 `_yuedan_line`（玩家卡的月旦評那一句，主人是大勢人物包，包經 `ctx` 叫）。其餘 10 個方法只有包裡叫，沒有委派。
核心原位接掛鉤的：`choose` 與 `_action_title` 的 `invite`（`Outcome`）、換季的頭銜簿（`on_season_start`）、`bot.py` 的 `invite:` 排除（`bot_always`）。
留委派、記進 `GAME_DELEGATE_CALLERS` 的：`_everyday_options` 叫 `_invite_options`（選單的順序是行為）；
結伴同行（移動包 `party.join`、`join_refusal`，第 48 批；`Game` 上的名字掛在 `game_api.py` 的表）在包裡經 `ctx` 叫 `_tell_sender`、`_peer`，不再記進 `GAME_DELEGATE_CALLERS`。第 38 批把第 37 批的 `GAME_DIRECT` 7 個（切磋、論武直接用這一包的 `social`、`invites`）與 `_PEERS_38` 的 6 筆呼叫端都拿掉；
`engine.py` 對 `invites`、`social` 的 import 也拿掉了，多 import 論武、截殺兩個動作檔（13 個委派用）與 `DISCUSS_SAME`、`_refusal` 一行（`test_discuss.py` 從 `engine` 拿的過渡；第 61 批拿掉，`test_discuss` 改讀 `discuss_actions`）。
懸賞榜第 45 批成包，截殺讀的 `hunting`、`official_hit`、`BEATEN_OFFICIAL` 三處改讀核心 `core/bounty_base`。
論武的 `discuss_actions` 讀共用層 `fusion`（合成與揣摩，第 87 批收進）。
網頁那一半（`MT_INKS` 等）第 3 階才切，這一批不碰 `web/`。

## 測試

`tianxia/features/peers/tests/`（整檔屬於這一包的，原樣搬來，只改檔頭的路徑字串）：

- `test_mingtie.py`（13 條，原 `tianxia/features/peers/tests/test_mingtie.py`）：名帖（定稿的檢查、遞與回帖、檢舉與撤下放回、假人做名帖與遞名帖）與審一句話。借 `tianxia/features/peers/tests/test_social.py` 的小工具（`NOW`、`_as`、`_done`、`_player`）。
- `test_spar.py`（18 個測試函式、參數展開 23 條，原 `tianxia/features/peers/tests/test_spar.py`，第 38 批整檔搬）：切磋（邀請、答應、婉拒、收回、戰報與經驗、假人答切磋）；改的只有路徑字串。
- `test_raid.py`（21 個測試函式、參數展開 26 條，原 `tianxia/features/peers/tests/test_raid.py`，第 38 批整檔搬）：截殺（敵對陣營、散人揭通緝、城鎮擋、新手期、冷卻與護身、混戰過的拒絕話、打贏打輸平手、假人截殺）；
  內有 5 條是混戰、設伏的呼叫端（`_melee_record`、`_ambush_record`），整檔不拆；改的只有路徑字串與假人的 patch（`monkeypatch.setattr(bots, "RAID_CHANCE", 1.0)` 改成 patch 包的 `bots`）。
- `test_peers_smoke.py`（1 條，**新寫的煙霧**，手冊 4.1 每一包至少一條）：兩人同地點互看、打開玩家卡、挑釁、乙的選單多出 `invite:` 回禮、挑一個回（這一包的 `choose` 掛鉤接走，標題「與甲」）。
- `test_season_book.py`（1 條，**合併時補**，第 37 批 PM 認定第 1 條）：換季的頭銜簿（`on_season_start`）——舊簿非空、其中一條跟這一季也掙到的重複，換季之後是舊的照順序、接上這一季新掙到的，重複的不再加（期望值照搬之前的行為寫，測試內容）。
- 不放 `peers_stage.py`：這一包不給選單（`menu` 沒接，`options` 空的，`invite:` 的選項由 `Game._everyday_options` 的 `_invite_options` 委派給，位置算行為）；契約測試的擺局面用預設的「平常」。

**不搬、另外要跑的混合檔**（含這一包的測試，但整檔不屬於這一包，不拆；數字是用到這一包的條數／全檔）：

- `test_social.py`、`test_discuss.py` 第 61 批整檔搬進這一包的 `tests/`（不拆：`test_social` 27 條裡另有 8 條是結伴同行、求見被打發與網頁字寬；其他測試檔照舊經 `from test_social import …` 借它的小工具）。
- `tianxia/features/bounties/tests/test_bounties.py`（8／56）：通緝（第 45 批成包，第 61 批搬進懸賞榜包）。
- `tests/gear/test_mounts.py`（3／53）、`tianxia/features/seal/tests/test_seal_revamp_sidedoor.py`（6／15）、`tests/server/test_server.py`（4／385）、`tianxia/features/bounties/tests/test_sanren_web.py`（1／6）、`tianxia/features/mall/tests/test_mall_bots.py`（1／3）、`tianxia/features/faction/tests/test_gentry_allied_fixes.py`（2／13）：各只有幾處經 `peer_card`、`peer_act`、`peers_here`。
- `tests/core/test_presence_window.py`（5 條）：「此地還有」的窗口（24 小時）與主機端兩支腳本刻意不跟著拉長——窗口的判斷已是核心的查詢服務（`core/presence.py`），這份留在核心測試；酒肆的 `tianxia/features/tavern/tests/test_tavern_seek_presence.py` 守「酒家說得出『此刻』不能比『此地還有』寬」，兩份不重複（一個管設定與腳本，一個管酒肆的查人），都原樣過。
- `tests/core/test_feature_boundaries.py`、`tests/core/test_contract_features.py`（核心契約）：這一包的邊界、前綴、欄位、換季都在裡面守。

## import 的規矩（手冊 3.11）

包只 import 核心、共用層、自己這一包（第二輪第 102 批硬規矩，手冊 3.11，寫註也放行不了），沒有過渡 import。`raid_actions.py` 讀核心 `core/bounty_base`。

## 量到的（第 37 批 Task 5）

包的測試 14 條 6.8 秒；改包任一檔挑到 219 條；Game 委派 21 個加 `_yuedan_line`；`GAME_DIRECT` 7 個（切磋、論武，第 38 批拿掉）；`engine.py` 9,369 行。`same_behavior` 的 `peers`、`tavern`、`roam` 三軌三種設定整段、半舊半新逐位元組一樣。細節見計畫 5.4。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`season.carry` 的 `peers`（`actions.carry_season`：名帖與一天的次數，不看開關）。

**第 56 批（選單收接縫，核心批）**：`here/invite` 是這一包登記的格；先後在 `core/features.py` 的 `MENU_ORDER`；委派 `_invite_options` 拿掉；上面寫「留委派」「原位」的以這一句為準。

## 畫面與狀態列（全部拆包第 66 批）

- 畫面：`web/peers.js`（名帖的畫法與畫布；此地還有誰、邀請、`socialHtml`、玩家卡、`peerAct` 第 67 批從 `main.js` 切進來）、`web/peers.css`；點擊分派第二輪第 84 批進這支 js；表單與 change 第 85 批。
- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`status` 表 `invites`（第一季才有）；`main` 表 `peers`（`here`、`calls`）。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `admin_tools`：`mingtie_remove`、`mingtie_restore`。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：`routes.py` 的 `prepare_peer`、`screen_peer`（路由照舊經 `shell.`；殼留一行包裝）。`screen_text` 探索包也用，留殼；`naming` 經 `shell.naming`。沒有 `/api/do/` 的 op，不接 `outlock` 掛鉤。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。另外要跑的（`test_for` 挑不到）：`tianxia/features/peers/tests/test_discuss.py`、`tests/server/test_outlock.py`。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_discuss.py`（原 `tests/arts/`）、`test_social.py`（原 `tests/core/`）。

照條拆來：`test_peers_page_web.py`（2 條，從 `tests/web/test_jianghu_page_web.py` 拆來）、`test_peers_shell.py`（3 條，從 `tests/server/test_server.py` 拆來）；兩邊都用的小工具在 `tests/kit/`（`engine_kit`、`server_kit`、`jianghu_kit`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- `bots.py` 多 `_answer_discuss`（第 101 批）。`mingtie.py`、`bots.py` 到 `leaderboard` 第 88 批起、`discuss_actions.py` 到 `fusion` 第 87 批起都是共用規則層。
- `admin_mingtie_reports` 改由這一包登記的 `admin` 表 `mingtie` 格叫，不再是 server 叫（第 90 批）。另外要跑的：改這一包的 `bots.py` 時 `test_for` 挑不到 `tests/bots/test_bot.py`、`test_bot_policy.py`、`test_bot_runner.py`。
