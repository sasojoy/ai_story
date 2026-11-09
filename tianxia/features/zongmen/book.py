"""師門武譜（設計稿 v6 第一根柱子，Joy 2026-11-08「不錯，按照設計稿動工」）的純規則：獻式、同門試練、入譜、學式。
只動傳進來的 SectBook 與 PlayerState；帳在全服的 SharedWorldState.sect_books（不分季），由 actions 經 ctx.world.mutate 改。
時刻一律是現實秒（呼叫端給 Game.now）；名號比對一律用 name_key。

- 獻：門人手上自己悟的、合出來的意境（不是內容寫死的基本意境，不是神品），整份抄下來掛在譜上。獻的人自己那一份不少。
- 試練：別的同門花一點心得試一次，就算一票；票湊滿 need 就入譜（第 N 式，刻上獻的人與第幾季），期限到了沒湊滿就退回。
- 學：入了譜的每一式，門人花心得學一份私有的，品質比原本的低一品（下品不再往下）；換季意境照舊歸零，譜還在，再學就好。
- 第三批：也收武學（自創、合成、練成絕學的；art 整份抄下）；學過的人下一季再學只花 relearn_share 成；
  外人截殺打贏親傳撿到殘頁（pages），照殘頁偷學一份下品的。"""
from __future__ import annotations

import math

from tianxia.characters import name_key
from tianxia.core.tuning.zongmen import ZongmenTuning
from tianxia.martial_arts import Insight, MartialArt
from tianxia.state import InsightFx, PlayerState
from tianxia.world_state import BookEntry, SectBook

QUALITY_DOWN = {"絕學": "上品", "上品": "中品", "中品": "下品", "下品": "下品"}
PAGE_QUALITY = "下品"  # 照殘頁偷學的那一份
NUMS = "一二三四五六七八九十"

# 待 joy 潤：這一包新寫給玩家看的字
OFFERED = "你把【{name}】獻上師門武譜，等同門試練。"
TRIED = "你試練了【{name}】（心得 {xinde}）。"
ENTERED = "【{name}】入了{sect}武譜，是第{num}式。"
LEARNED = "你學會了{sect}武譜第{num}式【{name}】。"
NO_XINDE = "心得不夠（要 {xinde}）"
FULL = "武學與意境已經滿了，先熔掉一些"
HAVE = "你已經有這一式了"
OWN_ENTRY = "這是你自己獻的"
DONE_TRY = "你已經試練過了"
SAME_NAME = "譜上已經有一式叫【{name}】"
TOO_MANY = "你還有一式在等同門試練"
NOT_YOURS = "這不是你的意境"
BASIC = "基本意境不能獻"
GOD = "神品意境不能獻"
GONE = "這一式已經不在了。"
PAGE_FOUND = "你從{who}身上搜出一張{sect}武譜的殘頁，記著第{num}式【{name}】。"
PAGE_LEARNED = "你照殘頁偷學了{sect}武譜第{num}式【{name}】的入門。"
NAME_TAKEN = "這一季江湖上已經有一門同名的武學"
CARVE = "第{num}式・{giver}所創・第 {season} 季"


def num(n: int) -> str:
    if 1 <= n <= 10:
        return NUMS[n - 1]
    if n < 20:
        return "十" + NUMS[n - 11]
    tens, ones = divmod(n, 10)
    return NUMS[tens - 1] + "十" + (NUMS[ones - 1] if ones else "")


def need_for(members: int, cfg: ZongmenTuning) -> int:
    """要幾個同門試練：門人（不含獻的人）過半，夾在 need_min～need_max。"""
    others = max(0, members - 1)
    return max(cfg.need_min, min(cfg.need_max, math.ceil(others / 2)))


def expire(book: SectBook, now: float) -> None:
    for e in book.entries:
        if e.status == "pending" and e.expires_at <= now:
            e.status = "dropped"


def entries_in(book: SectBook) -> list[BookEntry]:
    return sorted((e for e in book.entries if e.status == "in"), key=lambda e: e.number)


def pending(book: SectBook, now: float) -> list[BookEntry]:
    return [e for e in book.entries if e.status == "pending" and e.expires_at > now]


def find(book: SectBook, entry_id: str) -> BookEntry | None:
    return next((e for e in book.entries if e.id == entry_id), None)


def name_of(entry: BookEntry) -> str:
    return entry.art.name if entry.art is not None else entry.insight.name if entry.insight is not None else ""


def kind_of(entry: BookEntry) -> str:
    """意境、武學或內功（畫面上寫的那一格）。"""
    return entry.art.kind if entry.art is not None else "意境"


def attr_of(entry: BookEntry) -> str:
    return entry.art.attribute if entry.art is not None else entry.insight.attribute if entry.insight is not None else ""


def taken_names(book: SectBook) -> set[str]:
    return {name_of(e) for e in book.entries if e.status != "dropped"}


