"""結義「別人讀」的那一半（照 bounty_base、seal_base）：結義包 features/jieyi/ 的名號、排行與第一批（Joy 2026-11-09「贈素材不要 其他按照建議」）
別包要問的三件事——同義不相殘（截殺、懸賞榜讀）、替兄出頭的仇（截殺讀、截殺打贏時結清）、義名排行（玩家卡、名帖讀）。只靠核心跑得起來，不 import 包。

帳在全服的 SharedWorldState.jieyi（不分季）；讀一律經 book(world)，改一律經 world.mutate。開關 Config.jieyi.enabled 關著時每一個函式都當沒有結義。
包的 rules.py re-export NUMS、num、bond_of、rank_of、bond_name 同一批物件。"""
from __future__ import annotations

import hashlib
from typing import Any

from ..characters import name_key
from ..models import Content
from ..world_state import JieyiBond, JieyiBook, JieyiFeud

NUMS = "一二三四五六七八九十"

# 待 joy 潤：別包畫出來的結義字句
CARD_TAG = "{bond}・行{rank}"  # 玩家卡、名帖上名號旁邊那一小行
SWORN_NO = "你們是結義的兄弟，下不了這個手。"  # 截殺、揭通緝被擋（卡上不畫截殺，直接打 API 才看得到）
SWORN_BOUNTY = "要拿的是你結義兄弟，這一張你不揭。"
AVENGED = "你替{victim}出了這口氣，從{raider}身上追回 {silver} 兩，會轉交給{victim}。"
AVENGED_NONE = "你替{victim}出了這口氣。"
AVENGE_LABEL = "替兄出頭"  # 卡上截殺那一顆換成這個名字（有仇可報時）
AVENGE_CONFIRM = "{raider}截殺過你的兄弟{victim}，要替{victim}出這口氣？輸了一樣要丟銀兩、掉氣血。"


def num(n: int) -> str:
    return NUMS[n - 1] if 1 <= n <= len(NUMS) else str(n)


def on(content: Content) -> bool:
    return content.config.jieyi.enabled


def book(world: Any) -> JieyiBook | None:
    """全服的結義帳；記憶體裡沒有全服狀態的（某些測試）是 None。"""
    try:
        return world.read().jieyi
    except (AttributeError, NotImplementedError):
        return None


def bond_of(bk: JieyiBook, name: str) -> JieyiBond | None:
    k = name_key(name)
    return next((b for b in bk.bonds.values() if any(name_key(m) == k for m in b.members)), None)


def rank_of(bond: JieyiBond, name: str) -> int:
    k = name_key(name)
    return next((i + 1 for i, m in enumerate(bond.members) if name_key(m) == k), 0)


def _place_word(content: Content, place: str) -> str:
    loc = content.locations.get(place)
    word = (loc.name if loc else place).split("（")[0]
    return word[:-1] if len(word) > 2 and word[-1] in "郡縣" else word


def bond_name(bk: JieyiBook, content: Content, bond: JieyiBond) -> str:
    """名號照開義的地點與人數取（潁川二義、潁川三義）；同地同人數撞名的照開義的先後補「其二」「其三」。"""
    base = f"{_place_word(content, bond.place)}{num(len(bond.members))}義"
    twins = sorted(
        (b for b in bk.bonds.values() if f"{_place_word(content, b.place)}{num(len(b.members))}義" == base),
        key=lambda b: int(b.id) if b.id.isdigit() else 0,
    )
    nth = next((i for i, b in enumerate(twins) if b.id == bond.id), 0)
    return base if nth == 0 else f"{base}（其{num(nth + 1)}）"


def _book_on(content: Content, world: Any) -> JieyiBook | None:
    return book(world) if on(content) else None


def brothers(content: Content, world: Any, name: str) -> set[str]:
    """name 的結義兄弟（名號鍵，不含自己）；沒結義、開關關著是空的。"""
    bk = _book_on(content, world)
    bond = bond_of(bk, name) if bk is not None else None
    return {name_key(m) for m in bond.members if name_key(m) != name_key(name)} if bond else set()


