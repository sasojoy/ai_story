"""結義的動作（設計稿 v2 卷一）：玩家卡上「邀他結義」、此地還能做的「答應／婉拒」、俠客頁門下那一段的「割袍斷義」，與給畫面的那一份。
帳在全服的 SharedWorldState.jieyi（不分季），一律經 ctx.world.mutate 改；規則在 rules.py。真人假人同一套話。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import calendar
from tianxia.characters import name_key
from tianxia.core import annal_base as annals
from tianxia.core import cards, presence
from tianxia.core.option import Option
from tianxia.state import Rumor

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
# 待 joy 潤：替兄出頭與名分（第一批）
FEUD_TOLD = "你的兄弟{victim}在{place}被{raider}截殺了。{hours} 小時內在同一個地方遇到{raider}，他的卡上能「替兄出頭」。"
FEUD_PAID = "{who}替你向{raider}討回了這口氣，追回 {silver} 兩交到你手上。"
FEUD_DONE = "{who}替你向{raider}討回了這口氣。"


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


def _day(ctx: Game) -> str:
    """義聚一天一次的「今天」：季＋季曆天（換季重算）。"""
    w = ctx.state.world
    return f"{ctx.state.player.season_number}:{calendar.world_day(w.time, ctx.content, w)}"


def present_brothers(ctx: Game, bk: JieyiBook) -> list[str]:
    """此刻跟你同一個地方的結義兄弟（「此地還有」列得出來的，照排行）；你在路上、沒結義是空的。"""
    bond = rules.bond_of(bk, ctx.state.player.name)
    if bond is None or ctx.state.player.journey is not None:
        return []
    here = {name_key(o.player.name) for o in presence.here(ctx) if o.player.journey is None}
    me = name_key(ctx.state.player.name)
    return [m for m in bond.members if name_key(m) != me and name_key(m) in here]


def gather_view(ctx: Game, bk: JieyiBook) -> dict | None:
    """義聚那一格（俠客的金蘭帖上、此地還能做）：沒結義是 None；有兄弟在此、今天還沒聚過才 ready。"""
    if rules.bond_of(bk, ctx.state.player.name) is None:
        return None
    if rules.gathered_today(bk, ctx.state.player.name, _day(ctx)):
        return {"ready": False, "note": rules.GATHER_AGAIN}
    mates = present_brothers(ctx, bk)
    if not mates:
        return {"ready": False, "note": rules.GATHER_ALONE}
    n = rules.gather_amount(ctx.content.config.jieyi, len(mates) + 1)
    return {"ready": True, "mates": mates, "n": n, "label": rules.GATHER_LABEL.format(names="、".join(mates), n=n)}


def gather(ctx: Game) -> list[str]:
    """jieyi:gather：義聚。在行動鎖裡再驗一次（兄弟還在、今天還沒聚過），回體力（不超過上限）。"""
    bk = book(ctx)
    if not on(ctx) or bk is None:
        return [rules.GONE]
    mates = present_brothers(ctx, bk)
    p = ctx.state.player
    got: list = [0, ""]

    def _apply(shared) -> None:
        live = [m for m in mates if rules.bond_of(shared.jieyi, m) is rules.bond_of(shared.jieyi, p.name)]
        got[0], got[1] = rules.gather(shared.jieyi, ctx.content, p.name, live, p.location, p.season_number, _day(ctx))

    ctx.world.mutate(_apply)
    if not got[0]:
        return [got[1]]
    before = p.stamina
    p.stamina = min(float(ctx.content.config.stamina_max), p.stamina + got[0])
    gain = round(p.stamina - before)
    return [got[1] if gain == got[0] else got[1].replace(f"體力 +{got[0]}", f"體力 +{gain}（已到上限）")]


def options(ctx: Game) -> list[Option]:
    """有人邀你結義：此地還能做裡一張一對「答應／婉拒」（不在同一地方也回得了）；兄弟在此、今天還沒聚過：一顆「義聚」。"""
    bk = book(ctx)
    if bk is None:
        return []
    out: list[Option] = []
    g = gather_view(ctx, bk)
    if g is not None and g["ready"]:
        out.append(Option(id=f"{KIND}:gather", label=g["label"]))
    for offer in rules.incoming(bk, ctx.state.player.name, ctx.now):
        out.append(Option(id=f"{KIND}:yes:{offer.id}", label=YES.format(him=offer.sender)))
        out.append(Option(id=f"{KIND}:no:{offer.id}", label=NO.format(him=offer.sender)))
    return out


def answer(ctx: Game, arg: str) -> list[str]:
    """jieyi:yes:<編號>、jieyi:no:<編號>、jieyi:gather（義聚）。"""
    if arg == "gather":
        return gather(ctx)
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
        out.append(rules.accept(bk, ctx.content, offer, me.season_number, ctx.now, chron))

    chron: list[str] = []
    ctx.world.mutate(_apply)
    _chronicle(ctx, chron)
    return out


def _chronicle(ctx: Game, lines: list[str]) -> None:
    """名分：開義、入義、割袍、散義寫進這一季的江湖史。"""
    if not lines:
        return
    for line in lines:
        ctx.state.world.chronicle.append(Rumor(time=ctx.state.world.time, text=line))
    ctx._save_season()


def leave(ctx: Game) -> list[str]:
    """割袍斷義（俠客頁門下那一段的鈕，/api/do/jieyi_leave）。寫一則江湖紀錄。"""
    if not on(ctx):
        return [rules.NO_BOND]
    out: list[str] = []
    chron: list[str] = []
    ctx.world.mutate(lambda shared: out.append(rules.leave(shared.jieyi, ctx.content, ctx.state.player.name, ctx.state.player.season_number, ctx.now, chron)))
    if chron:  # 真的割了（沒結義的回 NO_BOND）：自己的列傳當場記
        annals.note(ctx.state, ctx.content, annals.DEED, out[0], 3)
    _chronicle(ctx, chron)
    return ctx._log(out)


def view(ctx: Game) -> dict | None:
    """名帖匣裡的金蘭帖（status 的 jieyi）：沒結義是 {"empty": 說明}、剛割袍是 {"cooling": …}；記憶體裡沒有全服狀態是 None。"""
    bk = book(ctx)
    if bk is None:
        return None
    me = ctx.state.player.name
    bond = rules.bond_of(bk, me)
    if bond is None:
        left = rules.cooling(bk, ctx.content.config.jieyi, me, ctx.now)
        if left > 0:
            return {"cooling": rules.COOLING.format(hours=max(1, int(left // 3600) + (1 if left % 3600 else 0)))}
        return {"empty": EMPTY}  # 名帖匣裡畫一張空的金蘭帖，說怎麼結義
    return {
        "gather": gather_view(ctx, bk),
        "name": rules.bond_name(bk, ctx.content, bond),
        "rank": rules.num(rules.rank_of(bond, me)),
        "members": [{"name": m, "rank": rules.num(i + 1), "me": name_key(m) == name_key(me)} for i, m in enumerate(bond.members)],
        "log": list(reversed(bond.log)),
        "leave_confirm": LEAVE_CONFIRM.format(
            bond=rules.bond_name(bk, ctx.content, bond), hours=max(1, round(ctx.content.config.jieyi.cooldown_seconds / 3600)),
        ),
    }


EMPTY = "跟互換過名帖的人在同一個地方，點他的名字，玩家卡上就能邀他結義。結了義換季也不散。"  # 待 joy 潤
LEAVE_CONFIRM = "割袍斷義就離開{bond}，{hours} 小時內不能再結義。確定？"  # 待 joy 潤


def deliver(ctx: Game) -> None:
    """自己同步時（Feature.deliver_notices）：兄弟被截殺的消息、別人替你追回的銀兩、還沒記進列傳的結義大事。開關關著不送（帳留著）。"""
    if not on(ctx):
        return
    bk = book(ctx)
    if bk is None:
        return
    me = ctx.state.player
    k = name_key(me.name)
    bond = rules.bond_of(bk, me.name)
    bros = {name_key(m) for m in bond.members if name_key(m) != k} if bond else set()
    if not (bk.notes.get(k) or any(name_key(f.victim) in bros or name_key(f.victim) == k for f in bk.feuds)):
        return  # 沒有自己的事：不進 mutate（不寫全服那一列）
    cfg = ctx.content.config.jieyi
    lines: list[str] = []
    notes: list[str] = []
    silver = [0]

    def _apply(shared) -> None:
        book_ = shared.jieyi
        notes.extend(book_.notes.pop(k, []))
        for f in book_.feuds:
            if name_key(f.victim) in bros and f.avenged_by is None and k not in f.told and ctx.now - f.at < cfg.feud_seconds:
                f.told.append(k)
                loc = ctx.content.locations.get(f.place)
                lines.append(FEUD_TOLD.format(victim=f.victim, raider=f.raider, place=loc.name if loc else f.place,
                                              hours=max(1, round((cfg.feud_seconds - (ctx.now - f.at)) / 3600))))
            elif name_key(f.victim) == k and f.avenged_by is not None and k not in f.told:
                f.told.append(k)
                silver[0] += f.owed
                lines.append((FEUD_PAID if f.owed else FEUD_DONE).format(who=f.avenged_by, raider=f.raider, silver=f.owed))
                f.owed = 0
        from tianxia.core import jieyi_base  # noqa: PLC0415

        jieyi_base.prune_feuds(book_, ctx.content, ctx.now)

    ctx.world.mutate(_apply)
    if silver[0]:
        me.stats["silver"] = me.stats.get("silver", 0) + silver[0]
    for line in notes:
        annals.note(ctx.state, ctx.content, annals.DEED, line, 3)
    if lines:
        ctx._write(TITLE, lines)
