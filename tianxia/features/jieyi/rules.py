"""結義的純規則（設計稿 v2 卷一，Joy 2026-11-07「先做丙，跨季保留關係」）：只動傳進來的 JieyiBook，誰在哪裡、存檔由 actions 做。
時刻一律是現實秒（呼叫端給 Game.now）；名號比對一律用 name_key。"""
from __future__ import annotations

import hashlib

from tianxia.characters import name_key
from tianxia.core.jieyi_base import NUMS, _place_word, bond_name, bond_of, num, rank_of  # noqa: F401（別包讀的那一半在核心，這裡 re-export 同一批）
from tianxia.core.tuning.jieyi import JieyiTuning
from tianxia.models import Content
from tianxia.world_state import JieyiBond, JieyiBook, JieyiOffer


# 待 joy 潤：這一包新寫給玩家看的字
NEED_CARDS = "要先跟他互換過名帖"
NOT_HERE = "要跟他在同一個地方"
HE_HAS = "他已是{bond}的人"
SAME = "你們同為{bond}"
FULL = "{bond}已經滿 {n} 人了"
WAITING = "等他回話"
HE_ASKED = "他邀你結義，到「此地還能做」回他"
COOLING = "剛割袍斷義，{hours} 小時後才能再結義"
HE_COOLING = "他剛割袍斷義，還不能再結義"
GONE = "這份結義的邀請已經不在了。"
SENT = "你向{him}提起結義，等{him}回話。"
FORMED = "你與{him}結為{bond}，排行第{rank}。"
JOINED = "你入了{bond}，排行第{rank}。"
DECLINED = "你婉拒了{him}的結義之邀。"
LEFT = "你割袍斷義，離開了{bond}。"
NO_BOND = "你還沒有結義。"
LOG_FORMED = "第 {season} 季，{a}與{b}在{place}結義。"
LOG_JOINED = "第 {season} 季，{who}在{place}入義，排行第{rank}。"
LOG_LEFT = "第 {season} 季，{who}割袍斷義。"
LOG_ENDED = "第 {season} 季，只剩{who}一人，{bond}就此散了。"
# 名分（第一批）：江湖史一行、各人列傳一行（列傳照「你」寫，他自己同步時記進行狀）
CHRON_FORMED = "{a}與{b}在{place}結為{bond}。"
CHRON_JOINED = "{who}入了{bond}，排行第{rank}。"
CHRON_LEFT = "{who}割袍斷義，離開了{bond}。"
CHRON_ENDED = "{bond}只剩{who}一人，就此散了。"
ANNAL_FORMED = "你與{him}在{place}結為{bond}，排行第{rank}。"
ANNAL_JOINED = "你在{place}入了{bond}，排行第{rank}。"
ANNAL_OTHER_JOINED = "{who}入了你們{bond}，排行第{rank}。"
ANNAL_LEFT = "你割袍斷義，離開了{bond}。"
ANNAL_OTHER_LEFT = "{who}割袍斷義，離開了{bond}。"
ANNAL_ENDED = "{bond}只剩你一人，就此散了。"
NOTES_CAP = 12  # 一個人最多攢幾行還沒記進列傳的（太久沒上線，舊的先丟）


def expire(book: JieyiBook, now: float) -> None:
    book.offers = [o for o in book.offers if o.expires_at > now]


def offer_between(book: JieyiBook, a: str, b: str, now: float) -> JieyiOffer | None:
    pair = {name_key(a), name_key(b)}
    return next((o for o in book.offers if {name_key(o.sender), name_key(o.target)} == pair and o.expires_at > now), None)


def incoming(book: JieyiBook, name: str, now: float) -> list[JieyiOffer]:
    k = name_key(name)
    return [o for o in book.offers if name_key(o.target) == k and o.expires_at > now]


def cooling(book: JieyiBook, cfg: JieyiTuning, name: str, now: float) -> float:
    """割袍斷義之後還要等幾秒（0＝不用等）。"""
    at = book.left_at.get(name_key(name))
    return 0.0 if at is None else max(0.0, at + cfg.cooldown_seconds - now)


