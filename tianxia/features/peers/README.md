# 玩家互動一（`tianxia/features/peers/`）

此地還有誰、玩家卡與卡上的動作登記表、邀請框（打招呼、名帖、切磋、論武、結伴同行共用的 `invite:` 選項）、打招呼、贈物、名帖（定稿、遞、回帖、檢舉、管理者撤下與放回）。全部拆包第 37 批搬進來，行為一個字不變。
第 38 批再搬進來：切磋、論武（三段式首創取名）、截殺（含策馬脫身），與假人答切磋、答論武、截殺（`spar`、`discuss`、`raid` 三個模組，舊名留別名）。
通緝（`wanted.py`）是第 45 批，還在原位；結伴同行（`_join`、`join_refusal`）第 48 批搬進移動包（`tianxia/features/travel/party.py`，Game 留一行委派）。

- 導覽：`docs/guide/散人與玩家互動.md`（玩家卡、切磋、論武）。
- 設計稿：玩家互動（企劃者 2026-10-08）；名帖（Joy 2026-10-19，設計稿 https://claude.ai/artifact/YLTXjaX77DJRsCmMX57xAi）。
- 計畫：`docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md`、`docs/superpowers/plans/2026-11-07-玩家互動包-第2批.md`。

## 裡面有什麼

- `social.py`（原 `tianxia/social.py`，舊名是別名）：玩家卡 `card`、卡上動作的登記表 `ACTIONS`／`CardAction`／`CardButton`／`register`（切磋、論武、截殺、通緝也登記進同一張）、贈物、打招呼（`Gesture`、`calls`）。
  「此地還有」的判斷（`here`、`visible`）與身分字（`side`、`affiliation`、`GONE`）不在這裡：先拆成核心的查詢服務 `tianxia/core/presence.py`（窗口 `Config.presence_seconds`），`social` 從那裡 re-export 同一批函式物件；
  酒肆（客人名單、查人）、探索（結算卡的「此地還有」）、狀態列都直接問核心。
- `invites.py`（原 `tianxia/invites.py`）：邀請的帳（`WorldState.invites`）；`mingtie.py`（原 `tianxia/mingtie.py`）：名帖的規則；`mingtie_card.py`（原 `tianxia/mingtie_card.py`）：遞名帖掛上玩家卡，載入這一包時登記進 `social.ACTIONS`（原本是 `engine.py` 頂端 import 它）。四個舊名都是指到同一個模組物件的別名。
- `actions.py`：原本 `Game` 上的 6 個方法——`peers_here`、`peer`（`_peer`）、`peer_card`、`peer_request`、`peer_act`、`calls_here`。
- `invite_actions.py`：7 個——`options`（`_invite_options`）、`invite`（`_invite`）、`answer_invite`、`answer_on_card`、`greet_back`、`tell_sender`、`status`（`_invite_status`）；加 `title`（原 `_action_title` 的 invite 那一支）與兩句邀請沒成局的字（`INVITE_LAPSED`、`INVITE_LAPSED_AWAY`，`engine` 照舊拿得到）。
- `pair_actions.py`：6 個——同一對人的帳（`pair_key`、`pair_left`、`pair_tick`）與贈物（`gifts_left`、`gift_day_left`、`gift_day_tick`）。切磋、論武的帳還是它們自己用（第 38 批）。
- `mingtie_actions.py`：12 個——`shared_or_none`、`face`、`view`、`screen`、`make`、`send_problem`、`send`、`swap`、`report`、`admin_reports`、`admin_remove`、`admin_restore`。
- `spar.py`／`discuss.py`／`raid.py`（原 `tianxia/spar.py`、`discuss.py`、`raid.py`，舊名是別名）：切磋、論武、截殺掛上玩家卡，載入這一包時登記進 `social.ACTIONS`（切磋 50、論武 55、截殺 60；通緝 65 還在 `engine.py` 頂端登記，第 45 批）。
- `spar_actions.py`：7 個——`who_problem`（論武、截殺也問）、`left`、`answer_problem`、`refusal`、`send`、`spar`、`spar_record`。
- `discuss_actions.py`：12 個——`left`、`items`、`cost_of`、`refusal`、`send`、`forge_pair`、`request`（A 段）、`forge`、`merge_problem`、`invite_problem`、`item_problem`、`discuss`（C 段），加 `DISCUSS_SAME`、`THEIR_SIDE`、`_refusal`。
  三段式的 B 段（`server.prepare_peer`、`screen_peer`）照手冊 G10 留在 `server.py`，經 `shell.` 叫。
