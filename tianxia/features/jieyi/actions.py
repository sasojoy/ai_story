"""結義的動作（設計稿 v2 卷一）：玩家卡上「邀他結義」、此地還能做的「答應／婉拒」、俠客頁門下那一段的「割袍斷義」，與給畫面的那一份。
帳在全服的 SharedWorldState.jieyi（不分季），一律經 ctx.world.mutate 改；規則在 rules.py。真人假人同一套話。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.characters import name_key
from tianxia.core import cards
from tianxia.core.option import Option

from . import rules

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.world_state import JieyiBook

KIND = "jieyi"
ASK = "邀他結義"  # 待 joy 潤
YES = "{him}邀你結義：答應"  # 待 joy 潤（江湖頁「結義之邀」那一張只畫{him}邀你結義，按鈕寫答應、婉拒）
NO = "{him}邀你結義：婉拒"  # 待 joy 潤
ASK_CONFIRM = "結義之後換季也不散，要散得割袍斷義。向{him}提起結義？"  # 待 joy 潤
TITLE = "結義"


def on(ctx: Game) -> bool:
    return ctx.content.config.jieyi.enabled


def book(ctx: Game) -> JieyiBook | None:
    """全服的結義帳；記憶體裡沒有全服狀態的（某些測試）是 None。"""
    try:
        return ctx.world.read().jieyi
    except (AttributeError, NotImplementedError):
        return None


def _swapped(me, him) -> bool:
    """兩人互換過名帖：各自的名帖匣裡都收著對方的一張。"""
    a, b = name_key(me.player.name), name_key(him.player.name)
    return any(name_key(x.name) == b for x in me.player.mingtie_box) and any(name_key(x.name) == a for x in him.player.mingtie_box)


def _apart(me, him) -> bool:
    return me.player.location != him.player.location or me.player.journey is not None or him.player.journey is not None


def card_problem(game: Game, other: Game, bk: JieyiBook) -> str | None:
    me, him = game.state, other.state
    problem = rules.invite_problem(bk, game.content, me.player.name, him.player.name, game.now)
    if problem is not None:
        return problem
    if not _swapped(me, him):
        return rules.NEED_CARDS
    if _apart(me, him):
        return rules.NOT_HERE
    return None


def buttons(game: Game, other: Game) -> list[cards.CardButton]:
    if not on(game):
        return []
    bk = book(game)
    if bk is None:
        return []
    me, him = game.state.player.name, other.state.player.name
    mine, his = rules.bond_of(bk, me), rules.bond_of(bk, him)
    if mine is not None and his is not None and mine.id == his.id:  # 同一組：卡上寫你們同為某某、他排行第幾，不給按
        return [cards.CardButton(
            action=KIND, arg="", label=rules.SAME.format(bond=rules.bond_name(bk, game.content, mine)),
            note=f"他排行第{rules.num(rules.rank_of(mine, him))}", enabled=False,
        )]
    pending = rules.offer_between(bk, me, him, game.now)
    if pending is not None:
        asked_me = name_key(pending.target) == name_key(me)
        return [cards.CardButton(action=KIND, arg="", label=ASK, enabled=False, note=rules.HE_ASKED if asked_me else rules.WAITING)]
    problem = card_problem(game, other, bk)
    note = problem or (f"入{rules.bond_name(bk, game.content, mine)}" if mine is not None else "")
    return [cards.CardButton(
        action=KIND, arg="ask", label=ASK, enabled=problem is None, note=note,
        confirm="" if problem else ASK_CONFIRM.format(him=him),
    )]


def run(game: Game, other: Game, params: dict) -> list[str]:
    """卡上「邀他結義」按下去：在行動鎖裡再驗一次，記一張邀請。"""
    if not on(game) or params.get("arg") != "ask":
        return [rules.GONE]
    out: list[str] = []
    me, him = game.state.player, other.state.player

    def _apply(shared) -> None:
        bk = shared.jieyi
        rules.expire(bk, game.now)
        if rules.offer_between(bk, me.name, him.name, game.now) is not None:
            out.append(rules.WAITING + "。")
            return
        problem = card_problem(game, other, bk)
        if problem is not None:
            out.append(problem + "。")
            return
        rules.send(bk, game.content, me.name, him.name, me.location, game.now)
        out.append(rules.SENT.format(him=him.name))

    game.world.mutate(_apply)
    return out


cards.register(cards.CardAction(id=KIND, buttons=buttons, run=run, order=18))  # 名帖（15）底下


def options(ctx: Game) -> list[Option]:
    """有人邀你結義：此地還能做裡一張一對「答應／婉拒」（不在同一地方也回得了）。"""
    bk = book(ctx)
    if bk is None:
        return []
    out: list[Option] = []
    for offer in rules.incoming(bk, ctx.state.player.name, ctx.now):
        out.append(Option(id=f"{KIND}:yes:{offer.id}", label=YES.format(him=offer.sender)))
        out.append(Option(id=f"{KIND}:no:{offer.id}", label=NO.format(him=offer.sender)))
    return out


def answer(ctx: Game, arg: str) -> list[str]:
    """jieyi:yes:<編號>、jieyi:no:<編號>。"""
    verb, _, offer_id = arg.partition(":")
    out: list[str] = []
    me = ctx.state.player

    def _apply(shared) -> None:
        bk = shared.jieyi
        offer = rules.find(bk, offer_id, ctx.now)
        if offer is None or name_key(offer.target) != name_key(me.name) or verb not in ("yes", "no"):
            out.append(rules.GONE)
            return
        if verb == "no":
            rules.drop(bk, offer.id)
            out.append(rules.DECLINED.format(him=offer.sender))
            return
        out.append(rules.accept(bk, ctx.content, offer, me.season_number, ctx.now))

    ctx.world.mutate(_apply)
    return out


def leave(ctx: Game) -> list[str]:
    """割袍斷義（俠客頁門下那一段的鈕，/api/do/jieyi_leave）。寫一則江湖紀錄。"""
    if not on(ctx):
        return [rules.NO_BOND]
    out: list[str] = []
    ctx.world.mutate(lambda shared: out.append(rules.leave(shared.jieyi, ctx.content, ctx.state.player.name, ctx.state.player.season_number, ctx.now)))
    return ctx._log(out)


def view(ctx: Game) -> dict | None:
    """俠客頁門下那一段（status 的 jieyi）：沒結義、也沒有冷卻時是 None（不畫）。"""
    bk = book(ctx)
    if bk is None:
        return None
    me = ctx.state.player.name
    bond = rules.bond_of(bk, me)
    if bond is None:
        left = rules.cooling(bk, ctx.content.config.jieyi, me, ctx.now)
        return {"cooling": rules.COOLING.format(hours=max(1, int(left // 3600) + (1 if left % 3600 else 0)))} if left > 0 else None
    return {
        "name": rules.bond_name(bk, ctx.content, bond),
        "rank": rules.num(rules.rank_of(bond, me)),
        "members": [{"name": m, "rank": rules.num(i + 1), "me": name_key(m) == name_key(me)} for i, m in enumerate(bond.members)],
        "log": list(reversed(bond.log)),
        "leave_confirm": LEAVE_CONFIRM.format(
            bond=rules.bond_name(bk, ctx.content, bond), hours=max(1, round(ctx.content.config.jieyi.cooldown_seconds / 3600)),
        ),
    }


LEAVE_CONFIRM = "割袍斷義就離開{bond}，{hours} 小時內不能再結義。確定？"  # 待 joy 潤
