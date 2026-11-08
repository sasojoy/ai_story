"""師門武譜（設計稿 v6 第一根柱子，Joy 2026-11-08「不錯，按照設計稿動工」）的純規則：獻式、同門試練、入譜、學式。
只動傳進來的 SectBook 與 PlayerState；帳在全服的 SharedWorldState.sect_books（不分季），由 actions 經 ctx.world.mutate 改。
時刻一律是現實秒（呼叫端給 Game.now）；名號比對一律用 name_key。

- 獻：門人手上自己悟的、合出來的意境（不是內容寫死的基本意境，不是神品），整份抄下來掛在譜上。獻的人自己那一份不少。
- 試練：別的同門花一點心得試一次，就算一票；票湊滿 need 就入譜（第 N 式，刻上獻的人與第幾季），期限到了沒湊滿就退回。
- 學：入了譜的每一式，門人花心得學一份私有的，品質比原本的低一品（下品不再往下）；換季意境照舊歸零，譜還在，再學就好。"""
from __future__ import annotations

import math

from tianxia.characters import name_key
from tianxia.core.tuning.zongmen import ZongmenTuning
from tianxia.martial_arts import Insight
from tianxia.state import InsightFx, PlayerState
from tianxia.world_state import BookEntry, SectBook

QUALITY_DOWN = {"上品": "中品", "中品": "下品", "下品": "下品"}
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


def offer_problem(book: SectBook, cfg: ZongmenTuning, giver: str, insight: Insight, now: float) -> str | None:
    k = name_key(giver)
    if sum(1 for e in pending(book, now) if name_key(e.giver) == k) >= cfg.pending_per_giver:
        return TOO_MANY
    if any(e.insight.name == insight.name for e in book.entries if e.status != "dropped"):
        return SAME_NAME.format(name=insight.name)
    return None


def offer(book: SectBook, cfg: ZongmenTuning, giver: str, insight: Insight, fx: InsightFx, season: int, members: int, now: float) -> BookEntry:
    book.seq += 1
    entry = BookEntry(
        id=str(book.seq), insight=insight.model_copy(deep=True), fx=fx.model_copy(deep=True), giver=giver, season=season,
        offered_at=now, expires_at=now + cfg.offer_seconds, need=need_for(members, cfg),
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
    return any(i.name == entry.insight.name for i in p.own_insights.values() if i.id in p.insights)


def learn_copy(entry: BookEntry) -> tuple[Insight, InsightFx]:
    """學的人拿到的那一份：意境照抄（私有，id 由 insights.add_own 另起），品質低一品。"""
    fx = entry.fx.model_copy(deep=True)
    fx.quality = QUALITY_DOWN.get(fx.quality, fx.quality)
    return entry.insight.model_copy(deep=True), fx


def carve(entry: BookEntry) -> str:
    return CARVE.format(num=num(entry.number), giver=entry.giver, season=entry.season)