- `raid_actions.py`：9 個——`is_shown`、`refusal`、`odds_word`、`targets`、`raid`、`flee_odds`、`fled`、`take_spoils`、`raid_record`，加 `RAID_AFTER_CLASH`、`RAID_SHIELD_CLASH`。
  打贏的交差 `ctx._raid_bounty` 是事件 `raid_win` 的發布點（懸賞榜，第 45 批），位置不動；懸賞榜的 `hunting`、`official_hit`、`BEATEN_OFFICIAL` 三處讀法標過渡（第 45 批）。
- `routes.py`：`/api/peer`、`/api/peer/act`、`/api/mingtie`、`/api/mingtie/{op}`。鎖外三段式的 `screen_peer`、`prepare_peer`（論武的首創取名）與 `screen_text`、`boards_now` 留在殼，經 `shell.` 叫。
- `bots.py`：假人收到打招呼、結伴邀請、名帖的回法（`answer_call`、`_roll` 與那幾個比例）、做名帖（`_make_card`）、遞名帖（`_hand_card`），以及第 38 批搬來的答切磋（`_answer_invite`）、答論武（`answer_discuss`，首創要取名時回一份資料、由 `bot_policy._answer_discuss` 包成 `DiscussJob`；`DiscussJob` 照鐵匠鋪 `ForgeJob` 的前例留在 `bot_policy`）、截殺（`_raid`）與 `INVITE_YES`、`RAID_CHANCE`、`RAID_ODDS`（`bot_policy` 的 `CHALLENGE_ODDS` 還有 `score` 在用，所以包裡寫一份同值）；`bot_policy` 照舊 import 這幾個名字。叫它們的順序（`take_turn`）一個字不動。
- 掛鉤：`prefix = "invite"`；`choose` 接 `invite:*`（標題在動作之前拿）；`bot_always = ("invite:",)`；`on_season_start` 把這一季值得留名的頭銜寫進 `title_book`（原本在 `Game._reset_player_for_new_season`）；`routes`；
  `enabled` 一直是 `True`（名帖開關 `Config.mingtie.enabled` 只管名帖那幾顆，不管整包）。`content = ("mingtie.json",)`（名帖現成的畫與假人的自題句庫，`content.py` 照舊讀）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`mingtie`、`mingtie_box`、`mingtie_day`、`mingtie_made`、`mingtie_sent`、`mingtie_hidden`、`taunt_muted`、`gift_day`、`gifts_today`。
- `carried`：全部（自己的名帖、收到的、檢舉過的、不接誰的挑釁話、一天的次數都跨季；`Game._reset_player_for_new_season` 照抄那幾行，留在核心）。
- 不認領：`title_book`（過去幾季掙到的頭銜，名帖印得出來）——換季時要加上這一季掙到的，不是原樣帶走，由 `on_season_start` 接；`tagalong`（結伴同行的跟隨）屬移動包。
- 全服帳（`SharedWorldState`，不分季）：`mingtie_reports`、`mingtie_removed`、`mingtie_cleared`；這一季的 `WorldState`：`invites`、`gift_tally`。第 38 批的 `spar_tally`、`discuss_tally`、`raids`、`raided`（混戰、設伏共用）、`clashes`、`clashed`（混戰寫、截殺的拒絕話讀）：資料在核心、不認領。沒有 `PlayerState` 欄位，資料表沒改。

## 委派與留在原位的接縫

