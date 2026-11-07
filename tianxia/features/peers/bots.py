"""假人收到打招呼、結伴邀請與名帖的回法，與做名帖、遞名帖（開發規範手冊 3.8；原本寫在 bot_policy.py：answer_call、_roll、_make_card、_hand_card
與那幾個比例常數，全部拆包第 37 批搬來）。bot_policy 照舊 import 這幾個名字（tianxia/features/peers/tests/test_social.py 用 bot_policy.answer_call 與 REPLY_MIN_SECONDS）；
呼叫的順序（_answer_discuss → _answer_invite → answer_call → 結伴等著 → 集結 → _raid → _hand_card）一個字不動，留在 bot_policy.take_turn。

邀請框的 invite: 前綴這一包拿了：假人看到 invite: 的選項分數是 None（不按；上面三個函式直接回應，不交給打分數亂按），跟搬包之前 score 走到最後 return None 一樣。
假人之間跟真人完全一樣、看不出來：這裡走玩家卡同一條路，任何畫面都不寫誰是假人。

_answer_discuss（包成取名單）第二輪第 101 批從 bot_policy 搬來，舊名 re-export 同一個函式；NamingSlot、DiscussJob 在共用層 bot_base，一律寫 `bot_base.X`。
"""
from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

from tianxia import bot_base
from tianxia import leaderboard  # 過渡：待搬（賽季榜單：名帖頭銜的榜單名次）
from tianxia.state import BotProfile, Invite

from . import actions, invites, mingtie_actions, raid_actions, social
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
# 切磋、論武、截殺（全部拆包第 38 批從 bot_policy.py 搬來；bot_policy 照舊 import 這幾個名字，測試與 same_behavior 兩邊都換）
INVITE_YES = 0.7  # 有人邀切磋、論武時答應的機會（付得起體力才算）【預設】
# 截殺（Config.raid）：此地有截殺得了、而且勝算夠的敵對陣營的人時，每一輪有 RAID_CHANCE 的機會動手；只挑 RAID_ODDS 的對象
# （輸了要丟銀兩、掉氣血，跟挑戰大勢人物同一個標準）。真人被假人截殺跟被真人截殺一模一樣【預設】
RAID_CHANCE = 0.1
RAID_ODDS = ("穩勝", "有把握")  # 同 bot_policy.CHALLENGE_ODDS（bot.CHALLENGE_ODDS）；包不 import bot_policy，照 SMITH_SCORE 的前例寫一份同值
NO_NAME: tuple[str | None, str] = (None, "")  # 開爐的 C 段不必取名：鎖內一定不叫模型（同 server.NO_NAME、bot_policy.NO_NAME）


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


def _answer_invite(game: Game, rng: random.Random) -> str | None:
    """有人在這裡邀假人切磋（玩家互動第二層）：跟真人一樣在自己這一輪看到才答——付得起體力時 INVITE_YES 的機會答應，
    其餘婉拒（真人也會婉拒，假人不能每一張都答應，不然看得出來）。一次只答一張，最早的那張。沒有邀請是 None。"""
    world = game.state.world
    incoming = [  # 論武的邀請由 answer_discuss 答（選單上那一顆是灰的，要在玩家卡上挑出哪一樣）
        o for o in game.options(odds=False, tick=False) if o.id.startswith("invite:yes:")
        and getattr(invites.find(world, o.id.removeprefix("invite:yes:")), "kind", "") == "spar"
    ]
    if not incoming:
        return None
    first = incoming[0]
    if first.enabled and rng.random() < INVITE_YES:
        return first.id
    return "invite:no:" + first.id.removeprefix("invite:yes:")


def answer_discuss(game: Game, rng: random.Random, slot_open: bool) -> list[str] | tuple[str, str, object] | None:
    """有人在這裡邀假人論武：跟切磋一樣 INVITE_YES 的機會答應，挑第一樣自己這邊合得成的（身上的在前）出；挑不到就婉拒。
    走玩家卡同一條路（actions.peer_request、peer_act）。首創要取名時回 (發邀請的人, 出哪一樣, 取名單)，由 bot_policy 包成 DiscussJob 放進取名的名額
    （這一輪到此為止，B、C 段在 bot_runner；DiscussJob 照鐵匠鋪 ForgeJob 的前例留在 bot_policy，包不 import bot_policy）；
    這一輪沒有取名的名額（slot_open 是 False）就先放著（邀請還在，下一輪再答）、照常做別的事（回 None）。沒有論武邀請也是 None。
    擲骰的先後（rng.random() 在 peer_request 之前）一個字不動。"""
    p = game.state.player
    pending = [i for i in invites.incoming(game.state.world, p.name) if i.kind == "discuss" and i.location == p.location]
    if not pending or not game.is_idle():
        return None
    inv = pending[0]
    # 照玩家卡上答應的那幾顆挑（跟真人看到的同一張卡）：按得下去的就是兩邊都合得成的（discuss._answer_buttons，FB-117）
    card = actions.peer_card(game, inv.sender)
    ready = [
        b["arg"].removeprefix("yes:") for b in (card or {}).get("actions", [])
        if b["action"] == "discuss" and b["enabled"] and b["arg"].startswith("yes:")
    ]
    item = ready[0] if ready else None
    if item is None or rng.random() >= INVITE_YES:  # 他走了（卡打不開）、一樣都合不成：收掉這張
        return game.choose(f"invite:no:{inv.id}")
    params = {"arg": f"yes:{item}"}
    request = actions.peer_request(game, inv.sender, "discuss", params)
    if request is None:
        return actions.peer_act(game, inv.sender, "discuss", {**params, "proposed": NO_NAME})
    if not slot_open:
        return None
    return (inv.sender, item, request)


def _raid(game: Game, rng: random.Random) -> list[str] | None:
    """此地有截殺得了、勝算在 RAID_ODDS 的人時，RAID_CHANCE 的機會截殺第一個（走玩家卡同一條路，actions.peer_act）。
    沒有對象時不擲骰（不改到其他行為的亂數）；這一輪不動手是 None。"""
    targets = [name for name, odds in raid_actions.targets(game) if odds in RAID_ODDS]
    if not targets or rng.random() >= RAID_CHANCE:
        return None
    return actions.peer_act(game, targets[0], "raid")


def _answer_discuss(game: Game, rng: random.Random, slot: bot_base.NamingSlot | None) -> list[str] | None:
    """有人在這裡邀假人論武（本體在玩家互動包 peers/bots.answer_discuss，全部拆包第 38 批）。首創要取名時包回來一份資料，
    這裡包成 DiscussJob 放進 slot（這一輪到此為止，B、C 段在 bot_runner）；其餘（婉拒、直接答、沒名額先放著、沒有邀請）原樣回。"""
    got = answer_discuss(game, rng, slot is not None and slot.open)
    if isinstance(got, tuple):
        slot.job = bot_base.DiscussJob(*got)
        return []
    return got
