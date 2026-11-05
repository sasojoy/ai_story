# 玩家互動一（`tianxia/features/peers/`）

此地還有誰、玩家卡與卡上的動作登記表、邀請框（打招呼、名帖、切磋、論武、結伴同行共用的 `invite:` 選項）、打招呼、贈物、名帖（定稿、遞、回帖、檢舉、管理者撤下與放回）。全部拆包第 37 批搬進來，行為一個字不變。
切磋、論武、截殺（`spar.py`、`discuss.py`、`raid.py`）是第 38 批，通緝（`wanted.py`）是第 45 批，結伴同行是移動包，都還在原位。

- 導覽：`docs/guide/散人與玩家互動.md`（玩家卡、切磋、論武）。
- 設計稿：玩家互動（企劃者 2026-10-08）；名帖（Joy 2026-10-19，設計稿 https://claude.ai/artifact/YLTXjaX77DJRsCmMX57xAi）。
- 計畫：`docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md`。

## 裡面有什麼

- `social.py`（原 `tianxia/social.py`，舊名是別名）：玩家卡 `card`、卡上動作的登記表 `ACTIONS`／`CardAction`／`CardButton`／`register`（切磋、論武、截殺、通緝也登記進同一張）、贈物、打招呼（`Gesture`、`calls`）。
  「此地還有」的判斷（`here`、`visible`）與身分字（`side`、`affiliation`、`GONE`）不在這裡：先拆成核心的查詢服務 `tianxia/core/presence.py`（窗口 `Config.presence_seconds`），`social` 從那裡 re-export 同一批函式物件；
  酒肆（客人名單、查人）、探索（結算卡的「此地還有」）、狀態列都直接問核心。
- `invites.py`（原 `tianxia/invites.py`）：邀請的帳（`WorldState.invites`）；`mingtie.py`（原 `tianxia/mingtie.py`）：名帖的規則；`mingtie_card.py`（原 `tianxia/mingtie_card.py`）：遞名帖掛上玩家卡，載入這一包時登記進 `social.ACTIONS`（原本是 `engine.py` 頂端 import 它）。四個舊名都是指到同一個模組物件的別名。
- `actions.py`：原本 `Game` 上的 6 個方法——`peers_here`、`peer`（`_peer`）、`peer_card`、`peer_request`、`peer_act`、`calls_here`。
- `invite_actions.py`：7 個——`options`（`_invite_options`）、`invite`（`_invite`）、`answer_invite`、`answer_on_card`、`greet_back`、`tell_sender`、`status`（`_invite_status`）；加 `title`（原 `_action_title` 的 invite 那一支）與兩句邀請沒成局的字（`INVITE_LAPSED`、`INVITE_LAPSED_AWAY`，`engine` 照舊拿得到）。
- `pair_actions.py`：6 個——同一對人的帳（`pair_key`、`pair_left`、`pair_tick`）與贈物（`gifts_left`、`gift_day_left`、`gift_day_tick`）。切磋、論武的帳還是它們自己用（第 38 批）。
- `mingtie_actions.py`：12 個——`shared_or_none`、`face`、`view`、`screen`、`make`、`send_problem`、`send`、`swap`、`report`、`admin_reports`、`admin_remove`、`admin_restore`。
- `routes.py`：`/api/peer`、`/api/peer/act`、`/api/mingtie`、`/api/mingtie/{op}`。鎖外三段式的 `screen_peer`、`prepare_peer`（論武的首創取名）與 `screen_text`、`boards_now` 留在殼，經 `shell.` 叫。
- `bots.py`：假人收到打招呼、結伴邀請、名帖的回法（`answer_call`、`_roll` 與那幾個比例）、做名帖（`_make_card`）、遞名帖（`_hand_card`）；`bot_policy` 照舊 import 這幾個名字。叫它們的順序（`take_turn`）一個字不動。
- 掛鉤：`prefix = "invite"`；`choose` 接 `invite:*`（標題在動作之前拿）；`bot_always = ("invite:",)`；`on_season_start` 把這一季值得留名的頭銜寫進 `title_book`（原本在 `Game._reset_player_for_new_season`）；`routes`；
  `enabled` 一直是 `True`（名帖開關 `Config.mingtie.enabled` 只管名帖那幾顆，不管整包）。`content = ("mingtie.json",)`（名帖現成的畫與假人的自題句庫，`content.py` 照舊讀）。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`mingtie`、`mingtie_box`、`mingtie_day`、`mingtie_made`、`mingtie_sent`、`mingtie_hidden`、`taunt_muted`、`gift_day`、`gifts_today`。
- `carried`：全部（自己的名帖、收到的、檢舉過的、不接誰的挑釁話、一天的次數都跨季；`Game._reset_player_for_new_season` 照抄那幾行，留在核心）。
- 不認領：`title_book`（過去幾季掙到的頭銜，名帖印得出來）——換季時要加上這一季掙到的，不是原樣帶走，由 `on_season_start` 接；`tagalong`（結伴同行的跟隨）屬移動包。
- 全服帳（`SharedWorldState`，不分季）：`mingtie_reports`、`mingtie_removed`、`mingtie_cleared`；這一季的 `WorldState`：`invites`、`gift_tally`（`spar_tally`、`discuss_tally` 是第 38 批的）。沒有 `PlayerState` 欄位，資料表沒改。

## 委派與留在原位的接縫

`Game` 留 21 個一行委派（`peers_here`、`_peer`、`peer_card`、`peer_request`、`peer_act`、`calls_here`、`_invite_options`、`_invite`、`answer_invite`、`_tell_sender`、`_invite_status`、
`gift_day_left`、`_spar_pair`、`_pair_left`、`_pair_tick`、`mingtie_view`、`make_mingtie`、`report_mingtie`、`admin_mingtie_reports`、`admin_mingtie_remove`、`admin_mingtie_restore`，其中管理者三個給 server 的 `admin_choices`、`ADMIN_ACTIONS`），
另加 `_yuedan_line`（玩家卡的月旦評那一句，主人是大勢人物包，包經 `ctx` 叫）。其餘 10 個方法只有包裡叫，沒有委派。
核心原位接掛鉤的：`choose` 與 `_action_title` 的 `invite`（`Outcome`）、換季的頭銜簿（`on_season_start`）、`bot.py` 的 `invite:` 排除（`bot_always`）。
留委派、記進 `GAME_DELEGATE_CALLERS` 的：`_everyday_options` 叫 `_invite_options`（選單的順序是行為）、`status_data` 叫 `_invite_status`（鍵的順序是行為，總表第 66 批才接 status 掛鉤）；
`_spar`、`_discuss`、`_join`（第 38 批與移動包）叫 `_tell_sender`、`_pair_tick`、`_pair_left`、`_peer`。
`GAME_DIRECT` 新增 7 個（`_spar_answer_problem`、`spar_invite`、`spar_refusal`、`_discuss`、`discuss_invite`、`discuss_invite_problem`、`discuss_refusal`）：切磋、論武在第 38 批搬走之前直接用這一包的 `social`、`invites`，跟著拿掉。
網頁那一半（`MT_INKS` 等）第 3 階才切，這一批不碰 `web/`。

## 測試

（Task 4 補。）

## 過渡（手冊 3.11）

過渡 import 2 處：`mingtie.py` 到 `ranks`（階級的稱號，總表第 40 批收進共用規則層）、`mingtie.py` 函式裡到 `leaderboard`（賽季榜單）；`bots.py` 到 `leaderboard`（名帖頭銜的榜單名次）。