`Game` 現在留 33 個一行委派：第 38 批加了 13 個（論武 `discuss_items`、`_discuss_cost`、`discuss_problem`、`discuss_item_problem`，截殺 `raid_shown`、`raid_refusal`、`raid_odds`、`raid_targets`、`raid`、`raid_flee_odds`、`_raid_fled`、`_raid_spoils`、`_raid_record`），拿掉沒人叫的 `_pair_left`，其餘 20 個是第 37 批留的（下面括號裡第 37 批的清單，`_pair_left` 除外）（`peers_here`、`_peer`、`peer_card`、`peer_request`、`peer_act`、`calls_here`、`_invite_options`、`_invite`、`answer_invite`、`_tell_sender`、`_invite_status`、
`gift_day_left`、`_spar_pair`、`_pair_left`、`_pair_tick`、`mingtie_view`、`make_mingtie`、`report_mingtie`、`admin_mingtie_reports`、`admin_mingtie_remove`、`admin_mingtie_restore`，其中管理者三個給 server 的 `admin_choices`、`ADMIN_ACTIONS`），
另加 `_yuedan_line`（玩家卡的月旦評那一句，主人是大勢人物包，包經 `ctx` 叫）。其餘 10 個方法只有包裡叫，沒有委派。
核心原位接掛鉤的：`choose` 與 `_action_title` 的 `invite`（`Outcome`）、換季的頭銜簿（`on_season_start`）、`bot.py` 的 `invite:` 排除（`bot_always`）。
留委派、記進 `GAME_DELEGATE_CALLERS` 的：`_everyday_options` 叫 `_invite_options`（選單的順序是行為）、`status_data` 叫 `_invite_status`（鍵的順序是行為，總表第 66 批才接 status 掛鉤）；
結伴同行（移動包 `party.join`、`join_refusal`，第 48 批；Game 留一行委派）在包裡經 `ctx` 叫 `_tell_sender`、`_peer`，不再記進 `GAME_DELEGATE_CALLERS`。第 38 批把第 37 批的 `GAME_DIRECT` 7 個（切磋、論武直接用這一包的 `social`、`invites`）與 `_PEERS_38` 的 6 筆呼叫端都拿掉；
`engine.py` 對 `invites`、`social` 的 import 也拿掉了，多 import 論武、截殺兩個動作檔（13 個委派用）與 `DISCUSS_SAME`、`_refusal` 一行（`tests/arts/test_discuss.py` 從 `engine` 拿的過渡）。
懸賞榜（`bounties`）是舊模組，截殺 import 它一行、用 `hunting`、`official_hit`、`BEATEN_OFFICIAL` 三處，標「過渡：待搬（第 45 批）」。
論武的 `discuss_actions` 還 import 舊模組 `fusion`（合成與揣摩，在 `SHARED_LATER`，標「過渡：待搬」），所以包到舊模組共 4 處：`mingtie.py`、`bots.py` 的 `leaderboard`，加 `bounties`、`fusion`。
網頁那一半（`MT_INKS` 等）第 3 階才切，這一批不碰 `web/`。

## 測試

`tianxia/features/peers/tests/`（整檔屬於這一包的，原樣搬來，只改檔頭的路徑字串）：

- `test_mingtie.py`（13 條，原 `tests/bots/test_mingtie.py`）：名帖（定稿的檢查、遞與回帖、檢舉與撤下放回、假人做名帖與遞名帖）與審一句話。借 `tests/core/test_social.py` 的小工具（`NOW`、`_as`、`_done`、`_player`）。
- `test_spar.py`（18 個測試函式、參數展開 23 條，原 `tests/battle/test_spar.py`，第 38 批整檔搬）：切磋（邀請、答應、婉拒、收回、戰報與經驗、假人答切磋）；改的只有路徑字串。
- `test_raid.py`（21 個測試函式、參數展開 26 條，原 `tests/ranger/test_raid.py`，第 38 批整檔搬）：截殺（敵對陣營、散人揭通緝、城鎮擋、新手期、冷卻與護身、混戰過的拒絕話、打贏打輸平手、假人截殺）；
  內有 5 條是混戰、設伏的呼叫端（`_melee_record`、`_ambush_record`），整檔不拆；改的只有路徑字串與假人的 patch（`monkeypatch.setattr(bots, "RAID_CHANCE", 1.0)` 改成 patch 包的 `bots`）。