def invite_problem(book: JieyiBook, content: Content, me: str, him: str, now: float) -> str | None:
    """我能不能邀他結義（不看名帖、地點：那兩樣呼叫端先看）。回 None 是可以。"""
    cfg = content.config.jieyi
    mine, his = bond_of(book, me), bond_of(book, him)
    if mine is not None and his is not None and mine.id == his.id:
        return SAME.format(bond=bond_name(book, content, mine))
    if his is not None:
        return HE_HAS.format(bond=bond_name(book, content, his))
    if mine is not None and len(mine.members) >= cfg.max_members:
        return FULL.format(bond=bond_name(book, content, mine), n=cfg.max_members)
    left = cooling(book, cfg, me, now)
    if left > 0:
        return COOLING.format(hours=max(1, int(left // 3600) + (1 if left % 3600 else 0)))
    if cooling(book, cfg, him, now) > 0:
        return HE_COOLING
    return None


def _offer_id(sender: str, target: str, now: float) -> str:
    return hashlib.sha1(f"{name_key(sender)}|{name_key(target)}|{now!r}".encode()).hexdigest()[:12]


def send(book: JieyiBook, content: Content, sender: str, target: str, location: str, now: float) -> JieyiOffer:
    offer = JieyiOffer(
        id=_offer_id(sender, target, now), sender=sender, target=target, location=location,
        sent_at=now, expires_at=now + content.config.jieyi.offer_seconds,
    )
    book.offers.append(offer)
    return offer


def find(book: JieyiBook, offer_id: str, now: float) -> JieyiOffer | None:
    return next((o for o in book.offers if o.id == offer_id and o.expires_at > now), None)


def drop(book: JieyiBook, offer_id: str) -> None:
    book.offers = [o for o in book.offers if o.id != offer_id]


def note(book: JieyiBook, name: str, line: str) -> None:
    """記一行要寫進 name 列傳的（他自己同步時 actions.deliver 記進行狀）。"""
    k = name_key(name)
    book.notes[k] = (book.notes.get(k, []) + [line])[-NOTES_CAP:]


def _log(book: JieyiBook, content: Content, bond: JieyiBond, line: str) -> None:
    bond.log.append(line)
    cap = content.config.jieyi.log_cap
    if len(bond.log) > cap:
        bond.log = bond.log[-cap:]


def accept(book: JieyiBook, content: Content, offer: JieyiOffer, season: int, now: float, chron: list[str] | None = None) -> str:
    """他答應了（offer.target 是答應的人）：兩人都沒有就開一組；邀的人已經有一組就入那一組。回給答應的人看的那一句。
    答應的那一刻再驗一次（這段時間裡可能別人先入了、滿了、他自己入了別組）：不行回那一句、邀請照樣收掉。
    chron 有給就接上江湖史那一行（名分）；各人列傳那一行記在 book.notes。"""
    drop(book, offer.id)
    problem = invite_problem(book, content, offer.sender, offer.target, now)
    if problem is not None:
        return f"結不成：{problem}。"
    place = content.locations.get(offer.location)
    place_name = place.name if place else offer.location
    bond = bond_of(book, offer.sender)
    out = chron if chron is not None else []
    if bond is None:
        book.seq += 1
        bond = JieyiBond(id=str(book.seq), place=offer.location, season=season, members=[offer.sender, offer.target])
        book.bonds[bond.id] = bond
        _log(book, content, bond, LOG_FORMED.format(season=season, a=offer.sender, b=offer.target, place=place_name))
        name = bond_name(book, content, bond)
        out.append(CHRON_FORMED.format(a=offer.sender, b=offer.target, place=place_name, bond=name))
        note(book, offer.sender, ANNAL_FORMED.format(him=offer.target, place=place_name, bond=name, rank=num(1)))
        note(book, offer.target, ANNAL_FORMED.format(him=offer.sender, place=place_name, bond=name, rank=num(2)))
        return FORMED.format(him=offer.sender, bond=name, rank=num(2))
    bond.members.append(offer.target)
    rank = num(len(bond.members))
    _log(book, content, bond, LOG_JOINED.format(season=season, who=offer.target, place=place_name, rank=rank))
    name = bond_name(book, content, bond)
    out.append(CHRON_JOINED.format(who=offer.target, bond=name, rank=rank))
    for m in bond.members[:-1]:
        note(book, m, ANNAL_OTHER_JOINED.format(who=offer.target, bond=name, rank=rank))
    note(book, offer.target, ANNAL_JOINED.format(place=place_name, bond=name, rank=rank))
    return JOINED.format(bond=name, rank=rank)


def leave(book: JieyiBook, content: Content, name: str, season: int, now: float, chron: list[str] | None = None) -> str:
    """割袍斷義。chron 同 accept；離開的人自己那一行列傳由呼叫端當場記（他就在線上），留下的人記在 book.notes。"""
    bond = bond_of(book, name)
    if bond is None:
        return NO_BOND
    was = bond_name(book, content, bond)
    out = chron if chron is not None else []
    k = name_key(name)
    bond.members = [m for m in bond.members if name_key(m) != k]
    book.left_at[k] = now
    book.offers = [o for o in book.offers if name_key(o.sender) != k]  # 他發出去、還沒回的邀請一起收掉
    _log(book, content, bond, LOG_LEFT.format(season=season, who=name))
    out.append(CHRON_LEFT.format(who=name, bond=was))
    if len(bond.members) <= 1:
        _log(book, content, bond, LOG_ENDED.format(season=season, who="".join(bond.members) or name, bond=was))
        last = bond.members[0] if bond.members else None
        del book.bonds[bond.id]
        if last is not None:
            book.left_at.pop(name_key(last), None)  # 被留下的那一位不算割袍，不冷卻
            out.append(CHRON_ENDED.format(bond=was, who=last))
            note(book, last, ANNAL_OTHER_LEFT.format(who=name, bond=was))
            note(book, last, ANNAL_ENDED.format(bond=was))
    else:
        for m in bond.members:
            note(book, m, ANNAL_OTHER_LEFT.format(who=name, bond=was))
    return LEFT.format(bond=was)