def sworn(content: Content, world: Any, a: str, b: str) -> bool:
    """a、b 同在一組結義（義不相殘：截殺不畫、通緝不揭）。"""
    return name_key(b) in brothers(content, world, a)


def card_tag(content: Content, world: Any, name: str) -> str:
    """玩家卡、名帖上的義名與排行（「白馬寺三義・行二」）；沒結義是空字串。"""
    bk = _book_on(content, world)
    bond = bond_of(bk, name) if bk is not None else None
    return CARD_TAG.format(bond=bond_name(bk, content, bond), rank=num(rank_of(bond, name))) if bond else ""


def feud_against(content: Content, world: Any, me: str, raider: str, now: float) -> JieyiFeud | None:
    """me 能替兄出頭打 raider 的那一筆仇：受害的是 me 此刻的兄弟（不是 me 自己）、raider 不是我們這一組的人、還沒報、還在時限內。"""
    bk = _book_on(content, world)
    if bk is None:
        return None
    bros = brothers(content, world, me)
    if not bros or name_key(raider) in bros or name_key(raider) == name_key(me):
        return None
    limit = content.config.jieyi.feud_seconds
    return next((f for f in reversed(bk.feuds) if f.avenged_by is None and name_key(f.raider) == name_key(raider)
                 and name_key(f.victim) in bros and now - f.at < limit), None)


def prune_feuds(bk: JieyiBook, content: Content, now: float) -> None:
    """報過、銀兩也交到了的，與過了時限還沒報的仇清掉（追回的銀兩還沒交到的留著，等受害的人上線領）。"""
    limit = content.config.jieyi.feud_seconds
    bk.feuds = [f for f in bk.feuds if (f.avenged_by is not None and f.owed > 0) or (f.avenged_by is None and now - f.at < limit)]


def record_feud(ctx: Any, victim: str, raider: str) -> None:
    """ctx（raider）截殺打贏了 victim：victim 有結義兄弟就記一筆仇（兄弟上線時收到一則、24 小時內能替他出頭）。截殺 raid()、
    設伏的伏兵打贏時叫；替兄出頭本身打贏的那一下不叫（不然冤冤相報、一路記下去）。開關關著、他沒結義什麼都不做。"""
    c = ctx.content
    if not on(c) or book(ctx.world) is None:
        return

    def _apply(shared) -> None:
        bk = shared.jieyi
        prune_feuds(bk, c, ctx.now)
        bond = bond_of(bk, victim)
        if bond is None or len(bond.members) < 2:
            return
        fid = hashlib.sha1(f"{name_key(victim)}|{name_key(raider)}|{ctx.now!r}".encode()).hexdigest()[:12]
        bk.feuds.append(JieyiFeud(id=fid, victim=victim, raider=raider, place=ctx.state.player.location, at=ctx.now))

    ctx.world.mutate(_apply)


def avenge(ctx: Any, raider: str, taken: int) -> list[str]:
    """替兄出頭打贏了 raider（截殺 raid() 照截殺輸的規則分完銀兩之後叫）：贏到的那一份（taken）從 ctx 身上拿出來、記在仇上等受害的兄弟領，
    仇結清。沒有這一筆仇（剛被別人報了）回 []、銀兩不動。"""
    c, me = ctx.content, ctx.state.player
    out: list[str] = []
    paid = [0]

    def _apply(shared) -> None:
        bk = shared.jieyi
        bros = {name_key(m) for b in [bond_of(bk, me.name)] if b for m in b.members if name_key(m) != name_key(me.name)}
        limit = c.config.jieyi.feud_seconds
        feud = next((f for f in reversed(bk.feuds) if f.avenged_by is None and name_key(f.raider) == name_key(raider)
                     and name_key(f.victim) in bros and ctx.now - f.at < limit), None)
        if feud is None:
            return
        silver = max(0, min(taken, me.stats.get("silver", 0)))
        feud.avenged_by, feud.owed = me.name, silver
        paid[0] = silver
        out.append((AVENGED if silver else AVENGED_NONE).format(victim=feud.victim, raider=raider, silver=silver))

    ctx.world.mutate(_apply)
    me.stats["silver"] = me.stats.get("silver", 0) - paid[0]
    return out