- `test_peers_smoke.py`（1 條，**新寫的煙霧**，手冊 4.1 每一包至少一條）：兩人同地點互看、打開玩家卡、挑釁、乙的選單多出 `invite:` 回禮、挑一個回（這一包的 `choose` 掛鉤接走，標題「與甲」）。
- `test_season_book.py`（1 條，**合併時補**，第 37 批 PM 認定第 1 條）：換季的頭銜簿（`on_season_start`）——舊簿非空、其中一條跟這一季也掙到的重複，換季之後是舊的照順序、接上這一季新掙到的，重複的不再加（期望值照搬之前的行為寫，測試內容）。
- 不放 `peers_stage.py`：這一包不給選單（`menu` 沒接，`options` 空的，`invite:` 的選項由 `Game._everyday_options` 的 `_invite_options` 委派給，位置算行為）；契約測試的擺局面用預設的「平常」。

**不搬、另外要跑的混合檔**（含這一包的測試，但整檔不屬於這一包，不拆；數字是用到這一包的條數／全檔）：

- `tests/core/test_social.py`（19／27）：此地還有、玩家卡、贈物、挑釁與回禮、假人回的步調；另外 8 條是結伴同行（移動包）、求見被打發（交友求見包）與網頁字寬（網頁），所以整檔不搬。其他測試檔經 `from test_social import …` 借它的小工具。
- `tests/arts/test_discuss.py`（論武；59 條，`test_social`、`test_server` 用裸名從它拿小工具、它自己又有網頁測試，第 41 批認定第 6 條不搬，歸第 61 批）、`tests/ranger/test_bounties.py`（8／56）：通緝（第 45 批）。
  `tests/core/test_social.py` 整檔也留著（第 37 批認定第 6 條寫「第 38 批搬結伴時再看」，結伴同行是移動包；27 條裡真的是結伴的只有 3 條，不拆，歸第 61 批）。
- `tests/gear/test_mounts.py`（3／53）、`tests/seal/test_seal_revamp_sidedoor.py`（6／15）、`tests/server/test_server.py`（4／385）、`tests/web/test_sanren_web.py`（1／6）、`tianxia/features/mall/tests/test_mall_bots.py`（1／3）、`tianxia/features/faction/tests/test_gentry_allied_fixes.py`（2／13）：各只有幾處經 `peer_card`、`peer_act`、`peers_here`。
- `tests/core/test_presence_window.py`（5 條）：「此地還有」的窗口（24 小時）與主機端兩支腳本刻意不跟著拉長——窗口的判斷已是核心的查詢服務（`core/presence.py`），這份留在核心測試；酒肆的 `tianxia/features/tavern/tests/test_tavern_seek_presence.py` 守「酒家說得出『此刻』不能比『此地還有』寬」，兩份不重複（一個管設定與腳本，一個管酒肆的查人），都原樣過。
- `tests/core/test_feature_boundaries.py`、`tests/core/test_contract_features.py`（核心契約）：這一包的邊界、前綴、欄位、換季都在裡面守。

## 過渡（手冊 3.11）

過渡 import 4 處（全部拆包第 38 批合完重印）：`mingtie.py` 函式裡到 `leaderboard`（賽季榜單）；`bots.py` 到 `leaderboard`（名帖頭銜的榜單名次）；第 38 批加的 `discuss_actions.py` 到 `fusion`（合成與揣摩，`SHARED_LATER`）與 `raid_actions.py` 到 `bounties`（懸賞榜，標「待搬（第 45 批）」）。`mingtie.py` 到 `ranks`（階級的稱號）第 40 批收進共用規則層，不算過渡（原本 3 處）。

## 量到的（第 37 批 Task 5）

包的測試 14 條 6.8 秒；改包任一檔挑到 219 條；過渡 3 處；Game 委派 21 個加 `_yuedan_line`；`GAME_DIRECT` 7 個（切磋、論武，第 38 批拿掉）；`engine.py` 9,369 行。`same_behavior` 的 `peers`、`tavern`、`roam` 三軌三種設定整段、半舊半新逐位元組一樣。細節見計畫 5.4。
