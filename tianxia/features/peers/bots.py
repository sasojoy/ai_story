"""假人收到打招呼、結伴邀請與名帖的回法，與做名帖、遞名帖（開發規範手冊 3.8；原本寫在 bot_policy.py：answer_call、_roll、_make_card、_hand_card
與那幾個比例常數，全部拆包第 37 批搬來）。bot_policy 照舊 import 這幾個名字（tests/core/test_social.py 用 bot_policy.answer_call 與 REPLY_MIN_SECONDS）；
呼叫的順序（_answer_discuss → _answer_invite → answer_call → 結伴等著 → 集結 → _raid → _hand_card）一個字不動，留在 bot_policy.take_turn。

邀請框的 invite: 前綴這一包拿了：假人看到 invite: 的選項分數是 None（不按；上面三個函式直接回應，不交給打分數亂按），跟搬包之前 score 走到最後 return None 一樣。
假人之間跟真人完全一樣、看不出來：這裡走玩家卡同一條路，任何畫面都不寫誰是假人。
"""
from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

from tianxia import leaderboard  # 過渡：待搬（賽季榜單：名帖頭銜的榜單名次）
from tianxia.state import BotProfile, Invite

from . import actions, invites, mingtie_actions, social
from . import mingtie as mingtie

if TYPE_CHECKING:
    from tianxia.engine import Game

# 打招呼、結伴邀請（玩家互動第二層）照人的步調回：不會一收到就回，有時回、有時拒、有時不理（等它逾時）。
# 真的回的時刻還要等假人下一次出手（在線時 1～3 分鐘一次），所以實際的延遲比這裡寫的更散【預設】
REPLY_MIN_SECONDS = 30  # 收到之後至少隔這麼多現實秒數才回
REPLY_SPREAD_SECONDS = 150  # 再加上 0～這麼多秒（每一件各擲一次，同一件永遠一樣）
GREET_REPLY_SHARE = 0.65  # 打招呼：回禮的比例，其餘不理
TRAVEL_ACCEPT_SHARE = 0.4  # 結伴邀請：答應的比例
TRAVEL_REJECT_SHARE = 0.3  # 婉拒的比例；其餘不理
MINGTIE_ACCEPT_SHARE = 0.7  # 有人遞名帖：回帖的比例（Joy 2026-10-19）
MINGTIE_REJECT_SHARE = 0.1  # 婉拒的比例；其餘不理
MINGTIE_SEND_CHANCE = 0.03  # 每一輪向此地一個還沒換過帖的人遞名帖的機會【預設】


def _roll(profile: BotProfile, invite: Invite, salt: str) -> float:
    """這個假人對這一張的決定性擲骰（0～1）：同一張、同一個假人永遠一樣，所以每一輪重看不會改主意。"""
    digest = hashlib.sha256(f"{profile.seed}|{invite.id}|{salt}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def answer_call(game: Game, profile: BotProfile) -> str | None:
    """別人遞過來的打招呼、結伴邀請（玩家互動第二層），要回的那一個選項（invite:<回應>:<編號>，跟真人按的同一顆）；這一輪不回是 None。
    每一張先等一段（收到之後 REPLY_MIN_SECONDS＋擲出來的一段現實秒），再照擲骰回、拒或不理；結伴答應不了（手上有事、對方走了）就婉拒。
    一輪只回一張，最早的那張先。"""
    s = game.state
    menu = {o.id for o in game.options(odds=False, tick=False) if o.enabled and o.id.startswith("invite:")}
    for inv in invites.incoming(s.world, s.player.name):
        if inv.kind not in ("greet", "travel", "mingtie"):
            continue
        waited = (s.world.time - inv.sent_at) / game.content.config.time_scale
        if waited < REPLY_MIN_SECONDS + _roll(profile, inv, "wait") * REPLY_SPREAD_SECONDS:
            continue
        roll = _roll(profile, inv, "answer")
        gesture = social.gesture_of(inv)
        if gesture is not None:
            if roll >= GREET_REPLY_SHARE:
                continue
            verb = gesture.replies[int(_roll(profile, inv, "which") * len(gesture.replies))][0]
        elif inv.kind == "mingtie":
            if roll < MINGTIE_ACCEPT_SHARE:
                verb = "yes"
            elif roll < MINGTIE_ACCEPT_SHARE + MINGTIE_REJECT_SHARE:
                verb = "no"
            else:
                continue
        elif roll < TRAVEL_ACCEPT_SHARE:
            verb = "yes" if game.join_refusal(inv.sender) is None else "no"
        elif roll < TRAVEL_ACCEPT_SHARE + TRAVEL_REJECT_SHARE:
            verb = "no"
        else:
            continue
        option = f"invite:{verb}:{inv.id}"
        if option in menu:
            return option
    return None


def _make_card(game: Game) -> None:
    """還沒有名帖就做一張（Joy 2026-10-19「假人也做名帖」）：現成的畫、句庫或留空、照雜湊挑頭銜（mingtie.bot_card），
    走 mingtie_actions.make（跟真人按定稿同一條；不叫模型：句庫的句子本來就過得了字表）。頭銜的榜單名次照此刻掃一次榜。"""
    p, c = game.state.player, game.content
    if p.mingtie is not None or not c.config.mingtie.enabled:
        return
    board = leaderboard.compute_boards(c, game.world, top=10) if hasattr(game.world, "db") else None
    card = mingtie.bot_card(game.state, c, mingtie.earned(game.state, c, game.world, board))
    mingtie_actions.make(game, card.strokes, card.titles, card.motto, board=board)


def _hand_card(game: Game, rng: random.Random) -> list[str] | None:
    """有名帖、今天還能遞時，MINGTIE_SEND_CHANCE 的機會向此地一個遞得了的人遞名帖（走玩家卡同一條路）。先擲骰再看此地有誰。"""
    if game.state.player.mingtie is None or rng.random() >= MINGTIE_SEND_CHANCE:
        return None
    for peer in actions.peers_here(game):
        card = actions.peer_card(game, peer["name"])
        ready = [b for b in (card or {}).get("actions", []) if b["action"] == "mingtie" and b["arg"] == "send" and b["enabled"]]
        if ready:
            return actions.peer_act(game, peer["name"], "mingtie", {"arg": "send"})
    return None