def offer_problem(book: SectBook, cfg: ZongmenTuning, giver: str, name: str, now: float) -> str | None:
    k = name_key(giver)
    if sum(1 for e in pending(book, now) if name_key(e.giver) == k) >= cfg.pending_per_giver:
        return TOO_MANY
    if name in taken_names(book):
        return SAME_NAME.format(name=name)
    return None


def offer(
    book: SectBook, cfg: ZongmenTuning, giver: str, season: int, members: int, now: float, *,
    insight: Insight | None = None, fx: InsightFx | None = None, art: MartialArt | None = None, art_quality: str | None = None,
) -> BookEntry:
    """掛上一式：意境給 insight＋fx，武學給 art＋art_quality（兩樣擇一）。"""
    book.seq += 1
    entry = BookEntry(
        id=str(book.seq), giver=giver, season=season, offered_at=now, expires_at=now + cfg.offer_seconds, need=need_for(members, cfg),
        insight=insight.model_copy(deep=True) if insight is not None else None, fx=fx.model_copy(deep=True) if fx is not None else None,
        art=art.model_copy(deep=True) if art is not None else None, art_quality=art_quality,
    )
    book.entries.append(entry)
    return entry


def try_problem(entry: BookEntry, who: str, xinde: int, cfg: ZongmenTuning, now: float) -> str | None:
    if entry.status != "pending" or entry.expires_at <= now:
        return GONE.rstrip("。")
    k = name_key(who)
    if name_key(entry.giver) == k:
        return OWN_ENTRY
    if any(name_key(t) == k for t in entry.tried):
        return DONE_TRY
    if xinde < cfg.trial_xinde:
        return NO_XINDE.format(xinde=cfg.trial_xinde)
    return None


def try_entry(book: SectBook, entry: BookEntry, who: str, now: float) -> bool:
    """記一票；湊滿就入譜（回 True）。"""
    entry.tried.append(who)
    if len(entry.tried) < entry.need:
        return False
    entry.status = "in"
    entry.in_at = now
    entry.number = 1 + max((e.number for e in book.entries if e.status == "in" and e is not entry), default=0)
    return True


def learned_name(p: PlayerState, entry: BookEntry) -> bool:
    """手上已經有這一式（意境照名字認，武學照 id 認：配在身上或在功法庫）。"""
    if entry.art is not None:
        return entry.art.id in {p.member.neigong_id, p.member.wugong_id, *p.arts}
    return entry.insight is not None and any(i.name == entry.insight.name for i in p.own_insights.values() if i.id in p.insights)


def learn_copy(entry: BookEntry, quality: str | None = None) -> tuple[Insight, InsightFx]:
    """學意境的人拿到的那一份：意境照抄（私有，id 由 insights.add_own 另起），品質低一品（quality 給了就照它，殘頁用）。"""
    fx = entry.fx.model_copy(deep=True)
    fx.quality = quality or QUALITY_DOWN.get(fx.quality, fx.quality)
    return entry.insight.model_copy(deep=True), fx


def art_learn_quality(entry: BookEntry) -> str:
    """學武學的人那一份的品質：獻的人那一份低一品（絕學學到的是上品）。"""
    q = entry.art_quality or entry.art.quality
    return QUALITY_DOWN.get(q, q)


def learn_price(entry: BookEntry, who: str, cfg: ZongmenTuning) -> int:
    """學過的人（上一季學過）再學只花 relearn_share 成。"""
    if name_key(who) in entry.learners:
        return max(1, round(cfg.learn_xinde * cfg.relearn_share))
    return cfg.learn_xinde


def note_learner(entry: BookEntry, who: str) -> None:
    k = name_key(who)
    if k not in entry.learners:
        entry.learners.append(k)


def is_inner(p: PlayerState, book: SectBook, cfg: ZongmenTuning) -> bool:
    """親傳：學過本門武譜 inner_learned 式以上，或有一式是自己獻、入了譜的。"""
    rows = entries_in(book)
    k = name_key(p.name)
    if any(name_key(e.giver) == k for e in rows):
        return True
    return sum(1 for e in rows if learned_name(p, e)) >= cfg.inner_learned


def page_pick(book: SectBook, thief: PlayerState, pick: int) -> BookEntry | None:
    """撿殘頁：入了譜、偷的人還沒有殘頁也還沒學過的式裡，照 pick 挑一式（機率呼叫端已經擲過）。"""
    k = name_key(thief.name)
    rows = [e for e in entries_in(book) if k not in e.pages and not learned_name(thief, e)]
    return rows[pick % len(rows)] if rows else None


def pages_of(books: dict[str, SectBook], who: str) -> list[tuple[str, BookEntry]]:
    """who 手上的殘頁：（門派, 那一式）。"""
    k = name_key(who)
    return [(sid, e) for sid, bk in books.items() for e in entries_in(bk) if k in e.pages]


def carve(entry: BookEntry) -> str:
    return CARVE.format(num=num(entry.number), giver=entry.giver, season=entry.season)
